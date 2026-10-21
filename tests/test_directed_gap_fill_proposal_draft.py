"""Offline directed gap-fill proposal draft template tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gamingcreator.application.analysis_reliability import (
    DIRECTED_GAP_FILL_PROPOSAL,
    POLICY,
    load_coverage_document,
)
from gamingcreator.application.directed_gap_fill import (
    DRAFT_SCHEMA,
    assert_directed_gap_fill_draft_inert,
    build_directed_gap_fill_proposal_draft,
    draft_content_sha256,
)
from gamingcreator.domain.errors import AppError


def _coverage(
    *,
    completed: list[str] | None = None,
    rejected: list[str] | None = None,
    unexecuted: list[str] | None = None,
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
        "completedEligible": False,
        "windows": windows,
    }


def test_draft_defaults_to_all_rejected_and_stays_inert():
    coverage = _coverage(
        completed=["vision-000000", "vision-000001"],
        rejected=["vision-000021", "vision-000248", "vision-000253"],
    )
    draft = build_directed_gap_fill_proposal_draft(coverage)
    assert draft["schemaVersion"] == DRAFT_SCHEMA
    assert draft["proposalIdentity"] == DIRECTED_GAP_FILL_PROPOSAL
    assert draft["selectsOptionB"] is False
    assert draft["gapsCleared"] is False
    assert draft["draftStatus"] == "template-unfrozen"
    assert draft["targets"]["stageIds"] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]
    assert draft["targets"]["windowCount"] == 3
    assert draft["limits"]["maximumAdditionalCostCny"] is None
    assert draft["limits"]["costCeilingFilled"] is False
    assert draft["authorization"] == {
        "executionAuthorized": False,
        "feeAuthorized": False,
        "sendAuthorized": False,
        "optionBChosenByUser": False,
        "requiresNewExplicitFeeAndImageApproval": True,
        "draftDoesNotAuthorizeAnything": True,
    }
    assert "vision-000000" in draft["forbidden"]["completedStageIds"]
    assert draft["draftContentSha256"] == draft_content_sha256(draft)
    assert_directed_gap_fill_draft_inert(draft)


def test_draft_accepts_rejected_subset_and_optional_cost_placeholder():
    coverage = _coverage(
        completed=["vision-000000"],
        rejected=["vision-000021", "vision-000248", "vision-000253"],
    )
    draft = build_directed_gap_fill_proposal_draft(
        coverage,
        proposed_stage_ids=["vision-000248", "vision-000253"],
        maximum_additional_cost_cny="0.50",
    )
    assert draft["targets"]["stageIds"] == ["vision-000248", "vision-000253"]
    assert draft["limits"]["maximumAdditionalCostCny"] == "0.50"
    assert draft["limits"]["costCeilingFilled"] is True
    assert draft["authorization"]["feeAuthorized"] is False
    assert draft["authorization"]["optionBChosenByUser"] is False
    assert_directed_gap_fill_draft_inert(draft)


@pytest.mark.parametrize(
    "bad_cost",
    [0, "0", "-1", "abc"],
)
def test_draft_rejects_non_positive_or_invalid_cost(bad_cost):
    coverage = _coverage(rejected=["vision-000021"])
    with pytest.raises(AppError) as refused:
        build_directed_gap_fill_proposal_draft(coverage, maximum_additional_cost_cny=bad_cost)
    assert refused.value.code == "input.directed_gap_fill_draft"


def test_empty_cost_string_means_unset():
    coverage = _coverage(rejected=["vision-000021"])
    draft = build_directed_gap_fill_proposal_draft(coverage, maximum_additional_cost_cny="")
    assert draft["limits"]["maximumAdditionalCostCny"] is None
    assert draft["limits"]["costCeilingFilled"] is False
    assert_directed_gap_fill_draft_inert(draft)


def test_draft_refuses_completed_targets():
    coverage = _coverage(
        completed=["vision-000000"],
        rejected=["vision-000021"],
    )
    with pytest.raises(AppError) as refused:
        build_directed_gap_fill_proposal_draft(
            coverage, proposed_stage_ids=["vision-000000", "vision-000021"]
        )
    assert refused.value.code == "input.directed_gap_fill_targets"


def test_assert_inert_catches_tampered_authorization():
    coverage = _coverage(rejected=["vision-000021"])
    draft = build_directed_gap_fill_proposal_draft(coverage)
    draft["authorization"] = dict(draft["authorization"])
    cast_auth = draft["authorization"]
    assert isinstance(cast_auth, dict)
    cast_auth["executionAuthorized"] = True
    with pytest.raises(AppError) as refused:
        assert_directed_gap_fill_draft_inert(draft)
    assert refused.value.code == "input.directed_gap_fill_draft"


def test_assert_inert_catches_hash_mismatch():
    coverage = _coverage(rejected=["vision-000021"])
    draft = build_directed_gap_fill_proposal_draft(coverage)
    draft["purpose"] = "tampered"
    with pytest.raises(AppError) as refused:
        assert_directed_gap_fill_draft_inert(draft)
    assert refused.value.code == "input.directed_gap_fill_draft"


def test_real_zhongkui_draft_when_present():
    path = Path(
        "artifacts/independent-footage-20261011/runs/"
        "5c7894aa10e94b8aa82533bd77f9871e/analysis_coverage.json"
    )
    if not path.is_file():
        pytest.skip("real coverage artifact absent")
    coverage = load_coverage_document(path)
    draft = build_directed_gap_fill_proposal_draft(coverage)
    assert draft["targets"]["stageIds"] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]
    assert draft["inventoryCounts"]["completed"] == 269
    assert draft["inventoryCounts"]["rejected"] == 3
    assert draft["coverageCompletedEligible"] is False
    assert draft["gapsCleared"] is False
    assert draft["selectsOptionB"] is False
    assert_directed_gap_fill_draft_inert(draft)
