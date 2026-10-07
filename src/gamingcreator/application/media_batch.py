"""Sequential media-only batches with preallocated run IDs and durable checkpoints."""

import asyncio
import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import cast

from gamingcreator.application.analysis import (
    MediaPreparationOutcome,
    prepare_media,
    vision_windows,
)
from gamingcreator.application.inputs import AnalysisConfig, PreparedAnalyze
from gamingcreator.application.media import MediaProcessor
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import RunStatus, StageStatus, StoredRun, TimelineStore
from gamingcreator.domain.errors import AppError, ExitCode

MAX_BATCH_ITEMS = 100
MAX_BATCH_INPUT_BYTES = 1_048_576
ITEM_STATES = {
    "pending",
    "running",
    "prepared",
    "coverage_blocked",
    "analysis_started",
    "failed",
    "cancelled",
}


@dataclass(frozen=True, slots=True)
class MediaBatchItem:
    item_id: str
    video: Path
    run_id: str


@dataclass(frozen=True, slots=True)
class MediaBatchPlan:
    batch_id: str
    project: Path
    config: AnalysisConfig
    max_cost_cny: Decimal
    timeout_seconds: float
    items: tuple[MediaBatchItem, ...]


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("清单含重复JSON字段。")
        result[key] = value
    return result


def loads_batch_input(data: bytes) -> tuple[tuple[str, str], ...]:
    if len(data) > MAX_BATCH_INPUT_BYTES:
        raise ValueError("素材清单不能超过1MiB。")
    raw = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs)
    if (
        type(raw) is not dict
        or set(raw) != {"schemaVersion", "items"}
        or raw["schemaVersion"] != "media-batch-input-v1"
    ):
        raise ValueError("素材清单版本／字段不同。")
    if type(raw["items"]) is not list or not 1 <= len(raw["items"]) <= MAX_BATCH_ITEMS:
        raise ValueError("每批须有1–100个素材。")
    values = []
    for row in raw["items"]:
        if type(row) is not dict or set(row) != {"id", "path"}:
            raise ValueError("素材须仅填写id和path。")
        identifier, path = row["id"], row["path"]
        if (
            any(type(value) is not str or not value.strip() for value in (identifier, path))
            or len(identifier) > 120
            or len(path) > 16384
            or "\0" in path
        ):
            raise ValueError("素材身份／路径须为有界文字。")
        values.append((identifier, path))
    if len({identifier for identifier, _ in values}) != len(values):
        raise ValueError("素材身份不能重复。")
    return tuple(values)


def initial_batch_state(plan: MediaBatchPlan, plan_sha256: str) -> dict[str, object]:
    return {
        "schemaVersion": "media-batch-state-v1",
        "batchId": plan.batch_id,
        "planSha256": plan_sha256,
        "status": "pending",
        "exitCode": 0,
        "items": [
            {
                "id": item.item_id,
                "runId": item.run_id,
                "status": "pending",
                "attempts": 0,
                "sourceSha256": None,
                "result": None,
                "errorCode": None,
                "message": None,
                "verifiedThisInvocation": False,
            }
            for item in plan.items
        ],
    }


