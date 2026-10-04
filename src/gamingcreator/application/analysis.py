"""Analysis over the existing media, ASR, vision, and store ports.

A missing vision price snapshot is not treated as zero. The vision provider's
budget ledger stops that attempt before a request leaves the process. Resume of
a pending or running analysis continues after completed stage checkpoints and
does not redo those stages.
"""

import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from time import monotonic
from uuid import uuid4

from gamingcreator.application.inputs import AnalysisConfig, PreparedAnalyze
from gamingcreator.application.media import MediaProcessor, SamplingParameters
from gamingcreator.application.providers import (
    AsrProvider,
    AsrRequest,
    CancellationContext,
    InvocationMetadata,
    ProviderStatus,
    ProviderUsage,
    VisionProvider,
    VisionRequest,
)
from gamingcreator.application.storage import (
    InvocationStatus,
    RunConfiguration,
    RunStatus,
    StageCheckpoint,
    StageStatus,
    StoredTimeline,
    TimelineStore,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import MediaAsset, MediaPreprocessingResult, VisualEvidence
from gamingcreator.domain.models import EvidenceReference

PIPELINE_VERSION = "phase0-analyze-v1"
WINDOW_PIPELINE_VERSION = "phase0-analyze-v2"
TEMPORAL_PIPELINE_VERSION = "phase0-analyze-temporal-v1"
DETAILED_PIPELINE_VERSION = "phase0-analyze-detailed-v1"
# These match the first vision provider. The provider rejects any other pair.
VISION_PROMPT_VERSION = "phase0-vision-v1"
VISION_SCHEMA_VERSION = "semantic-events-v1"
ASR_SCHEMA_VERSION = "transcript-v1"
REQUIRED_STAGES = ("media", "asr", "vision")


@dataclass(frozen=True, slots=True)
class AnalysisPorts:
    media: MediaProcessor
    asr: AsrProvider
    vision: VisionProvider
    store: TimelineStore
    asr_metadata: Callable[[AsrRequest], InvocationMetadata] | None = None


@dataclass(frozen=True, slots=True)
class AnalyzeOutcome:
    run_id: str
    media_id: str
    event_count: int
    transcript_count: int


def _exit_for(code: str) -> ExitCode:
    if code == "operation.cancelled" or code.endswith(".cancelled"):
        return ExitCode.CANCELLED
    if code.startswith("budget."):
        return ExitCode.BUDGET
    if code.startswith("storage."):
        return ExitCode.STORAGE
    if code.startswith(("input.", "media.")):
        return ExitCode.INPUT
    if code.startswith(("configuration.", "environment.")):
        return ExitCode.ENVIRONMENT
    return ExitCode.PROVIDER


def _vision_limit(vision: VisionProvider) -> tuple[int, int]:
    capabilities = vision.capabilities
    width = capabilities.max_image_width
    if (
        not capabilities.image_sequence
        or not capabilities.structured_output
        or capabilities.max_images is None
        or capabilities.max_images < 1
        or width is None
        or width < 2
    ):
        raise AppError("provider.capability", "视觉模型不接受带时间的图片序列。", ExitCode.PROVIDER)
    return capabilities.max_images, width


def _select(images: tuple[VisualEvidence, ...], limit: int) -> tuple[VisualEvidence, ...]:
    if len(images) <= limit:
        return images
    if limit == 1:
        return (images[0],)
    last = len(images) - 1
    indexes = sorted({round(i * last / (limit - 1)) for i in range(limit)})
    return tuple(images[index] for index in indexes)


def _image_requests(bundle: MediaPreprocessingResult, limit: int) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            image.evidence_id,
            bundle.asset.media_id,
            "image",
            image.source_time,
            image.path,
            image.sha256,
            bundle.transform_version,
        )
        for image in _select(bundle.images, limit)
    )


def vision_windows(
    bundle: MediaPreprocessingResult, config: AnalysisConfig
) -> tuple[tuple[EvidenceReference, ...], ...]:
    """Cover every extracted frame; consecutive windows share the configured overlap."""
    images = bundle.images
    stride = config.window_frames - config.window_overlap
    windows = []
    for offset in range(0, len(images), stride):
        selected = images[offset : offset + config.window_frames]
        windows.append(
            tuple(
                EvidenceReference(
                    image.evidence_id,
                    bundle.asset.media_id,
                    "image",
                    image.source_time,
                    image.path,
                    image.sha256,
                    bundle.transform_version,
                )
                for image in selected
            )
        )
        if offset + config.window_frames >= len(images):
            break
    return tuple(windows)


