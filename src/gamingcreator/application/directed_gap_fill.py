"""Offline directed gap-fill proposal draft template (never authorizes send)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import cast

from gamingcreator.application.analysis_reliability import (
    DIRECTED_GAP_FILL_PROPOSAL,
    POLICY,
    digest,
    directed_gap_fill_inventory,
    validate_directed_gap_fill_targets,
)
from gamingcreator.domain.errors import AppError, ExitCode

DRAFT_SCHEMA = "directed-gap-fill-proposal-draft-v1"


def _optional_cost(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        text = format(value, "f")
    elif isinstance(value, (int, float, str)):
        text = str(value).strip()
    else:
        raise AppError(
            "input.directed_gap_fill_draft",
            "费用上限必须是数字或数字字符串，或留空。",
            ExitCode.INPUT,
        )
    if not text:
        return None
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(
            "input.directed_gap_fill_draft",
            "费用上限不是合法十进制数字。",
            ExitCode.INPUT,
        ) from exc
    if amount <= 0 or not amount.is_finite():
        raise AppError(
            "input.directed_gap_fill_draft",
            "费用上限必须是大于 0 的有限金额。",
            ExitCode.INPUT,
        )
    return format(amount, "f")


def build_directed_gap_fill_proposal_draft(
    coverage: dict[str, object],
    *,
    proposed_stage_ids: object | None = None,
    maximum_additional_cost_cny: object | None = None,
    purpose: str | None = None,
) -> dict[str, object]:
    """Build an unfrozen, non-authorizing draft for a future option-B proposal.

    Does not choose option B, does not mark fees authorized, and does not claim
    coverage gaps are cleared. Target stages are validated against coverage.
    """
    inventory = directed_gap_fill_inventory(coverage)
    allowed = cast(list[str], inventory["allowedRejectedStageIds"])
    if proposed_stage_ids is None:
        targets = list(allowed)
    else:
        targets = sorted(validate_directed_gap_fill_targets(coverage, proposed_stage_ids))
    if not targets:
        raise AppError(
            "input.directed_gap_fill_draft",
            "覆盖清单没有 rejected 窗口，不能起草定向补窗提案。",
            ExitCode.INPUT,
        )
    cost_text = _optional_cost(maximum_additional_cost_cny)
    rejected_rows = [
        row
        for row in cast(list[object], inventory["rejectedWindows"])
        if cast(dict[str, object], row)["stageId"] in set(targets)
    ]
    draft: dict[str, object] = {
        "schemaVersion": DRAFT_SCHEMA,
        "proposalIdentity": DIRECTED_GAP_FILL_PROPOSAL,
        "draftStatus": "template-unfrozen",
        "selectsOptionB": False,
        "notIsolateResume": True,
        "isolatePolicy": POLICY,
        "purpose": purpose
        or (
            "离线定向补窗提案草稿：仅列出可补的 rejected 窗口与合同边界；"
            "未选择选项 B，未授权费用或发图。"
        ),
        "runId": coverage.get("runId"),
        "sourceSha256": coverage.get("sourceSha256"),
        "configHash": coverage.get("configHash"),
        "pipelineHash": coverage.get("pipelineHash"),
        "coveragePolicyVersion": coverage.get("policyVersion"),
        "coveragePolicyHash": coverage.get("policyHash"),
        "coverageCompletedEligible": coverage.get("completedEligible"),
        "inventoryCounts": inventory["counts"],
        "targets": {
            "stageIds": targets,
            "windowCount": len(targets),
            "windows": rejected_rows,
        },
        "forbidden": {
            "completedStageIds": inventory["forbiddenCompletedStageIds"],
            "mustNotResendCompleted": True,
            "mustNotIncludeUnexecuted": True,
            "mustNotReuseOldV2OrBalance": True,
            "mustNotRelaxSameFrameContract": True,
        },
        "limits": {
            "maximumAdditionalCostCny": cost_text,
            "costCeilingFilled": cost_text is not None,
            "fullCompletionNotGuaranteed": True,
            "noAutomaticBudgetIncrease": True,
            "note": (
                "金额仅草稿占位。冻结并请用户批准前必须填入明确新增费用上限；"
                "旧续跑余额与旧 v2 授权无效。"
            ),
        },
        "authorization": {
            "executionAuthorized": False,
            "feeAuthorized": False,
            "sendAuthorized": False,
            "optionBChosenByUser": False,
            "requiresNewExplicitFeeAndImageApproval": True,
            "draftDoesNotAuthorizeAnything": True,
        },
        "qualityGate": None,
        "gapsCleared": False,
        "rules": inventory["rules"],
    }
    draft["draftContentSha256"] = draft_content_sha256(draft)
    return draft


def draft_content_sha256(draft: dict[str, object]) -> str:
    """Stable hash of draft fields excluding the hash field itself."""
    payload = {key: value for key, value in draft.items() if key != "draftContentSha256"}
    return digest(payload)


def assert_directed_gap_fill_draft_inert(draft: dict[str, object]) -> None:
    """Refuse any draft that looks executable or claims option B / cleared gaps."""
    if not isinstance(draft, dict):
        raise AppError(
            "input.directed_gap_fill_draft",
            "定向补窗草稿必须是对象。",
            ExitCode.INPUT,
        )
    if draft.get("schemaVersion") != DRAFT_SCHEMA:
        raise AppError(
            "input.directed_gap_fill_draft",
            "定向补窗草稿 schemaVersion 不匹配。",
            ExitCode.INPUT,
        )
    if draft.get("proposalIdentity") != DIRECTED_GAP_FILL_PROPOSAL:
        raise AppError(
            "input.directed_gap_fill_draft",
            "定向补窗草稿提案身份不匹配。",
            ExitCode.INPUT,
        )
    auth = draft.get("authorization")
    if not isinstance(auth, dict):
        raise AppError(
            "input.directed_gap_fill_draft",
            "定向补窗草稿缺少 authorization。",
            ExitCode.INPUT,
        )
    for key in (
        "executionAuthorized",
        "feeAuthorized",
        "sendAuthorized",
        "optionBChosenByUser",
    ):
        if auth.get(key) is not False:
            raise AppError(
                "input.directed_gap_fill_draft",
                "定向补窗草稿不得带有任何授权或已选 B 标记。",
                ExitCode.INPUT,
            )
    if draft.get("selectsOptionB") is not False:
        raise AppError(
            "input.directed_gap_fill_draft",
            "定向补窗草稿不得代选选项 B。",
            ExitCode.INPUT,
        )
    if draft.get("gapsCleared") is not False:
        raise AppError(
            "input.directed_gap_fill_draft",
            "定向补窗草稿不得声称缺口已清除。",
            ExitCode.INPUT,
        )
    if draft.get("draftStatus") != "template-unfrozen":
        raise AppError(
            "input.directed_gap_fill_draft",
            "本助手只产出 template-unfrozen 草稿。",
            ExitCode.INPUT,
        )
    expected = draft_content_sha256(draft)
    if draft.get("draftContentSha256") != expected:
        raise AppError(
            "input.directed_gap_fill_draft",
            "定向补窗草稿内容哈希不一致。",
            ExitCode.INPUT,
        )
