"""Cross-surface acceptance-readiness inert contract (CLI/API/JS)."""

from __future__ import annotations

from pathlib import Path

from gamingcreator.application.acceptance_readiness import (
    ACCEPTANCE_READINESS_VERSION,
    FORBIDDEN_FORMAL_STATUSES,
    FORBIDDEN_STATUS_LABELS,
    assert_acceptance_readiness_inert,
    build_acceptance_readiness,
    surface_js_inert_guards,
)
from gamingcreator.application.tasks import TASKS_VERSION

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "gamingcreator" / "ui" / "static"
SERVER = ROOT / "src" / "gamingcreator" / "ui" / "server.py"
CLI = ROOT / "src" / "gamingcreator" / "cli" / "main.py"


def _tasks(*rows: dict) -> dict:
    return {
        "schemaVersion": TASKS_VERSION,
        "tasks": list(rows),
        "total": len(rows),
        "offset": 0,
        "limit": 100,
        "hasMore": False,
        "ordering": "created-time-descending-then-run-id",
        "snapshotOnly": True,
    }


def _row(run_id: str, *, phase: str, search_eligible: bool) -> dict:
    return {
        "runId": run_id,
        "phase": phase,
        "phaseLabel": phase,
        "runStatus": "completed" if search_eligible else "failed",
        "errorCode": "analysis.coverage_gap" if phase == "analysis_coverage_gap" else None,
        "searchEligible": search_eligible,
        "completedEligible": search_eligible,
        "continuationBlockers": ["coverage_gap"] if phase == "analysis_coverage_gap" else [],
        "sourceName": f"{run_id}.mp4",
    }


def test_all_built_statuses_remain_inert() -> None:
    docs = [
        build_acceptance_readiness(_tasks()),
        build_acceptance_readiness(
            _tasks(_row("g", phase="analysis_coverage_gap", search_eligible=False))
        ),
        build_acceptance_readiness(_tasks(_row("ok", phase="completed", search_eligible=True))),
    ]
    for doc in docs:
        assert_acceptance_readiness_inert(doc)
        assert doc["schemaVersion"] == ACCEPTANCE_READINESS_VERSION
        assert doc["formalAcceptancePassed"] is False
        assert doc["formalAcceptanceStatus"] not in FORBIDDEN_FORMAL_STATUSES
        assert doc["formalAcceptanceStatusLabel"] not in FORBIDDEN_STATUS_LABELS


def test_workbench_and_workflow_js_keep_shared_inert_guards() -> None:
    guards = surface_js_inert_guards()
    assert guards
    surfaces = {
        "app.js": (STATIC / "app.js").read_text(encoding="utf-8"),
        "benchmark-workflow.js": (STATIC / "benchmark-workflow.js").read_text(encoding="utf-8"),
    }
    for name, source in surfaces.items():
        for guard in guards:
            assert guard in source, f"{name} missing inert guard {guard!r}"


def test_server_exposes_readiness_capability_and_route() -> None:
    source = SERVER.read_text(encoding="utf-8")
    assert "acceptance-readiness-v1" in source
    assert '"/api/acceptance-readiness"' in source


def test_cli_registers_acceptance_readiness_command() -> None:
    source = CLI.read_text(encoding="utf-8")
    assert "acceptance-readiness" in source
    assert "execute_acceptance_readiness" in source
    assert "不宣称通过" in source
