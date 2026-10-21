"""Read-only directed gap-fill draft writer tests (no provider calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.analysis_reliability import POLICY
from gamingcreator.application.directed_gap_fill import (
    DEFAULT_DIAGNOSIS_DIR,
    DEFAULT_DOCS_REPORT,
    assert_directed_gap_fill_draft_inert,
    build_diagnosis_evidence_links,
    format_diagnosis_readme_section,
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


def _diagnosis_pack(tmp_path: Path) -> Path:
    pack = tmp_path / "coverage-gap-diagnosis"
    pack.mkdir()
    payload = {
        "schemaVersion": "coverage-gap-diagnosis-v1",
        "paidProviderCalls": 0,
        "readOnly": True,
        "commonFailureMode": {
            "stopCode": "provider.schema",
            "schemaError": "event_frame_boundaries",
            "mechanism": "same-frame aliases empty the action interval",
        },
        "gaps": [
            {
                "stageId": "vision-000021",
                "schemaError": "event_frame_boundaries",
                "windowUs": {"startUs": 1, "endUs": 2},
                "sameFrameRejectEvents": [],
                "primaryRejectInference": {
                    "eventIndex": 2,
                    "inferredStartUs": 10,
                    "inferredEndUs": 11,
                    "rejectReason": (
                        "schemaDetail shows endUs == startUs + 1 (legacy same-frame pattern)"
                    ),
                },
                "schemaDetailPresent": True,
                "schemaProjectionPresent": False,
            },
            {
                "stageId": "vision-000248",
                "schemaError": "event_frame_boundaries",
                "windowUs": {"startUs": 100, "endUs": 200},
                "sameFrameRejectEvents": [
                    {
                        "eventIndex": 2,
                        "startFrameId": "f8",
                        "endFrameId": "f8",
                        "rejectReason": ("first_time >= last_time when startFrameId == endFrameId"),
                    }
                ],
                "primaryRejectInference": {
                    "eventIndex": 2,
                    "startFrameId": "f8",
                    "endFrameId": "f8",
                },
                "schemaDetailPresent": False,
                "schemaProjectionPresent": True,
            },
        ],
    }
    (pack / "diagnosis-v1.json").write_text(json.dumps(payload), encoding="utf-8")
    return pack


def test_write_draft_bundle_is_inert(tmp_path: Path):
    coverage = _coverage_file(
        tmp_path,
        completed=["vision-000000"],
        rejected=["vision-000021", "vision-000248", "vision-000253"],
    )
    output = tmp_path / "artifacts" / "directed-gap-fill-draft"
    receipt = write_directed_gap_fill_proposal_draft(
        coverage,
        output,
        diagnosis_dir=tmp_path / "missing-diagnosis",
        docs_report=tmp_path / "missing-report.md",
        repo_root=tmp_path,
    )
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
    assert (output / "diagnosis-links-v1.json").is_file()
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert "未授权" in readme
    assert "同帧拒因诊断证据" in readme


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
        diagnosis_dir=tmp_path / "missing-diagnosis",
        docs_report=tmp_path / "missing-report.md",
        repo_root=tmp_path,
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
            diagnosis_dir=tmp_path / "missing-diagnosis",
            repo_root=tmp_path,
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
            "--diagnosis-dir",
            str(tmp_path / "missing-diagnosis"),
            "--docs-report",
            str(tmp_path / "missing-report.md"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert code == 0
    draft = json.loads(
        (output / "directed-gap-fill-proposal-draft-v1.json").read_text(encoding="utf-8")
    )
    assert draft["targets"]["stageIds"] == ["vision-000021"]
    assert_directed_gap_fill_draft_inert(draft)
    assert "同帧拒因诊断证据" in (output / "README.md").read_text(encoding="utf-8")


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


def test_write_links_diagnosis_evidence_into_readme(tmp_path: Path):
    coverage = _coverage_file(
        tmp_path,
        completed=["vision-000000"],
        rejected=["vision-000021", "vision-000248", "vision-000253"],
    )
    pack = _diagnosis_pack(tmp_path)
    report = tmp_path / "report.md"
    report.write_text("# diagnosis report\n", encoding="utf-8")
    output = tmp_path / "out"
    receipt = write_directed_gap_fill_proposal_draft(
        coverage,
        output,
        diagnosis_dir=pack,
        docs_report=report,
        repo_root=tmp_path,
    )
    assert receipt["diagnosisPresent"] is True
    assert receipt["docsReportPresent"] is True
    assert receipt["matchedDiagnosisStageIds"] == [
        "vision-000021",
        "vision-000248",
    ]
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert "同帧拒因诊断证据" in readme
    assert "`vision-000021`" in readme
    assert "`vision-000248`" in readme
    assert "f8" in readme
    assert "endUs == startUs + 1" in readme
    assert "`vision-000253`" in readme
    assert "不表示缺口已清除" in readme or "不**表示缺口已清除" in readme
    links = json.loads((output / "diagnosis-links-v1.json").read_text(encoding="utf-8"))
    assert links["diagnosisPresent"] is True
    assert links["paidProviderCalls"] == 0
    assert links["readOnly"] is True
    assert_directed_gap_fill_draft_inert(
        json.loads(
            (output / "directed-gap-fill-proposal-draft-v1.json").read_text(encoding="utf-8")
        )
    )


def test_write_documents_expected_layout_when_diagnosis_missing(tmp_path: Path):
    coverage = _coverage_file(tmp_path, rejected=["vision-000021"])
    receipt = write_directed_gap_fill_proposal_draft(
        coverage,
        tmp_path / "out",
        diagnosis_dir=tmp_path / "no-diagnosis",
        docs_report=tmp_path / "missing-report.md",
        repo_root=tmp_path,
    )
    assert receipt["diagnosisPresent"] is False
    assert receipt["docsReportPresent"] is False
    assert receipt["matchedDiagnosisStageIds"] == []
    readme = (tmp_path / "out" / "README.md").read_text(encoding="utf-8")
    assert "未找到" in readme
    assert str(DEFAULT_DIAGNOSIS_DIR).replace("\\", "/") in readme.replace("\\", "/")
    assert str(DEFAULT_DOCS_REPORT).replace("\\", "/") in readme.replace("\\", "/")
    links = json.loads((tmp_path / "out" / "diagnosis-links-v1.json").read_text(encoding="utf-8"))
    assert links["expectedLayout"]["diagnosisDocument"] == "diagnosis-v1.json"


def test_build_diagnosis_evidence_links_matches_subset(tmp_path: Path):
    pack = _diagnosis_pack(tmp_path)
    report = tmp_path / "docs-report.md"
    report.write_text("report", encoding="utf-8")
    links = build_diagnosis_evidence_links(
        ["vision-000248"],
        diagnosis_dir=pack,
        docs_report=report,
        repo_root=tmp_path,
    )
    assert [row["stageId"] for row in links["matchedGaps"]] == ["vision-000248"]
    section = format_diagnosis_readme_section(links)
    assert "vision-000248" in section
    assert "f8" in section
    assert "vision-000021" not in section


def test_real_zhongkui_write_with_diagnosis_when_present(tmp_path: Path):
    coverage = Path(
        "artifacts/independent-footage-20261011/runs/"
        "5c7894aa10e94b8aa82533bd77f9871e/analysis_coverage.json"
    )
    diagnosis = Path("artifacts/coverage-gap-diagnosis-20261021")
    if not coverage.is_file() or not (diagnosis / "diagnosis-v1.json").is_file():
        pytest.skip("real coverage or diagnosis artifact absent")
    output = tmp_path / "zhongkui-draft"
    receipt = write_directed_gap_fill_proposal_draft(
        coverage,
        output,
        diagnosis_dir=diagnosis,
        docs_report=Path("docs/exec-plans/report-2026-10-21-coverage-gap-diagnosis.md"),
        repo_root=Path.cwd(),
    )
    assert receipt["targetStageIds"] == [
        "vision-000021",
        "vision-000248",
        "vision-000253",
    ]
    assert receipt["diagnosisPresent"] is True
    assert set(receipt["matchedDiagnosisStageIds"]) == {
        "vision-000021",
        "vision-000248",
        "vision-000253",
    }
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert "f8" in readme
    assert "event_frame_boundaries" in readme
    draft = json.loads(Path(str(receipt["draftPath"])).read_text(encoding="utf-8"))
    assert_directed_gap_fill_draft_inert(draft)
    assert draft["gapsCleared"] is False
    assert draft["selectsOptionB"] is False
