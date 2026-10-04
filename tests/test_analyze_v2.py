"""Window checkpoints preserve usable work across failures and explicit resumes."""

import asyncio
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from test_analyze import (
    RUN_ID,
    ScriptedAsr,
    asr_metadata,
    asr_result,
    build_bundle,
    jpeg_bytes,
)

from gamingcreator.application.analysis import (
    AnalysisPorts,
    resume_analysis,
    run_new_analysis,
    vision_windows,
)
from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.inputs import AnalysisConfig, PreparedAnalyze
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import (
    ProviderCapabilities,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
)
from gamingcreator.application.storage import InvocationStatus, RunStatus
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import VisualEvidence
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

CONFIG = AnalysisConfig("deepseek", "deepseek-flash", 20, 100, 2, "deepseek-flash-cny-2026-10-04")


def window_bundle(root: Path):
    bundle, project, source = build_bundle(root)
    images = []
    for index in range(13):
        path = bundle.manifest_path.parent / f"frame-{index:06d}.jpg"
        path.write_bytes(jpeg_bytes())
        pts = index * 300
        images.append(
            VisualEvidence(
                f"{RUN_ID}:{bundle.asset.media_id}:image:{index:06d}",
                path,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                pts,
                Fraction(1, 1000),
                bundle.asset.instant(pts, Fraction(1, 1000)),
            )
        )
    bundle = replace(bundle, images=tuple(images))
    write_manifest(bundle, SamplingParameters(max_width=512, max_frames=100))
    return bundle, project, source


class WindowMedia:
    def __init__(self, bundle):
        self.bundle = bundle
        self.calls = 0

    async def preprocess(self, source, output, parameters, context):
        self.calls += 1
        return self.bundle


class WindowVision:
    capabilities = ProviderCapabilities(
        image_sequence=True, structured_output=True, max_images=5, max_image_width=512
    )

    def __init__(self, failure=None):
        self.stages = []
        self.failure = failure

    async def analyze(self, request, context):
        self.stages.append(request.stage_id)
        if request.stage_id == self.failure:
            return ProviderResult(
                ProviderStatus.FAILED,
                None,
                asr_metadata(),
                ProviderFailure("provider.schema", False),
            )
        first, last = request.evidence[0], request.evidence[-1]
        event = SemanticEvent(
            request.stage_id,
            first.media_id,
            RUN_ID,
            SourceRange(
                first.source_time.time_us,
                last.source_time.time_us + 1,
                first.source_time.duration_us,
            ),
            ("角色跳跃",),
            ("jump",),
            tuple(sorted(item.evidence_id for item in request.evidence)),
            "visual",
            None,
        )
        return ProviderResult(ProviderStatus.COMPLETED, (event,), asr_metadata())


def test_every_frame_is_covered_and_overlap_is_bounded(tmp_path):
    bundle, _, _ = window_bundle(tmp_path)
    windows = vision_windows(bundle, CONFIG)
    assert [len(window) for window in windows] == [5, 5, 5]
    assert {item.evidence_id for window in windows for item in window} == {
        item.evidence_id for item in bundle.images
    }
    assert windows[0][-1].evidence_id == windows[1][0].evidence_id


def test_later_window_failure_resumes_only_missing_windows(tmp_path):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        media, asr = WindowMedia(bundle), ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO))
        vision = WindowVision("vision-000001")

        def describe(request):
            assert asr.calls == 0
            return asr_metadata()

        ports = AnalysisPorts(media, asr, vision, store, describe)
        try:
            with pytest.raises(AppError, match="视觉窗口"):
                await run_new_analysis(
                    PreparedAnalyze(source, project, CONFIG, Decimal(5), None),
                    ports,
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                )
            partial = await store.load_timeline(RUN_ID, require_completed=False)
            assert len(partial.events) == 1 and partial.run.status == RunStatus.FAILED
            replacement = WindowVision()
            result = await resume_analysis(
                PreparedAnalyze(source, project, None, None, RUN_ID),
                store,
                project,
                AnalysisPorts(media, asr, replacement, store, describe),
            )
            assert replacement.stages == ["vision-000001", "vision-000002"]
            assert media.calls == asr.calls == 1
            assert result.event_count == 3
        finally:
            await store.close()

    asyncio.run(scenario())


