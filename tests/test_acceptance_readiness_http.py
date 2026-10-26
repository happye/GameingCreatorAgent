"""Workbench acceptance-readiness API is local, read-only, never claims pass."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlencode

from test_detail_query import snapshot
from test_inspection_http import get, stored_project, workspace
from test_material_tasks import CONFIG, seed_tasks
from test_material_tasks_http import refuse_work
from test_sqlite_store import bundle_fixture

from gamingcreator.application.acceptance_readiness import (
    ACCEPTANCE_READINESS_VERSION,
    INERT_CONTRACT_VERSION,
)
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def test_acceptance_readiness_http_is_read_only_and_never_passed(tmp_path, monkeypatch):
    project, _ = seed_tasks(tmp_path / "artifacts", 2)
    before = snapshot(project)
    refuse_work(monkeypatch)
    with workspace(tmp_path) as base:
        query = urlencode({"project": str(project), "limit": 100})
        status, headers, raw = get(base, "/api/acceptance-readiness?" + query)
        payload = json.loads(raw)
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert payload["schemaVersion"] == ACCEPTANCE_READINESS_VERSION
        assert payload["project"] == str(project)
        assert payload["formalAcceptancePassed"] is False
        assert payload["humanEvalPassed"] is False
        assert payload["qualityGate"] is None
        assert payload["coverageGapsCleared"] is False
        assert payload["featureClaims"] == {"F006": False, "F009": False, "F010": False}
        assert payload["inertContract"]["schemaVersion"] == INERT_CONTRACT_VERSION
        assert payload["inertContract"]["snapshotOnlyRequired"] is True
        assert payload["formalAcceptanceStatus"] == "blocked_no_searchable_run"
        assert payload["formalAcceptanceStatus"] != "passed"
        assert "no_searchable_run" in payload["projectBlockers"]
        assert payload["userDecisionsPending"] == []
        assert payload["partialSnapshot"] is False
        status, head, raw = get(base, "/api/acceptance-readiness?" + query, method="HEAD")
        assert status == 200 and raw == b"" and int(head["Content-Length"]) > 0
        assert (
            get(
                base,
                "/api/acceptance-readiness?" + query,
                headers={"Origin": "https://external.invalid"},
            )[0]
            == 403
        )
        health_status, _, health_raw = get(base, "/api/health")
        health = json.loads(health_raw)
        assert health_status == 200
        assert "acceptance-readiness-v1" in health["capabilities"]
        assert "acceptance-readiness-inert-v1" in health["capabilities"]
    assert snapshot(project) == before


def test_acceptance_readiness_http_reads_every_task_unless_paged(tmp_path, monkeypatch):
    project, _ = seed_tasks(tmp_path / "artifacts", 3)
    refuse_work(monkeypatch)
    monkeypatch.setattr("gamingcreator.ui.service.all_tasks_payload", _small_pages)
    with workspace(tmp_path) as base:
        whole = json.loads(
            get(base, "/api/acceptance-readiness?" + urlencode({"project": str(project)}))[2]
        )
        assert whole["taskTotal"] == 3 and whole["taskRowsInSnapshot"] == 3
        assert whole["partialSnapshot"] is False
        assert whole["formalAcceptanceStatus"] == "blocked_no_searchable_run"
        paged = json.loads(
            get(
                base,
                "/api/acceptance-readiness?" + urlencode({"project": str(project), "limit": 2}),
            )[2]
        )
        assert paged["taskTotal"] == 3 and paged["taskRowsInSnapshot"] == 2
        assert paged["partialSnapshot"] is True
        assert paged["formalAcceptanceStatus"] == "unknown_partial_task_snapshot"
        assert paged["formalAcceptancePassed"] is False


def test_readiness_finds_an_old_completed_run_beyond_the_first_page(tmp_path, monkeypatch):
    """TD017: newer unfinished runs used to hide the only completed run on a later page."""
    project, _ = stored_project(tmp_path)
    newer = [bundle_fixture(project.parent, run_id=f"run-new-{index}") for index in range(2)]

    async def add():
        store = await SqliteTimelineStore.open(project)
        try:
            for bundle in newer:
                run_id = bundle.images[0].evidence_id.split(":")[0]
                await store.create_run(run_id, bundle.asset, CONFIG)
                await store.begin_stage(run_id, "media", bundle.asset.sha256)
                await store.persist_media_bundle(run_id, bundle)
                await store.finish_media_preparation(run_id)
        finally:
            await store.close()

    asyncio.run(add())
    monkeypatch.setattr("gamingcreator.ui.service.all_tasks_payload", _small_pages)
    with workspace(tmp_path) as base:
        reference = project.relative_to(tmp_path).as_posix()
        whole = json.loads(
            get(base, "/api/acceptance-readiness?" + urlencode({"project": reference}))[2]
        )
        assert whole["taskTotal"] == 3 and whole["taskRowsInSnapshot"] == 3
        assert whole["searchableRunIds"] == ["run-1"]
        assert whole["formalAcceptanceStatus"] == "awaiting_human_labels_and_freeze"
        assert whole["formalAcceptancePassed"] is False
        first_page = json.loads(
            get(
                base,
                "/api/acceptance-readiness?" + urlencode({"project": reference, "limit": 2}),
            )[2]
        )
        assert first_page["formalAcceptanceStatus"] == "unknown_partial_task_snapshot"


async def _small_pages(store):
    from gamingcreator.application.tasks import all_tasks_payload

    # Force several pages so the merge path, not one large page, is exercised.
    return await all_tasks_payload(store, page_size=1)


def test_workbench_static_exposes_readiness_controls():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "gamingcreator" / "ui" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert 'id="open-readiness"' in html
    assert 'id="readiness-dialog"' in html
    assert "acceptance-readiness-v1" in js or "/api/acceptance-readiness" in js
    assert "function loadReadiness" in js
    assert "material-tasks-v2" in js
    assert "formalAcceptancePassed !== false" in js
    assert "acceptance-readiness-inert-v1" in js
    assert "inertContract" in js
    assert "不会" in html or "不宣称" in html
