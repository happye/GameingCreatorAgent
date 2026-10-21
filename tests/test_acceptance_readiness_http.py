"""Workbench acceptance-readiness API is local, read-only, never claims pass."""

from __future__ import annotations

import json
from urllib.parse import urlencode

from test_detail_query import snapshot
from test_inspection_http import get, workspace
from test_material_tasks import seed_tasks
from test_material_tasks_http import refuse_work

from gamingcreator.application.acceptance_readiness import ACCEPTANCE_READINESS_VERSION


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
        assert payload["formalAcceptanceStatus"] == "blocked_no_searchable_run"
        assert payload["formalAcceptanceStatus"] != "passed"
        assert "no_searchable_run" in payload["projectBlockers"]
        assert "A_or_B_or_D_coverage_gap" in payload["userDecisionsPending"]
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
    assert snapshot(project) == before


def test_workbench_static_exposes_readiness_controls():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "gamingcreator" / "ui" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert 'id="open-readiness"' in html
    assert 'id="readiness-dialog"' in html
    assert "acceptance-readiness-v1" in js or "/api/acceptance-readiness" in js
    assert "function loadReadiness" in js
    assert 'material-tasks-v2' in js
    assert "formalAcceptancePassed !== false" in js
    assert "不会" in html or "不宣称" in html
