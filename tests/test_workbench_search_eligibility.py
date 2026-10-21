"""Workbench inspect/search aligns coverage-gap refusal with searchEligible."""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from test_sqlite_store import CONFIG, bundle_fixture

from gamingcreator.application.storage import RunStatus
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.server import create_server
from gamingcreator.ui.service import (
    inspect_run,
    project_runs_payload,
    search_abstention_for_run,
)


def _gap_project(root):
    bundle = bundle_fixture(root, run_id="run-gap")
    project = root / "project"

    async def build():
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-gap", bundle.asset, CONFIG)
            await store.begin_stage("run-gap", "media", bundle.asset.sha256)
            await store.persist_media_bundle("run-gap", bundle)
            await store.finish_media_preparation("run-gap")
            await store.stop_run("run-gap", RunStatus.FAILED, "analysis.coverage_gap")
        finally:
            await store.close()

    asyncio.run(build())
    return project


def test_search_abstention_maps_coverage_gap():
    class _Run:
        status = RunStatus.FAILED
        error_code = "analysis.coverage_gap"

    assert search_abstention_for_run(_Run()) == "retrieval.coverage_gap"


def test_inspect_run_marks_coverage_gap_not_search_eligible(tmp_path):
    project = _gap_project(tmp_path)

    async def scenario():
        payload = await inspect_run(project, "run-gap", "跳跃连招", tmp_path, mode="lexical")
        assert payload["runStatus"] == "failed"
        assert payload["errorCode"] == "analysis.coverage_gap"
        assert payload["searchEligible"] is False
        assert payload["completedEligible"] is False
        assert payload["abstentionReason"] == "retrieval.coverage_gap"
        assert payload["candidates"] == []

    asyncio.run(scenario())


def test_project_runs_payload_exposes_search_eligible(tmp_path):
    project = _gap_project(tmp_path)

    async def scenario():
        payload = await project_runs_payload(project)
        row = next(item for item in payload["runs"] if item["id"] == "run-gap")
        assert row["status"] == "failed"
        assert row["errorCode"] == "analysis.coverage_gap"
        assert row["searchEligible"] is False
        assert row["completedEligible"] is False

    asyncio.run(scenario())


@contextmanager
def workspace(repository):
    for _ in range(32):
        try:
            server = create_server("127.0.0.1", 20000 + secrets.randbelow(40000), repository)
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No free browser-safe test port.")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()


def _request(base, path, *, data=None, method=None):
    headers = {"Content-Type": "application/json"} if data is not None else {}
    body = None if data is None else json.dumps(data).encode("utf-8")
    request = Request(base + path, data=body, headers=headers, method=method)
    opener = build_opener(ProxyHandler({}))
    try:
        response = opener.open(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_http_inspect_coverage_gap_returns_aligned_abstention(tmp_path):
    project = _gap_project(tmp_path)
    reference = project.relative_to(tmp_path).as_posix()
    with workspace(tmp_path) as base:
        status, payload = _request(
            base,
            "/api/inspect?"
            + urlencode(
                {
                    "project": reference,
                    "run": "run-gap",
                    "query": "跳跃",
                    "mode": "lexical",
                    "top": "5",
                }
            ),
        )
        assert status == 200
        assert payload["searchEligible"] is False
        assert payload["errorCode"] == "analysis.coverage_gap"
        assert payload["abstentionReason"] == "retrieval.coverage_gap"


def test_http_project_search_refuses_coverage_gap(tmp_path):
    project = _gap_project(tmp_path)
    reference = project.relative_to(tmp_path).as_posix()
    with workspace(tmp_path) as base:
        status, payload = _request(
            base,
            "/api/search-project",
            method="POST",
            data={
                "project": reference,
                "runs": ["run-gap"],
                "query": "跳跃",
                "mode": "lexical",
                "top": 5,
            },
        )
        assert status == 400
        assert payload["code"] == "retrieval.coverage_gap"
        assert "覆盖缺口" in payload["message"]


def test_app_js_surfaces_coverage_gap_refusal_copy():
    text = Path("src/gamingcreator/ui/static/app.js").read_text(encoding="utf-8")
    assert "function isCoverageGapBlocked" in text
    assert "function isSearchEligible" in text
    assert "该分析保留覆盖缺口，未获完整资格，不能用于检索或正式验收。" in text
    assert "isSearchEligible(state.view)" in text
    assert "searchBlockedMessage(state.view)" in text
