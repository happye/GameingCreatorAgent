"""Offline acceptance readiness never claims F006 or human-eval pass."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.acceptance_readiness import (
    ACCEPTANCE_READINESS_VERSION,
    assert_acceptance_readiness_inert,
    build_acceptance_readiness,
    build_inert_contract,
    write_acceptance_readiness,
)
from gamingcreator.application.tasks import TASKS_VERSION


def _tasks(*rows: dict, total: int | None = None) -> dict:
    items = list(rows)
    return {
        "schemaVersion": TASKS_VERSION,
        "tasks": items,
        "total": len(items) if total is None else total,
        "offset": 0,
        "limit": 100,
        "hasMore": False,
        "ordering": "created-time-descending-then-run-id",
        "snapshotOnly": True,
    }


def _row(
    run_id: str,
    *,
    phase: str,
    search_eligible: bool,
    error_code: str | None = None,
    blockers: list[str] | None = None,
) -> dict:
    return {
        "runId": run_id,
        "phase": phase,
        "phaseLabel": phase,
        "runStatus": "completed" if search_eligible else "failed",
        "errorCode": error_code,
        "searchEligible": search_eligible,
        "completedEligible": search_eligible,
        "continuationBlockers": list(blockers or []),
        "sourceName": f"{run_id}.mp4",
    }


def test_empty_project_blocked_no_runs() -> None:
    doc = build_acceptance_readiness(_tasks(), project="/tmp/demo")
    assert doc["schemaVersion"] == ACCEPTANCE_READINESS_VERSION
    assert doc["formalAcceptanceStatus"] == "blocked_no_runs"
    assert doc["formalAcceptancePassed"] is False
    assert doc["humanEvalPassed"] is False
    assert doc["qualityGate"] is None
    assert doc["featureClaims"] == {"F006": False, "F009": False, "F010": False}
    assert doc["coverageGapsCleared"] is False
    assert "no_runs" in doc["projectBlockers"]
    assert doc["partialSnapshot"] is False
    assert doc["userDecisionsPending"] == []


def test_coverage_gap_only_not_searchable() -> None:
    doc = build_acceptance_readiness(
        _tasks(
            _row(
                "gap-1",
                phase="analysis_coverage_gap",
                search_eligible=False,
                error_code="analysis.coverage_gap",
                blockers=["coverage_gap"],
            ),
            _row("prep-1", phase="media_prepared", search_eligible=False),
        )
    )
    assert doc["formalAcceptanceStatus"] == "blocked_no_searchable_run"
    assert doc["counts"]["coverageGapRuns"] == 1
    assert doc["counts"]["searchableRuns"] == 0
    assert "coverage_gap_present" in doc["projectBlockers"]
    assert "no_searchable_run" in doc["projectBlockers"]
    assert doc["formalAcceptancePassed"] is False
    assert doc["featureClaims"]["F006"] is False
    assert doc["userDecisionsPending"] == ["A_or_B_or_D_coverage_gap"]
    assert doc["coverageGapRunIds"] == ["gap-1"]


def test_partial_snapshot_without_searchable_row_is_unknown_not_blocked() -> None:
    # Page one of a larger project: an older completed run may be on a later page.
    tasks = _tasks(_row("prep-1", phase="media_prepared", search_eligible=False), total=150)
    tasks["hasMore"] = True
    doc = build_acceptance_readiness(tasks)
    assert doc["formalAcceptanceStatus"] == "unknown_partial_task_snapshot"
    assert doc["partialSnapshot"] is True
    assert doc["taskTotal"] == 150 and doc["taskRowsInSnapshot"] == 1
    assert "partial_task_snapshot" in doc["projectBlockers"]
    assert "no_searchable_run" not in doc["projectBlockers"]
    assert doc["formalAcceptancePassed"] is False
    later = _tasks(total=150)
    later["offset"] = 100
    empty_page = build_acceptance_readiness(later)
    assert empty_page["formalAcceptanceStatus"] == "unknown_partial_task_snapshot"
    assert "no_runs" not in empty_page["projectBlockers"]


def test_no_gap_rows_leave_no_coverage_decision() -> None:
    doc = build_acceptance_readiness(
        _tasks(
            _row("ok-1", phase="completed", search_eligible=True),
            _row("prep-1", phase="media_prepared", search_eligible=False),
        )
    )
    assert doc["userDecisionsPending"] == []
    assert doc["coverageGapRunIds"] == []


def test_searchable_still_awaits_human_never_passed() -> None:
    doc = build_acceptance_readiness(_tasks(_row("ok-1", phase="completed", search_eligible=True)))
    assert doc["formalAcceptanceStatus"] == "awaiting_human_labels_and_freeze"
    assert doc["counts"]["searchableRuns"] == 1
    assert doc["searchableRunIds"] == ["ok-1"]
    assert doc["formalAcceptancePassed"] is False
    assert doc["humanEvalPassed"] is False
    assert "human_labels_required" in doc["projectBlockers"]
    assert "freeze_and_bind_required" in doc["projectBlockers"]


def test_inert_guard_rejects_pass_claims() -> None:
    doc = build_acceptance_readiness(_tasks())
    bad = dict(doc)
    bad["formalAcceptancePassed"] = True
    with pytest.raises(AssertionError, match="formalAcceptancePassed"):
        assert_acceptance_readiness_inert(bad)
    bad = dict(doc)
    bad["featureClaims"] = {"F006": True, "F009": False, "F010": False}
    with pytest.raises(AssertionError, match="F006"):
        assert_acceptance_readiness_inert(bad)
    bad = dict(doc)
    bad["qualityGate"] = True
    with pytest.raises(AssertionError, match="qualityGate"):
        assert_acceptance_readiness_inert(bad)


def test_write_acceptance_readiness_roundtrip(tmp_path: Path) -> None:
    doc = build_acceptance_readiness(
        _tasks(_row("ok-1", phase="completed", search_eligible=True)),
        project=str(tmp_path),
    )
    target = tmp_path / "acceptance-readiness.json"
    written = write_acceptance_readiness(doc, target)
    loaded = json.loads(written.read_text(encoding="utf-8"))
    assert loaded["formalAcceptancePassed"] is False
    assert loaded["featureClaims"]["F006"] is False
    assert_acceptance_readiness_inert(loaded)


def test_execute_acceptance_readiness_cli_read_only(tmp_path, monkeypatch) -> None:
    import asyncio

    from test_material_tasks import seed_tasks

    from gamingcreator.cli.main import execute_acceptance_readiness
    from gamingcreator.infrastructure import sqlite_store
    from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

    project, _bundles = seed_tasks(tmp_path, count=2)

    def forbidden(*args, **kwargs):
        raise AssertionError("acceptance readiness performed media/model/recovery work")

    monkeypatch.setattr(sqlite_store, "_hash", forbidden)
    for name in ("_integrity", "load_media_bundle", "load_timeline", "recover", "prepare_resume"):
        monkeypatch.setattr(SqliteTimelineStore, name, forbidden)
    before = (project / "timeline.sqlite3").read_bytes()

    async def run():
        out_path = tmp_path / "readiness.json"
        document = await execute_acceptance_readiness(project, output=out_path)
        assert document["formalAcceptancePassed"] is False
        assert document["featureClaims"]["F006"] is False
        assert document["humanEvalPassed"] is False
        assert document["formalAcceptanceStatus"] == "blocked_no_searchable_run"
        assert document["outputPath"] == str(out_path.resolve())
        assert out_path.is_file()
        return document

    asyncio.run(run())
    assert (project / "timeline.sqlite3").read_bytes() == before


def test_forbidden_pass_labels_are_rejected() -> None:
    doc = build_acceptance_readiness(_tasks())
    bad = dict(doc)
    bad["formalAcceptanceStatusLabel"] = "验收通过"
    with pytest.raises(AssertionError, match="forbidden formalAcceptanceStatusLabel"):
        assert_acceptance_readiness_inert(bad)


def test_inert_contract_is_embedded_and_stable() -> None:
    doc = build_acceptance_readiness(_tasks())
    assert doc["inertContract"] == build_inert_contract()
    assert doc["inertContract"]["schemaVersion"] == "acceptance-readiness-inert-v1"
