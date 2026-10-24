"""Offline coverage-gap-report never clears gaps or chooses A/B/D."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from test_material_tasks import seed_tasks

from gamingcreator.application.coverage_gap_report import (
    COVERAGE_GAP_REPORT_VERSION,
    assert_coverage_gap_report_inert,
    build_coverage_gap_report,
)
from gamingcreator.application.tasks import TASKS_VERSION
from gamingcreator.cli.main import execute_coverage_gap_report


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


def _gap_row(run_id: str) -> dict:
    return {
        "runId": run_id,
        "phase": "analysis_coverage_gap",
        "phaseLabel": "分析保留覆盖缺口，未获完整资格",
        "runStatus": "failed",
        "errorCode": "analysis.coverage_gap",
        "searchEligible": False,
        "completedEligible": False,
        "continuationBlockers": ["coverage_gap"],
        "sourceName": f"{run_id}.mp4",
    }


def _ok_row(run_id: str) -> dict:
    return {
        "runId": run_id,
        "phase": "completed",
        "phaseLabel": "completed",
        "runStatus": "completed",
        "errorCode": None,
        "searchEligible": True,
        "completedEligible": True,
        "continuationBlockers": [],
        "sourceName": f"{run_id}.mp4",
    }


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
            {
                "stageId": "vision-000248",
                "status": "rejected",
                "invocationVerified": False,
                "attempted": True,
                "checkpointStatus": "failed",
                "stopCode": "provider.schema",
                "startUs": 4_000_000,
                "endUs": 5_000_000,
            },
            {
                "stageId": "vision-000253",
                "status": "rejected",
                "invocationVerified": False,
                "attempted": True,
                "checkpointStatus": "failed",
                "stopCode": "provider.schema",
                "startUs": 6_000_000,
                "endUs": 7_000_000,
            },
        ],
    }


def test_report_lists_gap_runs_without_claiming_cleared() -> None:
    doc = build_coverage_gap_report(_tasks(_gap_row("g1"), _ok_row("ok")))
    assert_coverage_gap_report_inert(doc)
    assert doc["schemaVersion"] == COVERAGE_GAP_REPORT_VERSION
    assert doc["gapRunCount"] == 1
    assert doc["runs"][0]["runId"] == "g1"
    assert doc["runs"][0]["searchEligible"] is False
    assert doc["coverageGapsCleared"] is False
    assert doc["optionChosen"] is None
    assert doc["featureClaims"] == {"F006": False, "F009": False, "F010": False}


def test_report_loads_coverage_windows(tmp_path: Path) -> None:
    project = tmp_path / "project"
    run_id = "gap-run"
    coverage_dir = project / "runs" / run_id
    coverage_dir.mkdir(parents=True)
    coverage_path = coverage_dir / "analysis_coverage.json"
    coverage_path.write_text(
        json.dumps(_minimal_coverage(run_id=run_id), ensure_ascii=False),
        encoding="utf-8",
    )
    doc = build_coverage_gap_report(_tasks(_gap_row(run_id)), project=project)
    assert doc["rejectedStageCount"] == 3
    summary = doc["runs"][0]["windowSummary"]
    assert summary["rejectedStageIds"] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]
    assert summary["authorization"]["optionBChosen"] is False
    assert summary["completedEligible"] is False


def test_coverage_only_mode_without_task_rows(tmp_path: Path) -> None:
    coverage_path = tmp_path / "analysis_coverage.json"
    coverage_path.write_text(
        json.dumps(_minimal_coverage(run_id="solo"), ensure_ascii=False),
        encoding="utf-8",
    )
    doc = build_coverage_gap_report(_tasks(), coverage=coverage_path)
    assert doc["gapRunCount"] == 1
    assert doc["runs"][0]["coverageLoaded"] is True
    assert doc["rejectedStageCount"] == 3
    assert "A_retain_gaps" in doc["userDecisionsPending"]


def test_inert_guard_rejects_cleared_or_chosen() -> None:
    doc = build_coverage_gap_report(_tasks(_gap_row("g")))
    bad = dict(doc)
    bad["coverageGapsCleared"] = True
    with pytest.raises(AssertionError, match="coverageGapsCleared"):
        assert_coverage_gap_report_inert(bad)
    bad2 = dict(doc)
    bad2["optionChosen"] = "B_directed_gap_fill"
    with pytest.raises(AssertionError, match="optionChosen"):
        assert_coverage_gap_report_inert(bad2)


def test_write_and_cli_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    # Force a coverage-gap failed snapshot by rewriting via store is heavy;
    # instead exercise coverage-only path through execute with empty gaps + explicit coverage.
    coverage_path = tmp_path / "analysis_coverage.json"
    coverage_path.write_text(
        json.dumps(_minimal_coverage(run_id="cli-gap"), ensure_ascii=False),
        encoding="utf-8",
    )
    out = tmp_path / "report.json"
    before = (project / "timeline.sqlite3").read_bytes()

    async def run() -> None:
        document = await execute_coverage_gap_report(
            project,
            coverage=coverage_path,
            output=out,
        )
        assert document["schemaVersion"] == COVERAGE_GAP_REPORT_VERSION
        assert document["coverageGapsCleared"] is False
        assert Path(document["outputPath"]) == out

    asyncio.run(run())
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["rejectedStageCount"] == 3
    assert (project / "timeline.sqlite3").read_bytes() == before
