"""Task inventory is local, read-only and distinct from empty/failed retrieval."""

import asyncio
import json
import os
import shutil
import subprocess
from urllib.parse import urlencode

import pytest
from test_detail_query import snapshot
from test_inspection_http import get, workspace
from test_material_tasks import invocation, seed_tasks

from gamingcreator.application.storage import InvocationStatus, RunStatus, StageStatus
from gamingcreator.cli.main import execute_tasks
from gamingcreator.infrastructure import sqlite_store
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def unknown_attempt(project, *, run_id="run-000"):
    async def build():
        store = await SqliteTimelineStore.open(project)
        try:
            run = await store.load_run(run_id)
            await store.begin_stage(run_id, "asr", run.asset.sha256)
            await store.finish_stage(run_id, "asr", StageStatus.COMPLETED, run.asset.sha256)
            await store.begin_stage(run_id, "vision", run.asset.sha256)
            await store.begin_stage(run_id, "vision-000001", run.asset.sha256)
            opening = invocation().metadata
            await store.begin_invocation("unknown-1", run_id, "vision-000001", "logical-1", opening)
            await store.finish_invocation(
                "unknown-1", InvocationStatus.INTERRUPTED, opening, "provider.timeout"
            )
            await store.stop_run(run_id, RunStatus.INTERRUPTED, "provider.timeout")
        finally:
            await store.close()

    asyncio.run(build())


def refuse_work(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Task listing attempted media, inference or recovery")

    monkeypatch.setattr(sqlite_store, "_hash", forbidden)
    for name in ("recover", "prepare_resume", "load_media_bundle"):
        monkeypatch.setattr(SqliteTimelineStore, name, forbidden)


def test_task_http_is_paged_read_only_and_preserves_unknown_attempts(tmp_path, monkeypatch):
    project, _ = seed_tasks(tmp_path / "artifacts", 3)
    unknown_attempt(project)
    before = snapshot(project)
    refuse_work(monkeypatch)
    with workspace(tmp_path) as base:
        query = urlencode({"project": str(project), "limit": 2})
        status, headers, raw = get(base, "/api/tasks?" + query)
        payload = json.loads(raw)
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert payload["schemaVersion"] == "material-tasks-v1" and payload["hasMore"] is True
        assert payload["project"] == str(project)
        assert [task["runId"] for task in payload["tasks"]] == ["run-002", "run-001"]
        status, _, raw = get(
            base, "/api/tasks?" + urlencode({"project": str(project), "run": "run-000"})
        )
        task = json.loads(raw)["tasks"][0]
        assert status == 200 and task["phase"] == "analysis_incomplete"
        assert task["cost"]["unknownReservationCny"] == "2" and task["cost"]["remainingCny"] == "3"
        assert task["requiresRetryConfirmation"] is True
        assert "nextCommand" not in task and "sourcePath" not in task
        status, head, raw = get(base, "/api/tasks?" + query, method="HEAD")
        assert status == 200 and raw == b"" and int(head["Content-Length"]) > 0
        assert (
            get(base, "/api/tasks?" + query, headers={"Origin": "https://external.invalid"})[0]
            == 403
        )
        assert (
            get(base, "/api/tasks?" + urlencode({"project": str(project), "run": "missing"}))[0]
            == 404
        )
    assert snapshot(project) == before
    cli_task = asyncio.run(execute_tasks(project, run_id="run-000"))["tasks"][0]
    assert cli_task["requiresRetryConfirmation"] is True and cli_task["nextCommand"] is None
    assert snapshot(project) == before


@pytest.mark.parametrize(
    "extra",
    [
        "limit=0",
        "limit=201",
        "offset=-1",
        "offset=1000001",
        "offset=no",
        "run=",
        "run=run-000&offset=1",
        "limit=1&limit=2",
    ],
)
def test_task_http_rejects_invalid_page_and_identity(tmp_path, extra):
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    with workspace(tmp_path) as base:
        status, _, body = get(
            base, "/api/tasks?" + urlencode({"project": str(project)}) + "&" + extra
        )
        assert status == 400 and json.loads(body)["exitCode"] == 2


def test_public_task_script_without_api_key_reads_single_saved_task(tmp_path):
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    environment = os.environ.copy()
    environment.pop("DEEPSEEK_API_KEY", None)
    from pathlib import Path

    repository = Path(__file__).resolve().parents[1]
    before = snapshot(project)
    result = subprocess.run(
        [
            shutil.which("pwsh") or "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repository / "scripts/list-tasks.ps1"),
            "-Project",
            str(project),
            "-Run",
            "run-000",
            "-Json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["total"] == 1 and payload["tasks"][0]["phase"] == "media_prepared"
    assert payload["tasks"][0]["nextCommand"][1] == "analyze"
    assert snapshot(project) == before