def test_resume_finalizes_completed_checkpoints_without_model_calls(tmp_path, monkeypatch):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        media, asr, vision = (
            WindowMedia(bundle),
            ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO)),
            WindowVision(),
        )
        ports = AnalysisPorts(media, asr, vision, store, lambda request: asr_metadata())
        original_complete = store.complete_run

        async def crash_before_complete(run_id):
            raise AppError("storage.injected", "模拟最终提交前中断。", ExitCode.STORAGE)

        monkeypatch.setattr(store, "complete_run", crash_before_complete)
        try:
            with pytest.raises(AppError):
                await run_new_analysis(
                    PreparedAnalyze(source, project, CONFIG, Decimal(5), None),
                    ports,
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                )
            monkeypatch.setattr(store, "complete_run", original_complete)
            result = await resume_analysis(
                PreparedAnalyze(source, project, None, None, RUN_ID), store, project, ports
            )
            assert result.event_count == 3 and len(vision.stages) == 3
            assert media.calls == asr.calls == 1
        finally:
            await store.close()

    asyncio.run(scenario())


def test_uncertain_remote_attempt_needs_explicit_retry_and_keeps_charge(tmp_path):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        media, asr = WindowMedia(bundle), ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO))

        class InterruptedVision(WindowVision):
            async def analyze(self, request, context):
                if request.stage_id == "vision-000001":
                    metadata = replace(
                        asr_metadata(),
                        provider="deepseek",
                        elapsed_ms=None,
                        execution_details=json.dumps(
                            {
                                "inputFrames": len(request.evidence),
                                "reservationCny": "2.016384",
                                "evidenceIds": [item.evidence_id for item in request.evidence],
                            }
                        ),
                    )
                    await store.begin_invocation(
                        "uncertain-1", RUN_ID, request.stage_id, "logical-1", metadata
                    )
                    raise AppError("provider.timeout", "模拟远端未确认中断。", ExitCode.PROVIDER)
                return await super().analyze(request, context)

        ports = AnalysisPorts(
            media, asr, InterruptedVision(), store, lambda request: asr_metadata()
        )
        try:
            with pytest.raises(AppError):
                await run_new_analysis(
                    PreparedAnalyze(source, project, CONFIG, Decimal(5), None),
                    ports,
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                )
            attempts = await store.load_invocations(RUN_ID)
            assert attempts[-1].status == InvocationStatus.INTERRUPTED
            ledger = BudgetLedger(Decimal(5), 20, 100)
            ledger.restore(attempts)
            assert ledger.requests == 1 and ledger.frames == 5
            assert ledger.known_cost_cny == 0 and ledger.reserved_cny == Decimal("2.016384")
            replacement = WindowVision()
            resumed_ports = AnalysisPorts(
                media, asr, replacement, store, lambda request: asr_metadata()
            )
            with pytest.raises(AppError) as refused:
                await resume_analysis(
                    PreparedAnalyze(source, project, None, None, RUN_ID),
                    store,
                    project,
                    resumed_ports,
                )
            assert (
                refused.value.code == "budget.retry_confirmation_required"
                and not replacement.stages
            )
            outcome = await resume_analysis(
                PreparedAnalyze(source, project, None, None, RUN_ID, True),
                store,
                project,
                resumed_ports,
            )
            assert outcome.event_count == 3
            assert ledger.reserved_cny == Decimal("2.016384")
        finally:
            await store.close()

    asyncio.run(scenario())


def test_asr_is_recorded_before_inference_and_revised_model_cannot_resume(tmp_path):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        opening = replace(asr_metadata(), model_revision="revision-1", elapsed_ms=None)

        class InterruptedAsr(ScriptedAsr):
            async def transcribe(self, request, context):
                self.calls += 1
                attempts = await store.load_invocations(RUN_ID)
                assert len(attempts) == 1 and attempts[0].status == InvocationStatus.RUNNING
                assert attempts[0].metadata.model_revision == "revision-1"
                raise AppError("asr.timeout", "模拟worker中断。", ExitCode.PROVIDER)

        media, asr, vision = (
            WindowMedia(bundle),
            InterruptedAsr(asr_result(ProviderStatus.NO_AUDIO)),
            WindowVision(),
        )
        ports = AnalysisPorts(media, asr, vision, store, lambda request: opening)
        try:
            with pytest.raises(AppError):
                await run_new_analysis(
                    PreparedAnalyze(source, project, CONFIG, Decimal(5), None),
                    ports,
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                )
            updated = AnalysisPorts(
                media,
                asr,
                vision,
                store,
                lambda request: replace(opening, model_revision="revision-2"),
            )
            with pytest.raises(AppError) as refused:
                await resume_analysis(
                    PreparedAnalyze(source, project, None, None, RUN_ID), store, project, updated
                )
            assert refused.value.code == "storage.resume_mismatch"
            assert asr.calls == 1 and not vision.stages
        finally:
            await store.close()

    asyncio.run(scenario())
