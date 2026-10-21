"""Explicit scheduling identity and conservative, persisted content rejection checks."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import cast

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.providers import CostStatus
from gamingcreator.application.storage import (
    InvocationStatus,
    StageCheckpoint,
    StageStatus,
    StoredInvocation,
    StoredRun,
    TimelineStore,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.time import SourceInstant

POLICY = "isolate-schema-v1"
POLICY_STAGE = "policy-isolate-schema-v1"
CONTENT_ERRORS = frozenset(
    {
        "event_temporal_evidence",
        "event_frame_boundaries",
        "event_static_evidence",
        "event_boundary_evidence",
        "event_evidence_order",
        "evidence_outside_range",
        "evidence_unknown",
        "event_window_range",
        "time_range",
    }
)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def policy_hash(run: StoredRun) -> str:
    return digest(
        {
            "policy": POLICY,
            "runId": run.run_id,
            "sourceSha256": run.asset.sha256,
            "configHash": run.config_hash,
            "pipelineHash": run.configuration.pipeline_hash,
        }
    )


def validate_policy(
    run: StoredRun, checkpoints: tuple[StageCheckpoint, ...], selected: str, retry: bool
) -> None:
    markers = [row for row in checkpoints if row.stage_id.startswith("policy-")]
    expected = policy_hash(run)
    if (
        selected not in ("stop-v1", POLICY)
        or (selected == POLICY and (retry or run.configuration.analysis.schema_version != 2))
        or any(
            row.stage_id != POLICY_STAGE
            or selected != POLICY
            or row.status != StageStatus.COMPLETED
            or row.input_hash != expected
            or row.output_hash != expected
            or row.error_code is not None
            for row in markers
        )
    ):
        raise AppError(
            "input.window_failure_policy",
            "窗口失败策略身份不一致，不能续跑。",
            ExitCode.INPUT,
            run.run_id,
        )


async def rejected_windows(
    store: TimelineStore,
    run: StoredRun,
    windows: tuple[tuple[EvidenceReference, ...], ...],
    *,
    strict: bool = True,
) -> frozenset[str]:
    checkpoints = {row.stage_id: row for row in await store.load_checkpoints(run.run_id)}
    invocations = await store.load_invocations(run.run_id)
    rejected = set()
    config = run.configuration.analysis
    for index, window in enumerate(windows):
        stage = f"vision-{index:06d}"
        row = checkpoints.get(stage)
        if row is None:
            continue
        if row.input_hash != digest([item.evidence_id for item in window]):
            if strict:
                raise AppError(
                    "storage.checkpoint_identity",
                    "窗口检查点输入身份不一致。",
                    ExitCode.STORAGE,
                    run.run_id,
                )
            continue
        attempts = [item for item in invocations if item.stage_id == stage]
        if row.status == StageStatus.COMPLETED:
            if strict:
                _require_success(run, window, stage, tuple(attempts), invocations)
            continue
        if not attempts:
            if strict:
                raise AppError(
                    "analysis.isolation_ineligible",
                    "旧窗口缺少结束调用证据，不能自动重发。",
                    ExitCode.PROVIDER,
                    run.run_id,
                )
            continue
        expected_ids = [item.evidence_id for item in window]
        safe = row.input_hash == digest(expected_ids) and row.error_code in (
            None,
            "provider.schema",
            "storage.interrupted",
        )
        logical_ids = {item.logical_request_id for item in attempts}
        safe = (
            safe
            and len(logical_ids) == 1
            and not any(
                item.logical_request_id in logical_ids and item.stage_id != stage
                for item in invocations
            )
        )
        for item in attempts:
            metadata = item.metadata
            try:
                details = json.loads(metadata.execution_details or "{}")
            except (ValueError, TypeError):
                details = {}
            safe = safe and isinstance(details, dict)
            if not isinstance(details, dict):
                details = {}
            cost = metadata.usage.cost_cny
            safe = (
                safe
                and item.run_id == run.run_id
                and item.status == InvocationStatus.FAILED
                and item.error_code == "provider.schema"
                and metadata.provider == config.provider
                and metadata.requested_model == config.model
                and metadata.actual_model == config.model
                and bool(metadata.request_id)
                and bool(re.fullmatch(r"[a-f0-9]{32}", item.logical_request_id))
                and metadata.prompt_version == config.vision_prompt_version
                and metadata.schema_version
                == (
                    "temporal-actions-v1"
                    if config.vision_prompt_version
                    in ("phase0-vision-v4", "phase0-vision-v5", "phase0-vision-v6")
                    else "semantic-events-v1"
                )
                and metadata.price_version == config.price_version
                and cost is not None
                and cost.is_finite()
                and cost >= 0
                and metadata.usage.cost_status != CostStatus.UNVERIFIED
                and metadata.usage.input_tokens is not None
                and metadata.usage.output_tokens is not None
                and details.get("evidenceIds") == expected_ids
                and details.get("inputFrames") == len(window)
                and details.get("schemaError") in CONTENT_ERRORS
            )
        if not safe:
            if strict:
                raise AppError(
                    "analysis.isolation_ineligible",
                    "旧窗口调用不能安全隔离，已停止且不会重发。",
                    ExitCode.PROVIDER,
                    run.run_id,
                )
            continue
        rejected.add(stage)
    return frozenset(rejected)


def _successful_identity(
    item: StoredInvocation, config: AnalysisConfig, window: tuple[EvidenceReference, ...]
) -> bool:
    metadata = item.metadata
    try:
        details = json.loads(metadata.execution_details or "{}")
    except (TypeError, ValueError):
        return False
    cost = metadata.usage.cost_cny
    return (
        isinstance(details, dict)
        and item.status == InvocationStatus.COMPLETED
        and item.error_code is None
        and metadata.provider == config.provider
        and metadata.requested_model == config.model
        and metadata.actual_model == config.model
        and bool(metadata.request_id)
        and bool(re.fullmatch(r"[a-f0-9]{32}", item.logical_request_id))
        and metadata.prompt_version == config.vision_prompt_version
        and metadata.schema_version
        == (
            "temporal-actions-v1"
            if config.vision_prompt_version
            in ("phase0-vision-v4", "phase0-vision-v5", "phase0-vision-v6")
            else "semantic-events-v1"
        )
        and metadata.price_version == config.price_version
        and cost is not None
        and cost.is_finite()
        and cost >= 0
        and metadata.usage.cost_status != CostStatus.UNVERIFIED
        and metadata.usage.input_tokens is not None
        and metadata.usage.output_tokens is not None
        and metadata.usage.cached_input_tokens is not None
        and details.get("evidenceIds") == [item.evidence_id for item in window]
        and details.get("inputFrames") == len(window)
        and "schemaError" not in details
    )


def _require_success(
    run: StoredRun,
    window: tuple[EvidenceReference, ...],
    stage: str,
    attempts: tuple[StoredInvocation, ...],
    all_attempts: tuple[StoredInvocation, ...],
) -> None:
    if (
        len(attempts) != 1
        or not _successful_identity(attempts[0], run.configuration.analysis, window)
        or attempts[0].run_id != run.run_id
        or attempts[0].stage_id != stage
        or any(
            item.logical_request_id == attempts[0].logical_request_id and item.stage_id != stage
            for item in all_attempts
        )
    ):
        raise AppError(
            "analysis.isolation_ineligible",
            "成功窗口的费用或模型身份未确认，已停止且不会继续发送。",
            ExitCode.PROVIDER,
            run.run_id,
        )


async def verify_successful_window(
    store: TimelineStore, run: StoredRun, window: tuple[EvidenceReference, ...], stage: str
) -> None:
    attempts = await store.load_invocations(run.run_id)
    _require_success(
        run, window, stage, tuple(item for item in attempts if item.stage_id == stage), attempts
    )


async def write_coverage(
    store: TimelineStore,
    run: StoredRun,
    windows: tuple[tuple[EvidenceReference, ...], ...],
    project: Path,
) -> None:
    rows = {row.stage_id: row for row in await store.load_checkpoints(run.run_id)}
    invocations = await store.load_invocations(run.run_id)
    rejected = await rejected_windows(store, run, windows, strict=False)
    entries = []
    for index, window in enumerate(windows):
        stage = f"vision-{index:06d}"
        row = rows.get(stage)
        status = (
            "completed"
            if row and row.status == StageStatus.COMPLETED
            else "rejected"
            if stage in rejected
            else "unexecuted"
        )
        verified = False
        if (
            status == "completed"
            and row is not None
            and row.input_hash == digest([item.evidence_id for item in window])
        ):
            try:
                _require_success(
                    run,
                    window,
                    stage,
                    tuple(item for item in invocations if item.stage_id == stage),
                    invocations,
                )
                verified = True
            except AppError:
                pass
        entries.append(
            {
                "stageId": stage,
                "status": status,
                "invocationVerified": verified,
                "attempted": any(item.stage_id == stage for item in invocations),
                "checkpointStatus": None if row is None else row.status.value,
                "stopCode": None if row is None else row.error_code,
                "startUs": cast(SourceInstant, window[0].source_time).time_us,
                "endUs": cast(SourceInstant, window[-1].source_time).time_us + 1,
            }
        )
    document = {
        "schemaVersion": 1,
        "runId": run.run_id,
        "sourceSha256": run.asset.sha256,
        "configHash": run.config_hash,
        "pipelineHash": run.configuration.pipeline_hash,
        "policyVersion": POLICY,
        "policyHash": policy_hash(run),
        "completedEligible": bool(entries)
        and all(item["status"] == "completed" and item["invocationVerified"] for item in entries),
        "windows": entries,
    }
    path = project / "runs" / run.run_id / "analysis_coverage.json"
    temporary = path.with_suffix(".json.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(json.dumps(document, ensure_ascii=True, indent=2).encode())
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except OSError:
        raise AppError(
            "storage.coverage", "覆盖记录保存失败，任务仍未完成。", ExitCode.STORAGE, run.run_id
        ) from None


# ---------------------------------------------------------------------------
# Directed gap-fill (future option B) — offline contract only.
# isolate-schema-v1 never re-sends rejected windows; resume only continues
# unexecuted stages. A future paid gap-fill MUST be a separate proposal
# identity (DIRECTED_GAP_FILL_PROPOSAL), not resume under POLICY. These
# helpers draft / validate target stage sets from analysis_coverage.json
# without authorizing fees or calling a provider.
# ---------------------------------------------------------------------------

DIRECTED_GAP_FILL_PROPOSAL = "directed-gap-fill-v1"
_COVERAGE_STATUSES = frozenset({"completed", "rejected", "unexecuted"})


def load_coverage_document(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise AppError(
            "input.coverage_document",
            "覆盖清单无法读取或不是合法 JSON。",
            ExitCode.INPUT,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            "input.coverage_document",
            "覆盖清单根节点必须是对象。",
            ExitCode.INPUT,
        )
    windows = payload.get("windows")
    if not isinstance(windows, list) or not windows:
        raise AppError(
            "input.coverage_document",
            "覆盖清单缺少 windows 数组。",
            ExitCode.INPUT,
        )
    for row in windows:
        if not isinstance(row, dict):
            raise AppError(
                "input.coverage_document",
                "覆盖清单窗口项必须是对象。",
                ExitCode.INPUT,
            )
        stage = row.get("stageId")
        status = row.get("status")
        if not isinstance(stage, str) or not stage.startswith("vision-"):
            raise AppError(
                "input.coverage_document",
                "覆盖清单 stageId 非法。",
                ExitCode.INPUT,
            )
        if status not in _COVERAGE_STATUSES:
            raise AppError(
                "input.coverage_document",
                f"覆盖清单 status 非法：{status!r}。",
                ExitCode.INPUT,
            )
    return payload


def coverage_stage_sets(
    coverage: dict[str, object],
) -> dict[str, frozenset[str]]:
    windows = cast(list[object], coverage["windows"])
    buckets: dict[str, set[str]] = {
        "completed": set(),
        "rejected": set(),
        "unexecuted": set(),
    }
    for row in windows:
        item = cast(dict[str, object], row)
        stage = cast(str, item["stageId"])
        status = cast(str, item["status"])
        if (
            stage in buckets["completed"]
            or stage in buckets["rejected"]
            or stage in buckets["unexecuted"]
        ):
            raise AppError(
                "input.coverage_document",
                f"覆盖清单重复 stageId：{stage}。",
                ExitCode.INPUT,
            )
        buckets[status].add(stage)
    return {key: frozenset(value) for key, value in buckets.items()}


def directed_gap_fill_inventory(coverage: dict[str, object]) -> dict[str, object]:
    """Build a frozen offline inventory for a future directed gap-fill proposal.

    Does not authorize sending, does not change completedEligible, and does not
    claim the three real gaps are cleared.
    """
    sets = coverage_stage_sets(coverage)
    windows = cast(list[object], coverage["windows"])
    rejected_rows = []
    for row in windows:
        item = cast(dict[str, object], row)
        if item["status"] != "rejected":
            continue
        rejected_rows.append(
            {
                "stageId": item["stageId"],
                "stopCode": item.get("stopCode"),
                "startUs": item.get("startUs"),
                "endUs": item.get("endUs"),
                "checkpointStatus": item.get("checkpointStatus"),
                "attempted": item.get("attempted"),
                "invocationVerified": item.get("invocationVerified"),
            }
        )
    return {
        "schemaVersion": 1,
        "proposalIdentity": DIRECTED_GAP_FILL_PROPOSAL,
        "notIsolateResume": True,
        "isolatePolicy": POLICY,
        "runId": coverage.get("runId"),
        "sourceSha256": coverage.get("sourceSha256"),
        "configHash": coverage.get("configHash"),
        "pipelineHash": coverage.get("pipelineHash"),
        "coveragePolicyVersion": coverage.get("policyVersion"),
        "coveragePolicyHash": coverage.get("policyHash"),
        "completedEligible": coverage.get("completedEligible"),
        "counts": {
            "completed": len(sets["completed"]),
            "rejected": len(sets["rejected"]),
            "unexecuted": len(sets["unexecuted"]),
        },
        "forbiddenCompletedStageIds": sorted(sets["completed"]),
        "allowedRejectedStageIds": sorted(sets["rejected"]),
        "rejectedWindows": rejected_rows,
        "rules": {
            "targetsMustBeRejectedOnly": True,
            "mustNotResendCompleted": True,
            "mustNotIncludeUnexecuted": True,
            "requiresNewFeeProposalAndAuth": True,
            "oldIsolateResumeDoesNotAuthorizeGapFill": True,
            "sameFrameContractRemainsEnforced": True,
        },
        "authorization": {
            "feeAuthorized": False,
            "sendAuthorized": False,
            "note": (
                "Inventory only. Option B still needs a frozen fee proposal "
                "and explicit user approval."
            ),
        },
    }


def validate_directed_gap_fill_targets(
    coverage: dict[str, object], proposed_stage_ids: object
) -> frozenset[str]:
    """Refuse any target set that would touch completed or unexecuted windows."""
    if not isinstance(proposed_stage_ids, (list, tuple, set, frozenset)):
        raise AppError(
            "input.directed_gap_fill_targets",
            "定向补窗目标必须是 stageId 列表。",
            ExitCode.INPUT,
        )
    proposed = list(proposed_stage_ids)
    if not proposed:
        raise AppError(
            "input.directed_gap_fill_targets",
            "定向补窗目标不能为空。",
            ExitCode.INPUT,
        )
    if any(not isinstance(item, str) for item in proposed):
        raise AppError(
            "input.directed_gap_fill_targets",
            "定向补窗目标必须全是字符串 stageId。",
            ExitCode.INPUT,
        )
    unique = frozenset(proposed)
    if len(unique) != len(proposed):
        raise AppError(
            "input.directed_gap_fill_targets",
            "定向补窗目标含重复 stageId。",
            ExitCode.INPUT,
        )
    sets = coverage_stage_sets(coverage)
    known = sets["completed"] | sets["rejected"] | sets["unexecuted"]
    unknown = sorted(unique - known)
    if unknown:
        raise AppError(
            "input.directed_gap_fill_targets",
            "定向补窗目标含覆盖清单外的 stageId。",
            ExitCode.INPUT,
        )
    completed_hits = sorted(unique & sets["completed"])
    if completed_hits:
        raise AppError(
            "input.directed_gap_fill_targets",
            "定向补窗禁止重发已成功窗口。",
            ExitCode.INPUT,
        )
    unexecuted_hits = sorted(unique & sets["unexecuted"])
    if unexecuted_hits:
        raise AppError(
            "input.directed_gap_fill_targets",
            "定向补窗不得把未执行窗口塞进补窗目标；未执行仍走 isolate 续跑。",
            ExitCode.INPUT,
        )
    not_rejected = sorted(unique - sets["rejected"])
    if not_rejected:
        raise AppError(
            "input.directed_gap_fill_targets",
            "定向补窗目标必须全部是 rejected 窗口。",
            ExitCode.INPUT,
        )
    return unique