def validate_batch_state(state: dict[str, object], plan: MediaBatchPlan, plan_sha256: str) -> None:
    expected = initial_batch_state(plan, plan_sha256)
    if set(state) != set(expected) or any(
        state[key] != expected[key] for key in ("schemaVersion", "batchId", "planSha256")
    ):
        raise ValueError("批次状态的固定依据不同。")
    if (
        state["status"] not in ("pending", "running", "finished", "partial", "stopped", "cancelled")
        or type(state["exitCode"]) is not int
        or state["exitCode"] not in tuple(ExitCode)
    ):
        raise ValueError("批次状态／退出码无效。")
    rows = state["items"]
    if type(rows) is not list or len(rows) != len(plan.items):
        raise ValueError("批次状态素材不完整。")
    for row, original in zip(rows, cast(list[dict[str, object]], expected["items"]), strict=True):
        if (
            type(row) is not dict
            or set(row) != set(original)
            or row["id"] != original["id"]
            or row["runId"] != original["runId"]
        ):
            raise ValueError("批次状态的素材／运行身份改变。")
        if (
            row["status"] not in ITEM_STATES
            or type(row["attempts"]) is not int
            or row["attempts"] < 0
            or type(row["verifiedThisInvocation"]) is not bool
        ):
            raise ValueError("素材状态／次数无效。")
        digest = row["sourceSha256"]
        if digest is not None and (
            type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("原素材SHA无效。")
        if row["result"] is not None and type(row["result"]) is not dict:
            raise ValueError("素材准备结果无效。")
        if any(
            value is not None and (type(value) is not str or not value.strip() or len(value) > 4096)
            for value in (row["errorCode"], row["message"])
        ):
            raise ValueError("素材错误说明无效。")


def _payload(
    plan: MediaBatchPlan, item: MediaBatchItem, stored: StoredRun, result: MediaPreparationOutcome
) -> dict[str, object]:
    return {
        "runId": stored.run_id,
        "mediaId": stored.asset.media_id,
        "runStatus": str(stored.status),
        "sourceSha256": stored.asset.sha256,
        "durationUs": stored.asset.duration_us,
        "configHash": stored.config_hash,
        "savedMaxCostCny": str(stored.configuration.max_cost_cny),
        "imageCount": result.image_count,
        "audioAvailable": result.audio_available,
        "plannedWindows": result.window_count,
        "plannedUploadFrames": result.upload_frame_count,
        "coverageFits": result.coverage_fits,
        "modelInvocations": 0,
        "nextCommand": [
            "gamingcreator",
            "analyze",
            str(item.video),
            "--project",
            str(plan.project),
            "--resume",
            item.run_id,
        ]
        if result.coverage_fits
        else None,
    }


async def run_media_batch(
    plan: MediaBatchPlan,
    state: dict[str, object],
    media: MediaProcessor,
    store: TimelineStore,
    checkpoint: Callable[[dict[str, object]], None],
    *,
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Never construct a model/ledger; resume only these fixed allocated runs."""
    timeout = plan.timeout_seconds if timeout_seconds is None else timeout_seconds
    if type(timeout) not in (int, float) or not isfinite(timeout) or timeout <= 0:
        raise AppError("input.media_batch", "每素材期限须为有限正数。", ExitCode.INPUT)
    validate_batch_state(state, plan, cast(str, state["planSha256"]))
    state = deepcopy(state)
    rows = cast(list[dict[str, object]], state["items"])
    for row in rows:
        row["verifiedThisInvocation"] = False
    state["status"], state["exitCode"] = "running", 0
    checkpoint(deepcopy(state))
    began = perf_counter()
    reused = 0
    for item, row in zip(plan.items, rows, strict=True):
        item_started = perf_counter()

        def remaining(item_started: float = item_started) -> float:
            value = timeout - (perf_counter() - item_started)
            if value <= 0:
                raise AppError("media.timeout", "本素材准备达到时间上限。", ExitCode.INPUT)
            return value

        previous = row["status"]
        row.update(status="running", result=None, errorCode=None, message=None)
        checkpoint(deepcopy(state))
        try:
            try:
                stored = await store.load_run(item.run_id)
            except AppError as error:
                if error.code != "storage.run_missing" or previous in (
                    "prepared",
                    "coverage_blocked",
                    "analysis_started",
                ):
                    raise
                stored = None
            if stored is not None:
                if (
                    stored.asset.source_path != item.video
                    or stored.configuration.analysis != plan.config
                    or stored.configuration.max_cost_cny != plan.max_cost_cny
                    or row["sourceSha256"] not in (None, stored.asset.sha256)
                ):
                    raise AppError(
                        "storage.batch_identity",
                        "批次任务的原素材／配置／限额不同。",
                        ExitCode.STORAGE,
                    )
                row["sourceSha256"] = stored.asset.sha256
                stages = await store.load_checkpoints(item.run_id)
                if (
                    stored.status == RunStatus.COMPLETED
                    or any(stage.stage_id != "media" for stage in stages)
                    or await store.load_invocations(item.run_id)
                ):
                    row.update(
                        status="analysis_started",
                        result={
                            "runId": stored.run_id,
                            "runStatus": str(stored.status),
                            "mediaId": stored.asset.media_id,
                            "nextCommand": None,
                        },
                        message="任务已进入模型分析，批次只查看状态。",
                        verifiedThisInvocation=True,
                    )
                    checkpoint(deepcopy(state))
                    continue
                if stored.status == RunStatus.PENDING and any(
                    stage.stage_id == "media" and stage.status == StageStatus.COMPLETED
                    for stage in stages
                ):
                    bundle = await store.load_media_bundle(item.run_id)
                    windows = vision_windows(bundle, plan.config)
                    frames = sum(len(window) for window in windows)
                    result = MediaPreparationOutcome(
                        item.run_id,
                        stored.asset.media_id,
                        len(bundle.images),
                        bundle.audio is not None,
                        len(windows),
                        frames,
                        len(windows) <= plan.config.max_requests
                        and frames <= plan.config.max_input_frames,
                    )
                    reused += 1
                else:
                    row["attempts"] = cast(int, row["attempts"]) + 1
                    checkpoint(deepcopy(state))
                    result = await prepare_media(
                        PreparedAnalyze(item.video, plan.project, None, None, item.run_id),
                        media,
                        store,
                        plan.project,
                        run_id=item.run_id,
                        timeout_seconds=remaining(),
                    )
            else:
                row["attempts"] = cast(int, row["attempts"]) + 1
                checkpoint(deepcopy(state))
                asset = await media.probe(
                    item.video, CancellationContext(item.run_id, min(120, remaining()))
                )
                if row["sourceSha256"] not in (None, asset.sha256):
                    raise AppError(
                        "storage.batch_identity", "已登记素材内容改变。", ExitCode.STORAGE
                    )
                row["sourceSha256"] = asset.sha256
                checkpoint(deepcopy(state))
                result = await prepare_media(
                    PreparedAnalyze(item.video, plan.project, plan.config, plan.max_cost_cny, None),
                    media,
                    store,
                    plan.project,
                    run_id=item.run_id,
                    asset=asset,
                    timeout_seconds=remaining(),
                )
            remaining()
            stored = await store.load_run(item.run_id)
            row.update(
                status="prepared" if result.coverage_fits else "coverage_blocked",
                result=_payload(plan, item, stored, result),
                verifiedThisInvocation=True,
            )
            checkpoint(deepcopy(state))
        except (asyncio.CancelledError, KeyboardInterrupt):
            row.update(
                status="cancelled",
                errorCode="operation.cancelled",
                message="本次准备取消，可续跑同批次。",
                verifiedThisInvocation=True,
            )
            state["status"], state["exitCode"] = "cancelled", int(ExitCode.CANCELLED)
            checkpoint(deepcopy(state))
            break
        except AppError as error:
            row.update(
                status="failed",
                errorCode=error.code,
                message=error.message,
                verifiedThisInvocation=True,
            )
            if error.exit_code != ExitCode.INPUT:
                state["status"], state["exitCode"] = "stopped", int(error.exit_code)
            checkpoint(deepcopy(state))
            if state["status"] == "stopped":
                break
        except Exception:
            row.update(
                status="failed",
                errorCode="environment.media_batch",
                message="素材准备停止，请检查本机环境后续跑。",
                verifiedThisInvocation=True,
            )
            state["status"], state["exitCode"] = "stopped", int(ExitCode.ENVIRONMENT)
            checkpoint(deepcopy(state))
            break
    if state["status"] == "running":
        failed = any(row["status"] in ("failed", "coverage_blocked") for row in rows)
        state["status"], state["exitCode"] = (
            ("partial", int(ExitCode.INPUT)) if failed else ("finished", 0)
        )
        checkpoint(deepcopy(state))
    return {
        "schemaVersion": "media-batch-result-v1",
        "batchId": plan.batch_id,
        "project": str(plan.project),
        "status": state["status"],
        "exitCode": state["exitCode"],
        "items": rows,
        "reusedPreparedTasks": reused,
        "elapsedMs": round((perf_counter() - began) * 1000),
        "savedMaxCostCnyPerTask": str(plan.max_cost_cny),
        "modelInvocations": 0,
        "newReservations": 0,
        "nextCommand": [
            "gamingcreator",
            "prepare-media-batch",
            "--project",
            str(plan.project),
            "--resume",
            plan.batch_id,
        ],
        "message": "批次仅准备本机素材，后续分析须逐任务另行明确执行。",
    }
