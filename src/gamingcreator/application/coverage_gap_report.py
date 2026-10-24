"""Offline coverage-gap report; never clears gaps or chooses A/B/D."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from gamingcreator.application.analysis_reliability import (
    directed_gap_fill_inventory,
    load_coverage_document,
)

COVERAGE_GAP_REPORT_VERSION = "coverage-gap-report-v1"
_USER_DECISIONS = ("A_retain_gaps", "B_directed_gap_fill", "D_defer")
_DRAFT_HINT = (
    "可选本机草稿（不等于选 B、不花钱）："
    "scripts/prepare-directed-gap-fill-draft.ps1 "
    "-Coverage <analysis_coverage.json> "
    "-OutputDirectory artifacts/directed-gap-fill-draft-<date>"
)


def _as_task_rows(tasks_document: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = tasks_document.get("tasks")
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def _is_coverage_gap_row(row: Mapping[str, Any]) -> bool:
    if row.get("phase") == "analysis_coverage_gap":
        return True
    if row.get("errorCode") == "analysis.coverage_gap":
        return True
    blockers = row.get("continuationBlockers")
    if isinstance(blockers, list) and "coverage_gap" in blockers:
        return True
    return False


def resolve_run_coverage_path(project: Path, run_id: str) -> Path | None:
    """Return analysis_coverage.json under project/runs/<runId> when present."""
    candidate = project / "runs" / run_id / "analysis_coverage.json"
    return candidate if candidate.is_file() else None


def _window_summary(coverage: Mapping[str, Any]) -> dict[str, Any]:
    inventory: dict[str, Any] = directed_gap_fill_inventory(dict(coverage))
    rejected = list(inventory.get("allowedRejectedStageIds") or [])
    raw_counts = inventory.get("counts")
    counts = raw_counts if isinstance(raw_counts, Mapping) else {}
    return {
        "runId": inventory.get("runId"),
        "completedEligible": inventory.get("completedEligible") is True,
        "counts": {
            "completed": int(counts.get("completed") or 0),
            "rejected": int(counts.get("rejected") or 0),
            "unexecuted": int(counts.get("unexecuted") or 0),
        },
        "rejectedStageIds": rejected,
        "rejectedWindows": list(inventory.get("rejectedWindows") or []),
        "authorization": {
            "feeAuthorized": False,
            "sendAuthorized": False,
            "optionBChosen": False,
        },
        "inventorySchemaVersion": inventory.get("schemaVersion"),
        "proposalIdentity": inventory.get("proposalIdentity"),
    }


def _run_entry_from_task(
    row: Mapping[str, Any],
    *,
    project: Path | None,
    coverage_override: Path | None,
) -> dict[str, Any]:
    run_id = str(row.get("runId") or "")
    entry: dict[str, Any] = {
        "runId": run_id,
        "phase": row.get("phase"),
        "phaseLabel": row.get("phaseLabel"),
        "errorCode": row.get("errorCode"),
        "searchEligible": row.get("searchEligible") is True,
        "completedEligible": row.get("completedEligible") is True,
        "sourceName": row.get("sourceName"),
        "coveragePath": None,
        "coverageLoaded": False,
        "windowSummary": None,
    }
    coverage_file: Path | None = None
    if coverage_override is not None and coverage_override.is_file():
        coverage_file = coverage_override
    elif project is not None and run_id:
        coverage_file = resolve_run_coverage_path(project, run_id)
    if coverage_file is not None:
        entry["coveragePath"] = str(coverage_file.resolve())
        summary = _window_summary(load_coverage_document(coverage_file))
        entry["coverageLoaded"] = True
        entry["windowSummary"] = summary
        entry["completedEligible"] = summary["completedEligible"]
    return entry


def build_coverage_gap_report(
    tasks_document: Mapping[str, Any],
    *,
    project: str | Path | None = None,
    coverage: str | Path | None = None,
) -> dict[str, Any]:
    """Read-only report of coverage-gap runs and optional rejected windows.

    Never marks gaps cleared, never chooses A/B/D, never authorizes fees/send.
    """
    project_path = Path(project).resolve() if project is not None else None
    coverage_path = Path(coverage).resolve() if coverage is not None else None
    gap_rows = [row for row in _as_task_rows(tasks_document) if _is_coverage_gap_row(row)]
    runs = [
        _run_entry_from_task(row, project=project_path, coverage_override=coverage_path)
        for row in gap_rows
    ]

    if not runs and coverage_path is not None and coverage_path.is_file():
        summary = _window_summary(load_coverage_document(coverage_path))
        runs = [
            {
                "runId": summary.get("runId"),
                "phase": "analysis_coverage_gap",
                "phaseLabel": "分析保留覆盖缺口，未获完整资格",
                "errorCode": "analysis.coverage_gap",
                "searchEligible": False,
                "completedEligible": summary["completedEligible"],
                "sourceName": None,
                "coveragePath": str(coverage_path),
                "coverageLoaded": True,
                "windowSummary": summary,
            }
        ]

    total_rejected = 0
    for run in runs:
        window = run.get("windowSummary")
        if isinstance(window, Mapping):
            total_rejected += len(list(window.get("rejectedStageIds") or []))

    document = {
        "schemaVersion": COVERAGE_GAP_REPORT_VERSION,
        "snapshotOnly": True,
        "project": str(project_path) if project_path is not None else None,
        "coverageGapsCleared": False,
        "optionChosen": None,
        "userDecisionsPending": list(_USER_DECISIONS),
        "gapRunCount": len(runs),
        "rejectedStageCount": total_rejected,
        "runs": runs,
        "draftHint": _DRAFT_HINT,
        "notes": (
            "本报告只读汇总覆盖缺口 run 与（若有）analysis_coverage 拒窗；"
            "不清除缺口、不代选 A／B／D、不等于选 B、不授权付费发送、"
            "不宣称 F006／验收通过。"
        ),
        "featureClaims": {"F006": False, "F009": False, "F010": False},
    }
    assert_coverage_gap_report_inert(document)
    return document


def assert_coverage_gap_report_inert(document: Mapping[str, Any]) -> None:
    if document.get("schemaVersion") != COVERAGE_GAP_REPORT_VERSION:
        raise AssertionError(f"bad schemaVersion: {document.get('schemaVersion')!r}")
    if document.get("snapshotOnly") is not True:
        raise AssertionError("snapshotOnly must be True")
    if document.get("coverageGapsCleared") is not False:
        raise AssertionError("coverageGapsCleared must stay False")
    if document.get("optionChosen") is not None:
        raise AssertionError("optionChosen must stay None (do not pick A/B/D)")
    claims = document.get("featureClaims")
    if not isinstance(claims, Mapping):
        raise AssertionError("featureClaims missing")
    for feature_id in ("F006", "F009", "F010"):
        if claims.get(feature_id) is not False:
            raise AssertionError(f"featureClaims.{feature_id} must stay False")
    pending = document.get("userDecisionsPending")
    if list(pending or []) != list(_USER_DECISIONS):
        raise AssertionError("userDecisionsPending mismatch")
    for run in document.get("runs") or []:
        if not isinstance(run, Mapping):
            raise AssertionError("run entry must be object")
        if run.get("searchEligible") is True:
            raise AssertionError("coverage-gap runs must not be searchEligible")
        summary = run.get("windowSummary")
        if isinstance(summary, Mapping):
            auth = summary.get("authorization")
            if not isinstance(auth, Mapping):
                raise AssertionError("windowSummary.authorization missing")
            if auth.get("feeAuthorized") is not False or auth.get("sendAuthorized") is not False:
                raise AssertionError("authorization flags must stay false")
            if auth.get("optionBChosen") is not False:
                raise AssertionError("optionBChosen must stay false")
            if summary.get("completedEligible") is True:
                raise AssertionError("windowSummary.completedEligible must stay false")


def write_coverage_gap_report(document: Mapping[str, Any], output: Path) -> Path:
    assert_coverage_gap_report_inert(document)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2, default=str) + "\n"
    output.write_text(payload, encoding="utf-8")
    return output
