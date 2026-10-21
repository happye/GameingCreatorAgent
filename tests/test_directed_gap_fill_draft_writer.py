"""Read-only directed gap-fill draft writer tests (no provider calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.analysis_reliability import POLICY
from gamingcreator.application.directed_gap_fill import (
    assert_directed_gap_fill_draft_inert,
    write_directed_gap_fill_proposal_draft,
)
from gamingcreator.domain.errors import AppError, ExitCode


def _coverage_file(
    tmp_path: Path, *, rejected: list[str], completed: list[str] | None = None
) -> Path:
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
    for index, stage in enumerate(rejected):
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
    payload = {
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
    path = tmp_path / "analysis_coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_write_draft_bundle_is_inert(tmp_path: Path):
    coverage = _coverage_file(
        tmp_path,
        completed=["vision-000000"],
        rejected=["vision-000021", "vision-000248", "vision-000253"],
    )
    output = tmp_path / "artifacts" / "directed-gap-fill-draft"
    receipt = write_directed_gap_fill_proposal_draft(coverage, output)
    assert receipt["providerCalls"] == 0
    assert receipt["launcherStarted"] is False
    assert receipt["selectsOptionB"] is False
    assert receipt["gapsCleared"] is False
    assert receipt["authorization"] == {
        "executionAuthorized": False,
        "feeAuthorized": False,
        "sendAuthorized": False,
        "optionBChosenByUser": False,
    }
    draft_path = Path(str(receipt["draftPath"]))
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert_directed_gap_fill_draft_inert(draft)
    assert draft["targets"]["stageIds"] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]
    assert (output / "coverage-inventory-v1.json").is_file()
    assert (output / "README.md").is_file()
    assert (output / "write-receipt-v1.json").is_file()
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert "未授权" in readme
    assert "不是" in readme


def test_write_draft_subset_and_cost_placeholder_still_inert(tmp_path: Path):
    coverage = _coverage_file(
        tmp_path,
        completed=["vision-000000"],
        rejected=["vision-000021", "vision-000248"],
    )
    output = tmp_path / "out"
    receipt = write_directed_gap_fill_proposal_draft(
        coverage,
        output,
        proposed_stage_ids=["vision-000248"],
        maximum_additional_cost_cny="0.25",
    )
    draft = json.loads(Path(str(receipt["draftPath"])).read_text(encoding="utf-8"))
    assert draft["targets"]["stageIds"] == ["vision-000248"]
    assert draft["limits"]["maximumAdditionalCostCny"] == "0.25"
    assert draft["authorization"]["feeAuthorized"] is False
    assert_directed_gap_fill_draft_inert(draft)


def test_write_draft_refuses_completed_targets(tmp_path: Path):
    coverage = _coverage_file(
        tmp_path,
        completed=["vision-000000"],
        rejected=["vision-000021"],
    )
    with pytest.raises(AppError) as refused:
        write_directed_gap_fill_proposal_draft(
            coverage,
            tmp_path / "out",
            proposed_stage_ids=["vision-000000"],
        )
    assert refused.value.code == "input.directed_gap_fill_targets"
    assert not (tmp_path / "out" / "directed-gap-fill-proposal-draft-v1.json").exists()


def test_cli_prepare_directed_gap_fill_draft(tmp_path: Path):
    import importlib.util

    script = Path("scripts/prepare-directed-gap-fill-draft.py").resolve()
    spec = importlib.util.spec_from_file_location("prepare_directed_gap_fill_draft", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    coverage = _coverage_file(tmp_path, rejected=["vision-000021", "vision-000248"])
    output = tmp_path / "artifacts" / "draft-cli"
    code = module.main(
        [
            "--coverage",
            str(coverage),
            "--output",
            str(output),
            "--stage",
            "vision-000021",
        ]
    )
    assert code == 0
    draft = json.loads(
        (output / "directed-gap-fill-proposal-draft-v1.json").read_text(encoding="utf-8")
    )
    assert draft["targets"]["stageIds"] == ["vision-000021"]
    assert_directed_gap_fill_draft_inert(draft)


def test_cli_reports_input_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    import importlib.util

    script = Path("scripts/prepare-directed-gap-fill-draft.py").resolve()
    spec = importlib.util.spec_from_file_location("prepare_directed_gap_fill_draft_err", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    missing = tmp_path / "missing-coverage.json"
    output = tmp_path / "out"
    code = module.main(["--coverage", str(missing), "--output", str(output)])
    assert code == int(ExitCode.INPUT)
    err = capsys.readouterr().err
    assert err


def test_real_zhongkui_write_when_present(tmp_path: Path):
    coverage = Path(
        "artifacts/independent-footage-20261011/runs/"
        "5c7894aa10e94b8aa82533bd77f9871e/analysis_coverage.json"
    )
    if not coverage.is_file():
        pytest.skip("real coverage artifact absent")
    output = tmp_path / "zhongkui-draft"
    receipt = write_directed_gap_fill_proposal_draft(coverage, output)
    assert receipt["targetStageIds"] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]
    draft = json.loads(Path(str(receipt["draftPath"])).read_text(encoding="utf-8"))
    assert_directed_gap_fill_draft_inert(draft)
    assert draft["gapsCleared"] is False
    assert draft["selectsOptionB"] is False