def _pipeline_version(config: AnalysisConfig) -> str:
    if config.schema_version == 2 and config.vision_prompt_version == "phase0-vision-v5":
        return DETAILED_PIPELINE_VERSION
    if config.schema_version == 2 and config.vision_prompt_version in (
        "phase0-vision-v3",
        "phase0-vision-v4",
    ):
        return TEMPORAL_PIPELINE_VERSION
    return WINDOW_PIPELINE_VERSION if config.schema_version == 2 else PIPELINE_VERSION


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _asr_input_hash(asset: MediaAsset, metadata: InvocationMetadata) -> str:
    details = json.loads(metadata.execution_details or "{}")
    for volatile in (
        "workerElapsedMs",
        "detectedLanguage",
        "modelIntegrityVerified",
        "nativeLibraries",
    ):
        details.pop(volatile, None)
    return _digest(
        {
            "source": asset.sha256,
            "provider": metadata.provider,
            "model": metadata.requested_model,
            "revision": metadata.model_revision,
            "prompt": metadata.prompt_version,
            "schema": metadata.schema_version,
            "execution": details,
        }
    )


def _document(timeline: StoredTimeline) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "runId": timeline.run.run_id,
        "mediaId": timeline.run.asset.media_id,
        "media": {
            "sourcePath": str(timeline.run.asset.source_path),
            "sha256": timeline.run.asset.sha256,
            "durationUs": timeline.run.asset.duration_us,
            "originSeconds": {
                "numerator": timeline.run.asset.origin_seconds.numerator,
                "denominator": timeline.run.asset.origin_seconds.denominator,
            },
        },
        "status": "completed",
        "events": [
            {
                "eventId": event.event_id,
                "startUs": event.source_range.start_us,
                "endUs": event.source_range.end_us,
                "observableFacts": list(event.observable_facts),
                "mechanicTags": list(event.mechanic_tags),
                "evidenceIds": list(event.evidence_ids),
                "modality": event.modality,
                "uncertainty": event.uncertainty,
            }
            for event in timeline.events
        ],
        "transcripts": [
            {
                "startUs": segment.source_range.start_us,
                "endUs": segment.source_range.end_us,
                "text": segment.text,
                "uncertainty": segment.uncertainty,
            }
            for segment in timeline.transcripts
        ],
        "invocations": [
            {
                "invocationId": item.invocation_id,
                "stageId": item.stage_id,
                "attempt": item.metadata.attempt,
                "provider": item.metadata.provider,
                "requestedModel": item.metadata.requested_model,
                "actualModel": item.metadata.actual_model,
                "costCny": None
                if item.metadata.usage.cost_cny is None
                else str(item.metadata.usage.cost_cny),
                "costStatus": str(item.metadata.usage.cost_status),
                "status": str(item.status),
                "modelRevision": item.metadata.model_revision,
                "promptVersion": item.metadata.prompt_version,
                "schemaVersion": item.metadata.schema_version,
                "priceVersion": item.metadata.price_version,
                "elapsedMs": item.metadata.elapsed_ms,
                "requestId": item.metadata.request_id,
                "inputTokens": item.metadata.usage.input_tokens,
                "cachedInputTokens": item.metadata.usage.cached_input_tokens,
                "outputTokens": item.metadata.usage.output_tokens,
                "executionDetails": json.loads(item.metadata.execution_details or "{}"),
            }
            for item in timeline.invocations
        ],
        "providerElapsedMs": sum(item.metadata.elapsed_ms or 0 for item in timeline.invocations),
        "modelApiCost": {
            "knownEstimatedCny": str(
                sum((item.metadata.usage.cost_cny or 0 for item in timeline.invocations), start=0)
            ),
            "totalCny": None
            if any(item.metadata.usage.cost_cny is None for item in timeline.invocations)
            else str(
                sum((item.metadata.usage.cost_cny or 0 for item in timeline.invocations), start=0)
            ),
            "unknownAttempts": sum(
                item.metadata.usage.cost_cny is None for item in timeline.invocations
            ),
            "billingConfirmed": False,
        },
        "configuration": {
            "configHash": timeline.run.config_hash,
            "pipelineVersion": timeline.run.configuration.pipeline_version,
            "pipelineHash": timeline.run.configuration.pipeline_hash,
            "maxCostCny": str(timeline.run.configuration.max_cost_cny),
            "samplingIntervalMs": timeline.run.configuration.analysis.sampling_interval_ms,
            "windowFrames": timeline.run.configuration.analysis.window_frames,
            "windowOverlap": timeline.run.configuration.analysis.window_overlap,
            "visionPromptVersion": timeline.run.configuration.analysis.vision_prompt_version,
            "visionPromptHash": timeline.run.configuration.analysis.vision_prompt_hash,
        },
    }


