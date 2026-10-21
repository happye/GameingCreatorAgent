"""Offline directed gap-fill contract: inventory + target validation only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.analysis_reliability import (
    DIRECTED_GAP_FILL_PROPOSAL,
    POLICY,
    coverage_stage_sets,
    directed_gap_fill_inventory,
    load_coverage_document,
    validate_directed_gap_fill_targets,
)
from gamingcreator.domain.errors import AppError


def _coverage(
    *,
    completed: list[str] | None = None,
    rejected: list[str] | None = None,
    unexecuted: list[str] | None = None,
    completed_eligible: bool = False,
) -> dict:
    windows = []
    for stage in completed or []:
        windows.append(
            {
                "stageId": stage,
                "status": "completed",
                "invocationVerified": True,
                "attempted": True,
                "checkpointStatus": "completed",
                "stopCode": None,
                "startUs": 0,
                "endUs": 1,
            }
        )
    for index, stage in enumerate(rejected or []):
        windows.append(
            {
                "stageId": stage,
                "status": "rejected",
                "invocationVerified": False,
                "attempted": True,
                "checkpointStatus": "failed",
                "stopCode": "provider.schema",
                "startUs": 1000 * (index + 1),
                "endUs": 1000 * (index + 1) + 1,
            }
        )
    for stage in unexecuted or []:
        windows.append(
            {
                "stageId": stage,
                "status": "unexecuted",
                "invocationVerified": False,
                "attempted": False,
                "checkpointStatus": None,
                "stopCode": None,
                "startUs": 9000,
                "endUs": 9001,
            }
        )
    return {
        "schemaVersion": 1,
        "runId": "run-fixture",
        "sourceSha256": "a" * 64,
        "configHash": "b" * 64,
        "pipelineHash": "c" * 64,
        "policyVersion": POLICY,
        "policyHash": "d" * 64,
        "completedEligible": completed_eligible,
        "windows": windows,
    }


def test_inventory_lists_only_rejected_and_forbids_completed():
    coverage = _coverage(
        completed=["vision-000000", "vision-000001"],
        rejected=["vision-000021", "vision-000248", "vision-000253"],
        unexecuted=[],
    )
    inventory = directed_gap_fill_inventory(coverage)
    assert inventory["proposalIdentity"] == DIRECTED_GAP_FILL_PROPOSAL
    assert inventory["notIsolateResume"] is True
    assert inventory["isolatePolicy"] == POLICY
    assert inventory["authorization"]["feeAuthorized"] is False
    assert inventory["authorization"]["sendAuthorized"] is False
    assert inventory["counts"] == {"completed": 2, "rejected": 3, "unexecuted": 0}
    assert inventory["allowedRejectedStageIds"] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]
    assert inventory["forbiddenCompletedStageIds"] == [
        "vision-000000",
        "vision-000001",
    ]
    assert inventory["completedEligible"] is False
    assert inventory["rules"]["mustNotResendCompleted"] is True
    assert inventory["rules"]["requiresNewFeeProposalAndAuth"] is True
    assert [row["stageId"] for row in inventory["rejectedWindows"]] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]


def test_validate_accepts_rejected_subset_only():
    coverage = _coverage(
        completed=["vision-000000"],
        rejected=["vision-000021", "vision-000248", "vision-000253"],
    )
    accepted = validate_directed_gap_fill_targets(coverage, ["vision-000248", "vision-000253"])
    assert accepted == frozenset({"vision-000248", "vision-000253"})
    all_rejected = validate_directed_gap_fill_targets(
        coverage, ["vision-000021", "vision-000248", "vision-000253"]
    )
    assert all_rejected == frozenset({"vision-000021", "vision-000248", "vision-000253"})


@pytest.mark.parametrize(
    "targets,code",
    [
        ([], "input.directed_gap_fill_targets"),
        (["vision-000000"], "input.directed_gap_fill_targets"),
        (["vision-000021", "vision-000000"], "input.directed_gap_fill_targets"),
        (["vision-000999"], "input.directed_gap_fill_targets"),
        (["vision-000021", "vision-000021"], "input.directed_gap_fill_targets"),
        (["vision-000900"], "input.directed_gap_fill_targets"),
        ("vision-000021", "input.directed_gap_fill_targets"),
    ],
)
def test_validate_refuses_unsafe_or_empty_targets(targets, code):
    coverage = _coverage(
        completed=["vision-000000"],
        rejected=["vision-000021", "vision-000248"],
        unexecuted=["vision-000900"],
    )
    with pytest.raises(AppError) as refused:
        validate_directed_gap_fill_targets(coverage, targets)
    assert refused.value.code == code


def test_validate_refuses_unexecuted_even_alone():
    coverage = _coverage(
        completed=["vision-000000"],
        rejected=["vision-000021"],
        unexecuted=["vision-000900"],
    )
    with pytest.raises(AppError) as refused:
        validate_directed_gap_fill_targets(coverage, ["vision-000900"])
    assert refused.value.code == "input.directed_gap_fill_targets"
    assert "未执行" in refused.value.message


def test_load_coverage_document_roundtrip(tmp_path: Path):
    path = tmp_path / "analysis_coverage.json"
    payload = _coverage(
        completed=["vision-000000"],
        rejected=["vision-000021"],
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_coverage_document(path)
    sets = coverage_stage_sets(loaded)
    assert sets["completed"] == frozenset({"vision-000000"})
    assert sets["rejected"] == frozenset({"vision-000021"})
    assert sets["unexecuted"] == frozenset()


def test_load_coverage_document_rejects_bad_status(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "windows": [
                    {"stageId": "vision-000000", "status": "mystery"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AppError) as refused:
        load_coverage_document(path)
    assert refused.value.code == "input.coverage_document"


def test_real_zhongkui_coverage_inventory_when_present():
    path = Path(
        "artifacts/independent-footage-20261011/runs/"
        "5c7894aa10e94b8aa82533bd77f9871e/analysis_coverage.json"
    )
    if not path.is_file():
        pytest.skip("real coverage artifact absent")
    coverage = load_coverage_document(path)
    inventory = directed_gap_fill_inventory(coverage)
    assert inventory["counts"]["completed"] == 269
    assert inventory["counts"]["rejected"] == 3
    assert inventory["counts"]["unexecuted"] == 0
    assert inventory["allowedRejectedStageIds"] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]
    assert "vision-000000" in inventory["forbiddenCompletedStageIds"]
    assert inventory["completedEligible"] is False
    assert inventory["authorization"]["feeAuthorized"] is False
    accepted = validate_directed_gap_fill_targets(coverage, inventory["allowedRejectedStageIds"])
    assert accepted == frozenset(inventory["allowedRejectedStageIds"])
    with pytest.raises(AppError):
        validate_directed_gap_fill_targets(coverage, ["vision-000000", "vision-000021"])
