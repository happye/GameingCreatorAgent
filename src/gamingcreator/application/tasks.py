"""Saved task progress and conservative cost views; no media or model work."""

import json
from dataclasses import asdict
from decimal import Decimal

from gamingcreator.application.providers import CostStatus
from gamingcreator.application.storage import (
    InvocationStatus,
    RunStatus,
    RunTaskSnapshot,
    StageStatus,
    TimelineStore,
)
from gamingcreator.domain.errors import AppError, ExitCode

TASKS_VERSION = "material-tasks-v1"


def _reservation(details: str | None) -> tuple[int, Decimal] | None:
    try:
        data = json.loads(details or "{}")
        frames, value = data["inputFrames"], data["reservationCny"]
        if type(frames) is not int or frames < 0 or not isinstance(value, str):
            return None
        amount = Decimal(value)
        if not amount.is_finite() or amount <= 0:
            return None
        return frames, amount
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return None


def task_payload(snapshot: RunTaskSnapshot) -> dict[str, object]:
    run, checkpoints = snapshot.run, snapshot.checkpoints
    config = run.configuration.analysis
    completed = {row.stage_id for row in checkpoints if row.status == StageStatus.COMPLETED}
    model_started = bool(snapshot.invocations) or any(
        row.stage_id != "media" for row in checkpoints
    )
    phase = (
        "completed"
        if run.status == RunStatus.COMPLETED
        else "analysis_incomplete"
        if model_started
        else "media_prepared"
        if "media" in completed
        else "preparation_incomplete"
    )
    labels = {
        "completed": "分析已完成",
        "analysis_incomplete": "分析未完成",
        "media_prepared": "素材已保存，等待分析",
        "preparation_incomplete": "素材准备未完成",
    }
    if config.schema_version == 2:
        stride = config.window_frames - config.window_overlap
        windows = (
            1 + (max(0, snapshot.image_count - config.window_frames) + stride - 1) // stride
            if snapshot.image_count
            else 0
        )
        frames = snapshot.image_count + config.window_overlap * max(0, windows - 1)
    else:
        windows, frames = int(snapshot.image_count > 0), min(snapshot.image_count, 5)
    coverage = (
        windows <= config.max_requests and frames <= config.max_input_frames
        if "media" in completed
        else None
    )
    known = Decimal(0)
    unknown = 0
    reserved = Decimal(0)
    reservation_complete = True
    remote_requests = 0
    remote_frames = 0
    frames_complete = True
    for invocation in snapshot.invocations:
        metadata, usage = invocation.metadata, invocation.metadata.usage
        is_remote = metadata.provider == "deepseek"
        cost_unknown = (
            usage.cost_cny is None
            or usage.cost_status == CostStatus.UNVERIFIED
            or (is_remote and not metadata.price_version)
        )
        if cost_unknown:
            unknown += 1
        else:
            assert usage.cost_cny is not None
            known += usage.cost_cny
        if is_remote:
            remote_requests += 1
            reservation = _reservation(metadata.execution_details)
            if reservation is None:
                frames_complete = False
                if cost_unknown:
                    reservation_complete = False
            else:
                remote_frames += reservation[0]
                if cost_unknown:
                    reserved += reservation[1]
        elif cost_unknown:
            # No upper bound is recorded for an unpriced non-DeepSeek invocation.
            reservation_complete = False
    retry_confirmation = (
        run.status != RunStatus.COMPLETED
        and "vision" not in completed
        and any(
            item.metadata.provider == "deepseek"
            and item.stage_id not in completed
            and (
                item.status
                in (
                    InvocationStatus.RUNNING,
                    InvocationStatus.INTERRUPTED,
                    InvocationStatus.COMPLETED,
                )
                or item.metadata.usage.cost_cny is None
            )
            for item in snapshot.invocations
        )
    )
    commitment = known + reserved if reservation_complete else None
    next_action = (
        None
        if phase == "completed"
        else "prepare_media"
        if not model_started and config.schema_version == 2 and "media" not in completed
        else "analyze"
    )
    blockers = []
    if run.error_code == "storage.integrity":
        blockers.append("material_integrity")
    if retry_confirmation:
        blockers.append("explicit_retry_required")
    if config.schema_version == 1 and run.status in (
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    ):
        blockers.append("legacy_stopped")
    if coverage is False and next_action == "analyze":
        blockers.append("coverage_limit")
    if config.provider != "deepseek" or config.model != "deepseek-flash":
        blockers.append("unsupported_cli_provider")
    return {
        "runId": run.run_id,
        "runStatus": str(run.status),
        "phase": phase,
        "phaseLabel": labels[phase],
        "sourceName": run.asset.source_path.name,
        "durationUs": run.asset.duration_us,
        "sourceSha256": run.asset.sha256,
        "configHash": run.config_hash,
        "errorCode": run.error_code,
        "integrityCheck": "not_requested",
        "imageCount": snapshot.image_count,
        "audioCount": snapshot.audio_count,
        "eventCount": snapshot.event_count,
        "transcriptCount": snapshot.transcript_count,
        "configuration": {
            "analysis": asdict(config),
            "pipelineVersion": run.configuration.pipeline_version,
            "pipelineHash": run.configuration.pipeline_hash,
            "requiredStages": list(run.configuration.required_stages),
            "maxCostCny": str(run.configuration.max_cost_cny),
        },
        "progress": {
            "requiredCompleted": sum(
                stage in completed for stage in run.configuration.required_stages
            ),
            "requiredTotal": len(run.configuration.required_stages),
            "completedVisionWindows": sum(
                row.stage_id.startswith("vision-") and row.status == StageStatus.COMPLETED
                for row in checkpoints
            ),
            "plannedWindows": windows if "media" in completed else None,
            "plannedUploadFrames": frames if "media" in completed else None,
            "coverageFits": coverage,
        },
        "stages": [
            {
                "id": row.stage_id,
                "status": str(row.status),
                "attempt": row.attempt,
                "errorCode": row.error_code,
            }
            for row in checkpoints
        ],
        "cost": {
            "scope": "base_analysis",
            "knownCny": str(known),
            "unknownAttempts": unknown,
            "knownUnknownReservationCny": str(reserved),
            "unknownReservationCny": str(reserved) if reservation_complete else None,
            "reservationRecordsComplete": reservation_complete,
            "committedCny": str(commitment) if commitment is not None else None,
            "remainingCny": str(run.configuration.max_cost_cny - commitment)
            if commitment is not None
            else None,
            "remoteRequests": remote_requests,
            "remoteFrames": remote_frames if frames_complete else None,
            "billingConfirmed": False,
        },
        "nextAction": next_action,
        "continuationBlockers": blockers,
        "requiresRetryConfirmation": retry_confirmation,
        "humanQualityGate": None,
    }


async def tasks_payload(
    store: TimelineStore, *, limit: int = 100, offset: int = 0, run_id: str | None = None
) -> dict[str, object]:
    if (
        type(limit) is not int
        or not 1 <= limit <= 200
        or type(offset) is not int
        or not 0 <= offset <= 1_000_000
        or (run_id is not None and not run_id.strip())
    ):
        raise AppError(
            "input.tasks", "任务页大小须为1–200，偏移为0–1000000，任务ID不能为空。", ExitCode.INPUT
        )
    if run_id is not None and offset != 0:
        raise AppError("input.tasks", "单项任务查看不接受分页偏移。", ExitCode.INPUT)
    page = await store.load_task_page(limit=limit, offset=offset, run_id=run_id)
    return {
        "schemaVersion": TASKS_VERSION,
        "tasks": [task_payload(item) for item in page.tasks],
        "total": page.total,
        "offset": page.offset,
        "limit": page.limit,
        "hasMore": run_id is None and page.offset + len(page.tasks) < page.total,
        "ordering": "created-time-descending-then-run-id",
        "snapshotOnly": True,
    }
