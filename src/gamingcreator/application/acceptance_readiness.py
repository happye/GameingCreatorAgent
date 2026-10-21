"""Offline acceptance readiness snapshot; never claims F006 or human-eval pass."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ACCEPTANCE_READINESS_VERSION = "acceptance-readiness-v1"

_FEATURE_IDS = ("F006", "F009", "F010")

# Offline tool statuses: never "passed".
_STATUS_NO_RUNS = "blocked_no_runs"
_STATUS_NO_SEARCHABLE = "blocked_no_searchable_run"
_STATUS_AWAITING_HUMAN = "awaiting_human_labels_and_freeze"

_STATUS_LABELS = {
    _STATUS_NO_RUNS: "项目尚无任务，不能进入正式验收",
    _STATUS_NO_SEARCHABLE: "没有可检索的已完成运行（含覆盖缺口未获资格），不能正式验收",
    _STATUS_AWAITING_HUMAN: "已有可检索运行，但仍须人工标签、冻结与绑定；本报告不宣称通过",
}

FORBIDDEN_FORMAL_STATUSES = frozenset(
    {
        "passed",
        "accepted",
        "formal_pass",
        "quality_pass",
        "human_eval_passed",
    }
)
FORBIDDEN_STATUS_LABELS = frozenset(
    {
        "passed",
        "accepted",
        "已通过",
        "验收通过",
        "正式验收通过",
        "人评通过",
        "F006通过",
        "F006 通过",
    }
)

# Substrings each workbench/workflow surface must keep checking (offline contract).
SURFACE_JS_INERT_GUARDS = (
    "acceptance-readiness-v1",
    "formalAcceptancePassed !== false",
    "humanEvalPassed !== false",
    "coverageGapsCleared !== false",
    "featureClaims.F006 !== false",
    'formalAcceptanceStatus === "passed"',
)


def _as_task_rows(tasks_document: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = tasks_document.get("tasks")
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _compact_run(task: Mapping[str, Any]) -> dict[str, object]:
    blockers = task.get("continuationBlockers")
    blocker_list = [str(x) for x in blockers] if isinstance(blockers, list) else []
    return {
        "runId": task.get("runId"),
        "phase": task.get("phase"),
        "phaseLabel": task.get("phaseLabel"),
        "runStatus": task.get("runStatus"),
        "errorCode": task.get("errorCode"),
        "searchEligible": bool(task.get("searchEligible")),
        "completedEligible": bool(task.get("completedEligible")),
        "continuationBlockers": blocker_list,
        "sourceName": task.get("sourceName"),
    }


def build_acceptance_readiness(
    tasks_document: Mapping[str, Any],
    *,
    project: str | None = None,
) -> dict[str, object]:
    """Build a read-only readiness document from material-tasks payload.

    This helper never sets qualityGate/humanEvalPassed/feature claims to True.
    Having searchable runs only yields awaiting_human_labels_and_freeze.
    """
    rows = _as_task_rows(tasks_document)
    searchable = [row for row in rows if row.get("searchEligible") is True]
    coverage_gap = [
        row
        for row in rows
        if row.get("phase") == "analysis_coverage_gap"
        or (
            isinstance(row.get("continuationBlockers"), list)
            and "coverage_gap" in row["continuationBlockers"]
        )
        or row.get("errorCode") == "analysis.coverage_gap"
    ]
    incomplete = [
        row
        for row in rows
        if row.get("phase")
        in ("analysis_incomplete", "media_prepared", "preparation_incomplete")
    ]

    if not rows:
        status = _STATUS_NO_RUNS
    elif not searchable:
        status = _STATUS_NO_SEARCHABLE
    else:
        status = _STATUS_AWAITING_HUMAN

    project_blockers: list[str] = []
    if not rows:
        project_blockers.append("no_runs")
    if not searchable:
        project_blockers.append("no_searchable_run")
    if coverage_gap:
        project_blockers.append("coverage_gap_present")
    if incomplete:
        project_blockers.append("incomplete_runs_present")
    # Always required for formal path; offline snapshot cannot clear these.
    project_blockers.extend(
        (
            "human_labels_required",
            "freeze_and_bind_required",
            "feature_claims_remain_false",
        )
    )

    document: dict[str, object] = {
        "schemaVersion": ACCEPTANCE_READINESS_VERSION,
        "snapshotOnly": True,
        "project": project,
        "tasksSchemaVersion": tasks_document.get("schemaVersion"),
        "taskTotal": tasks_document.get("total", len(rows)),
        "taskRowsInSnapshot": len(rows),
        "counts": {
            "searchableRuns": len(searchable),
            "coverageGapRuns": len(coverage_gap),
            "incompleteRuns": len(incomplete),
            "otherRuns": max(
                0, len(rows) - len(searchable) - len(coverage_gap) - len(incomplete)
            ),
        },
        "formalAcceptanceStatus": status,
        "formalAcceptanceStatusLabel": _STATUS_LABELS[status],
        "formalAcceptancePassed": False,
        "qualityGate": None,
        "humanEvalPassed": False,
        "featureClaims": {feature_id: False for feature_id in _FEATURE_IDS},
        "projectBlockers": project_blockers,
        "searchableRunIds": [row.get("runId") for row in searchable],
        "coverageGapRunIds": [row.get("runId") for row in coverage_gap],
        "runs": [_compact_run(row) for row in rows],
        "notes": (
            "本报告只读汇总任务资格与阻断，不能代替人工评分、冻结评测或宣称 F006／F009／F010 通过。"
            "有可检索运行时状态仅为 awaiting_human_labels_and_freeze；永不输出 passed。"
        ),
        "coverageGapsCleared": False,
        "userDecisionsPending": ["A_or_B_or_D_coverage_gap"],
    }
    assert_acceptance_readiness_inert(document)
    return document


def assert_acceptance_readiness_inert(document: Mapping[str, Any]) -> None:
    """Guard: readiness snapshot must never claim formal pass or feature true."""
    if document.get("schemaVersion") != ACCEPTANCE_READINESS_VERSION:
        raise AssertionError("acceptance readiness schemaVersion mismatch")
    if document.get("formalAcceptancePassed") is not False:
        raise AssertionError("formalAcceptancePassed must stay False")
    if document.get("humanEvalPassed") is not False:
        raise AssertionError("humanEvalPassed must stay False")
    if document.get("qualityGate") is True:
        raise AssertionError("qualityGate must not be True in offline readiness")
    if document.get("coverageGapsCleared") is not False:
        raise AssertionError("coverageGapsCleared must stay False")
    claims = document.get("featureClaims")
    if not isinstance(claims, Mapping):
        raise AssertionError("featureClaims missing")
    for feature_id in _FEATURE_IDS:
        if claims.get(feature_id) is not False:
            raise AssertionError(f"{feature_id} claim must stay False")
    status = document.get("formalAcceptanceStatus")
    if status not in _STATUS_LABELS:
        raise AssertionError(f"unknown formalAcceptanceStatus: {status!r}")
    if status in FORBIDDEN_FORMAL_STATUSES:
        raise AssertionError(f"forbidden formalAcceptanceStatus: {status!r}")
    label = document.get("formalAcceptanceStatusLabel")
    if label in FORBIDDEN_STATUS_LABELS or label == "passed":
        raise AssertionError(f"forbidden formalAcceptanceStatusLabel: {label!r}")
    if document.get("snapshotOnly") is not True:
        raise AssertionError("snapshotOnly must be True")


def write_acceptance_readiness(document: Mapping[str, Any], output: Path) -> Path:
    """Write readiness JSON; re-checks inert claims before disk write."""
    assert_acceptance_readiness_inert(document)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2, default=str) + "\n"
    output.write_text(payload, encoding="utf-8")
    return output


def surface_js_inert_guards() -> tuple[str, ...]:
    """Guards that static workbench/workflow JS must keep for inert readiness."""
    return SURFACE_JS_INERT_GUARDS
