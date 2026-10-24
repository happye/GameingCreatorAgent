"""Workbench coverage-gap-report API is local, read-only, never clears gaps."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

from test_detail_query import snapshot
from test_inspection_http import get, workspace
from test_material_tasks import seed_tasks
from test_material_tasks_http import refuse_work

from gamingcreator.application.coverage_gap_report import COVERAGE_GAP_REPORT_VERSION


def _minimal_coverage(*, run_id: str = "gap-run") -> dict:
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "sourceSha256": "a" * 64,
        "configHash": "b" * 64,
        "pipelineHash": "c" * 64,
        "policyVersion": "isolate-schema-v1",
        "policyHash": "d" * 64,
        "completedEligible": False,
        "windows": [
            {
                "stageId": "vision-000000",
                "status": "completed",
                "invocationVerified": True,
                "attempted": True,
                "checkpointStatus": "completed",
                "stopCode": None,
                "startUs": 0,
                "endUs": 1_000_000,
            },
            {
                "stageId": "vision-000021",
                "status": "rejected",
                "invocationVerified": False,
                "attempted": True,
                "checkpointStatus": "failed",
                "stopCode": "provider.schema",
                "startUs": 2_000_000,
                "endUs": 3_000_000,
            },
        ],
    }


def test_coverage_gap_report_http_is_read_only_and_never_cleared(tmp_path, monkeypatch):
    project, _ = seed_tasks(tmp_path / "artifacts", 2)
    before = snapshot(project)
    refuse_work(monkeypatch)
    coverage = tmp_path / "analysis_coverage.json"
    coverage.write_text(
        json.dumps(_minimal_coverage(run_id="solo"), ensure_ascii=False), encoding="utf-8"
    )
    with workspace(tmp_path) as base:
        query = urlencode({"project": str(project), "limit": 100, "coverage": str(coverage)})
        status, headers, raw = get(base, "/api/coverage-gap-report?" + query)
        payload = json.loads(raw)
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert payload["schemaVersion"] == COVERAGE_GAP_REPORT_VERSION
        assert payload["coverageGapsCleared"] is False
        assert payload["optionChosen"] is None
        assert payload["featureClaims"] == {"F006": False, "F009": False, "F010": False}
        assert payload["rejectedStageCount"] == 1
        assert "A_retain_gaps" in payload["userDecisionsPending"]
        health_status, _, health_raw = get(base, "/api/health")
        health = json.loads(health_raw)
        assert health_status == 200
        assert "coverage-gap-report-v1" in health["capabilities"]
        assert (
            get(
                base,
                "/api/coverage-gap-report?" + query,
                headers={"Origin": "https://external.invalid"},
            )[0]
            == 403
        )
    assert snapshot(project) == before


def test_workbench_static_exposes_coverage_gap_controls():
    root = Path(__file__).resolve().parents[1] / "src" / "gamingcreator" / "ui" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert 'id="open-coverage-gaps"' in html
    assert 'id="coverage-gaps-dialog"' in html
    assert "不清除缺口" in html or "不代选" in html
    assert "/api/coverage-gap-report" in js
    assert "function loadCoverageGaps" in js
    assert "function renderCoverageGaps" in js
    assert "coverageGapsCleared !== false" in js
    assert "coverage-gap-report-v1" in js
    assert "coverageGapSummary" in js