def _write_export(project: Path, timeline: StoredTimeline) -> None:
    path = project / "runs" / timeline.run.run_id / "semantic_timeline.json"
    temporary = path.with_suffix(".json.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("wb") as handle:
        handle.write(json.dumps(_document(timeline), ensure_ascii=False, indent=2).encode())
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


async def _abort(
    store: TimelineStore, run_id: str, created: bool, completed: bool, code: str
) -> None:
    if not created or completed:
        return
    status = RunStatus.CANCELLED if _exit_for(code) == ExitCode.CANCELLED else RunStatus.FAILED
    with suppress(AppError):
        await store.stop_run(run_id, status, code)


def _audio_request(run_id: str, bundle: MediaPreprocessingResult) -> AsrRequest:
    audio = bundle.audio
    reference = None
    if audio is not None:
        coverage = audio.map_interval(0, audio.sample_count, bundle.asset)
        reference = EvidenceReference(
            audio.evidence_id,
            bundle.asset.media_id,
            "audio",
            coverage.source_range,
            audio.path,
            audio.sha256,
            bundle.transform_version,
        )
    return AsrRequest(
        run_id,
        reference,
        ASR_SCHEMA_VERSION,
        media_asset=bundle.asset,
        audio_clock=audio,
    )


async def _record_asr(
    store: TimelineStore,
    run_id: str,
    metadata: InvocationMetadata,
    status: ProviderStatus,
    error_code: str | None,
) -> None:
    opening = replace(metadata, usage=ProviderUsage(), elapsed_ms=None)
    invocation_id = uuid4().hex
    await store.begin_invocation(invocation_id, run_id, "asr", f"{run_id}:asr", opening)
    await store.finish_invocation(
        invocation_id, InvocationStatus(status.value), metadata, error_code
    )


async def _run_pipeline(
    prepared: PreparedAnalyze,
    ports: AnalysisPorts,
    asset: MediaAsset,
    config: AnalysisConfig,
    project: Path,
    *,
    run_id: str,
    completed_stages: frozenset[str],
    timeout_seconds: float,
) -> AnalyzeOutcome:
    image_limit, image_width = _vision_limit(ports.vision)
    # Preserve the extraction identity of historical prompts after capability growth.
    image_width = min(
        image_width, 1280 if config.vision_prompt_version == "phase0-vision-v5" else 512
    )
    if config.vision_prompt_version not in (
        "phase0-vision-v3",
        "phase0-vision-v4",
        "phase0-vision-v5",
    ):
        image_limit = min(image_limit, 5)
    context = CancellationContext(run_id, timeout_seconds)
    deadline = monotonic() + timeout_seconds

    def remaining() -> CancellationContext:
        seconds = deadline - monotonic()
        if seconds <= 0:
            raise AppError(
                "analysis.timeout",
                "分析达到总时间上限，已保留完成窗口。",
                ExitCode.PROVIDER,
                run_id,
            )
        return CancellationContext(run_id, seconds, context.cancelled)

    finished = False
    try:
        if "media" in completed_stages:
            bundle = await ports.store.load_media_bundle(run_id)
        else:
            await ports.store.begin_stage(run_id, "media", asset.sha256)
            media_directory = project / "runs" / run_id / "media"
            if config.schema_version == 2 and media_directory.exists():
                media_directory = media_directory.with_name("media-retry-" + uuid4().hex[:12])
            bundle = await ports.media.preprocess(
                prepared.video,
                media_directory,
                SamplingParameters(
                    Fraction(config.sampling_interval_ms, 1000),
                    image_width,
                    config.max_input_frames,
                ),
                remaining(),
            )
            if bundle.asset.sha256 != asset.sha256 or not bundle.images:
                raise AppError("media.no_frames", "没有可分析的画面证据。", ExitCode.INPUT, run_id)
            await ports.store.persist_media_bundle(run_id, bundle)
        if "asr" not in completed_stages:
            if config.schema_version == 2:
                windows = vision_windows(bundle, config)
                if (
                    len(windows) > config.max_requests
                    or sum(len(window) for window in windows) > config.max_input_frames
                ):
                    raise AppError(
                        "budget.coverage_limit",
                        "配置的请求或上传帧上限不足以覆盖视频，尚未调用模型。",
                        ExitCode.BUDGET,
                        run_id,
                    )
            audio_request = replace(_audio_request(run_id, bundle), language=config.asr_language)
            description = ports.asr_metadata(audio_request) if ports.asr_metadata else None
            await ports.store.begin_stage(
                run_id,
                "asr",
                _asr_input_hash(asset, description)
                if config.schema_version == 2 and description is not None
                else asset.sha256,
            )
            invocation_id = uuid4().hex
            attempt = next(
                stage.attempt
                for stage in await ports.store.load_checkpoints(run_id)
                if stage.stage_id == "asr"
            )
            if description is not None:
                opening = replace(
                    description,
                    attempt=attempt,
                    usage=ProviderUsage(),
                    elapsed_ms=None,
                )
                await ports.store.begin_invocation(
                    invocation_id, run_id, "asr", f"{run_id}:asr", opening
                )
            elif config.schema_version == 2:
                raise AppError(
                    "configuration.asr_metadata",
                    "语音模型缺少调用前版本记录。",
                    ExitCode.ENVIRONMENT,
                    run_id,
                )
            transcript = await ports.asr.transcribe(audio_request, remaining())
            if ports.asr_metadata is not None:
                await ports.store.finish_invocation(
                    invocation_id,
                    InvocationStatus(transcript.status.value),
                    replace(transcript.metadata, attempt=attempt),
                    None if transcript.error is None else transcript.error.code,
                )
            else:
                await _record_asr(
                    ports.store,
                    run_id,
                    transcript.metadata,
                    transcript.status,
                    None if transcript.error is None else transcript.error.code,
                )
            if transcript.status in (ProviderStatus.FAILED, ProviderStatus.CANCELLED):
                code = transcript.error.code if transcript.error is not None else "asr.failed"
                raise AppError(code, "语音转录没有完成。", _exit_for(code), run_id)
            segments = transcript.output if transcript.output is not None else ()
            await ports.store.persist_timeline(
                run_id,
                "asr",
                (),
                segments,
                _digest([segment.text for segment in segments]),
            )
        evidence = _image_requests(bundle, min(config.max_input_frames, image_limit))
        if not evidence:
            raise AppError("media.no_frames", "没有可分析的画面证据。", ExitCode.INPUT, run_id)
        if "vision" not in completed_stages:
            await ports.store.begin_stage(
                run_id, "vision", _digest([item.evidence_id for item in bundle.images])
            )
            if config.schema_version == 2:
                if config.window_frames > image_limit:
                    raise AppError(
                        "provider.capability", "窗口超过模型图片上限。", ExitCode.PROVIDER, run_id
                    )
                windows = vision_windows(bundle, config)
                existing = {
                    event.event_id: event
                    for event in (
                        await ports.store.load_timeline(run_id, require_completed=False)
                    ).events
                }
                for index, window in enumerate(windows):
                    stage_id = f"vision-{index:06d}"
                    if stage_id in completed_stages:
                        continue
                    await ports.store.begin_stage(
                        run_id, stage_id, _digest([item.evidence_id for item in window])
                    )
                    visual = await ports.vision.analyze(
                        VisionRequest(
                            run_id,
                            window,
                            config.vision_prompt_version,
                            "temporal-actions-v1"
                            if config.vision_prompt_version
                            in ("phase0-vision-v4", "phase0-vision-v5")
                            else VISION_SCHEMA_VERSION,
                            config.max_output_tokens,
                            stage_id=stage_id,
                        ),
                        remaining(),
                    )
                    if visual.status != ProviderStatus.COMPLETED or visual.output is None:
                        code = visual.error.code if visual.error else "provider.failed"
                        raise AppError(
                            code, "视觉窗口分析没有完成；已保存先前窗口。", _exit_for(code), run_id
                        )
                    fresh = []
                    for event in visual.output:
                        previous = existing.get(event.event_id)
                        if previous is not None:
                            if previous != event:
                                raise AppError(
                                    "provider.event_identity",
                                    "同一事件标识对应不同内容。",
                                    ExitCode.PROVIDER,
                                    run_id,
                                )
                            continue
                        existing[event.event_id] = event
                        fresh.append(event)
                    await ports.store.persist_timeline(
                        run_id,
                        stage_id,
                        tuple(fresh),
                        (),
                        _digest([event.event_id for event in visual.output]),
                    )
                    print(
                        json.dumps(
                            {
                                "runId": run_id,
                                "stage": "vision",
                                "completedWindows": index + 1,
                                "totalWindows": len(windows),
                            },
                            ensure_ascii=True,
                        ),
                        file=sys.stderr,
                        flush=True,
                    )
                await ports.store.finish_stage(
                    run_id, "vision", StageStatus.COMPLETED, _digest(sorted(existing))
                )
            else:
                await _legacy_vision(ports, run_id, evidence, remaining())
        await ports.store.complete_run(run_id)
        finished = True
        timeline = await ports.store.load_completed_timeline(run_id)
        try:
            _write_export(project, timeline)
        except OSError:
            raise AppError(
                "storage.export",
                "语义时间线已入库，导出文件写入失败。",
                ExitCode.STORAGE,
                run_id,
            ) from None
        return AnalyzeOutcome(
            run_id, timeline.run.asset.media_id, len(timeline.events), len(timeline.transcripts)
        )
    except AppError as error:
        await _abort(ports.store, run_id, True, finished, error.code)
        if error.run_id is None:
            raise AppError(error.code, error.message, error.exit_code, run_id) from error
        raise
    except (KeyboardInterrupt, asyncio.CancelledError):
        await _abort(ports.store, run_id, True, finished, "operation.cancelled")
        raise
    except Exception:
        await _abort(ports.store, run_id, True, finished, "analysis.unexpected")
        raise AppError(
            "analysis.unexpected", "分析意外停止，已保留完成窗口。", ExitCode.PROVIDER, run_id
        ) from None


async def _legacy_vision(
    ports: AnalysisPorts,
    run_id: str,
    evidence: tuple[EvidenceReference, ...],
    context: CancellationContext,
) -> None:
    visual = await ports.vision.analyze(
        VisionRequest(run_id, evidence, VISION_PROMPT_VERSION, VISION_SCHEMA_VERSION, 1024), context
    )
    if visual.status != ProviderStatus.COMPLETED or visual.output is None:
        code = visual.error.code if visual.error else "provider.failed"
        raise AppError(code, "视觉分析没有完成。", _exit_for(code), run_id)
    await ports.store.persist_timeline(
        run_id, "vision", visual.output, (), _digest([event.event_id for event in visual.output])
    )


async def run_new_analysis(
    prepared: PreparedAnalyze,
    ports: AnalysisPorts,
    asset: MediaAsset,
    project: Path,
    *,
    run_id: str,
    timeout_seconds: float = 3600,
) -> AnalyzeOutcome:
    config = prepared.config
    budget = prepared.max_cost_cny
    if config is None or budget is None or prepared.resume is not None:
        raise AppError("input.analyze", "新分析须提供配置文件与正数费用上限。", ExitCode.INPUT)
    await ports.store.create_run(
        run_id,
        asset,
        RunConfiguration(
            config,
            budget,
            _pipeline_version(config),
            hashlib.sha256(_pipeline_version(config).encode()).hexdigest(),
            REQUIRED_STAGES,
        ),
    )
    return await _run_pipeline(
        prepared,
        ports,
        asset,
        config,
        project,
        run_id=run_id,
        completed_stages=frozenset(),
        timeout_seconds=timeout_seconds,
    )


def _resume_stages(checkpoints: tuple[StageCheckpoint, ...]) -> frozenset[str]:
    completed: set[str] = set()
    for checkpoint in checkpoints:
        if checkpoint.status != StageStatus.COMPLETED:
            raise AppError(
                "storage.run_incomplete",
                "未完成的运行还有未结束的阶段，不能从中断处续跑。",
                ExitCode.STORAGE,
            )
        completed.add(checkpoint.stage_id)
    if ("asr" in completed and "media" not in completed) or (
        "vision" in completed and not {"media", "asr"} <= completed
    ):
        raise AppError(
            "storage.run_incomplete",
            "未完成的运行还有未结束的阶段，不能从中断处续跑。",
            ExitCode.STORAGE,
        )
    return frozenset(completed)


async def resume_analysis(
    prepared: PreparedAnalyze,
    store: TimelineStore,
    project: Path,
    ports: AnalysisPorts | None = None,
    *,
    timeout_seconds: float = 3600,
) -> AnalyzeOutcome:
    run_id = prepared.resume
    if run_id is None:
        raise AppError("input.resume", "续跑须提供运行 ID，且不得覆盖配置或预算。", ExitCode.INPUT)
    try:
        stored = await store.load_run(run_id)
    except AppError as error:
        raise AppError(error.code, error.message, error.exit_code, run_id) from error
    if stored.asset.source_path.resolve() != prepared.video.resolve():
        raise AppError("input.resume", "续跑视频与原运行不一致。", ExitCode.INPUT, run_id)
    if stored.status == RunStatus.COMPLETED:
        timeline = await store.load_completed_timeline(run_id)
        if not (project / "runs" / run_id / "semantic_timeline.json").is_file():
            _write_export(project, timeline)
        return AnalyzeOutcome(
            run_id, timeline.run.asset.media_id, len(timeline.events), len(timeline.transcripts)
        )
    configuration = stored.configuration
    window_pipeline = configuration.analysis.schema_version == 2
    if not window_pipeline and stored.status in (
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    ):
        code = stored.error_code or "storage.run_state"
        raise AppError(code, "该运行已停止，不会自动重放。", _exit_for(code), run_id)
    if ports is None:
        raise AppError(
            "storage.run_incomplete", "未完成的运行还不能从中断处续跑。", ExitCode.STORAGE, run_id
        )
    try:
        checkpoints = await store.load_checkpoints(run_id)
        completed_stages = (
            frozenset(row.stage_id for row in checkpoints if row.status == StageStatus.COMPLETED)
            if window_pipeline
            else _resume_stages(checkpoints)
        )
    except AppError as error:
        raise AppError(error.code, error.message, error.exit_code, run_id) from error
    version = _pipeline_version(configuration.analysis)
    if (
        configuration.pipeline_version != version
        or configuration.pipeline_hash != hashlib.sha256(version.encode()).hexdigest()
        or configuration.required_stages != REQUIRED_STAGES
        or configuration.analysis.provider != "deepseek"
        or configuration.analysis.model != "deepseek-flash"
    ):
        raise AppError("input.resume", "续跑不能改用另一套流水线。", ExitCode.INPUT, run_id)
    if window_pipeline:
        # An attempt can finish remotely before its local result/checkpoint is committed.
        # Replaying any such uncommitted response requires an explicit retry choice.
        # Its charge, including an unknown-charge reservation, remains in the ledger.
        attempts = await store.load_invocations(run_id)
        if (
            "vision" not in completed_stages
            and any(
                item.metadata.provider == "deepseek"
                and (
                    item.status
                    in (
                        InvocationStatus.RUNNING,
                        InvocationStatus.INTERRUPTED,
                        InvocationStatus.COMPLETED,
                    )
                    or item.metadata.usage.cost_cny is None
                )
                and item.stage_id not in completed_stages
                for item in attempts
            )
            and not prepared.retry_uncertain
        ):
            raise AppError(
                "budget.retry_confirmation_required",
                "有未提交的远端调用；显式传入 --retry-uncertain 可保留原费用后重试。",
                ExitCode.BUDGET,
                run_id,
            )
        if ("asr" in completed_stages and "media" not in completed_stages) or (
            "vision" in completed_stages and not {"media", "asr"} <= completed_stages
        ):
            raise AppError(
                "storage.run_incomplete", "阶段检查点顺序无效。", ExitCode.STORAGE, run_id
            )
        await store.prepare_resume(run_id)
    return await _run_pipeline(
        prepared,
        ports,
        stored.asset,
        configuration.analysis,
        project,
        run_id=run_id,
        completed_stages=completed_stages,
        timeout_seconds=timeout_seconds,
    )
