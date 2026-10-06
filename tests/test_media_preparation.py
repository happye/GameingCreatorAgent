"""Offline preparation leaves a durable checkpoint for explicit analysis."""

import asyncio
from dataclasses import replace
from decimal import Decimal

import pytest
from test_analyze import RUN_ID, ScriptedAsr, asr_metadata, asr_result, build_bundle
from test_analyze_v2 import CONFIG, WindowMedia, WindowVision, window_bundle

from gamingcreator.application.analysis import AnalysisPorts, prepare_media, resume_analysis
from gamingcreator.application.inputs import PreparedAnalyze
from gamingcreator.application.providers import ProviderStatus
from gamingcreator.application.storage import RunStatus, StageStatus
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.deepseek_vision import vision_prompt_fingerprint
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def prepared(source, project, *, config=CONFIG, resume=False):
    return PreparedAnalyze(
        source,
        project,
        None if resume else config,
        None if resume else Decimal(5),
        RUN_ID if resume else None,
    )


def test_preparation_is_pending_and_explicit_analysis_reuses_media_after_reopening(tmp_path):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        media = WindowMedia(bundle)
        store = await SqliteTimelineStore.open(project)
        try:
            result = await prepare_media(
                prepared(source, project), media, store, project, run_id=RUN_ID, asset=bundle.asset
            )
            assert result.image_count == 13 and result.window_count == 3
            assert result.upload_frame_count == 15 and result.coverage_fits
            stored = await store.load_run(RUN_ID)
            assert stored.status == RunStatus.PENDING and stored.configuration.analysis == CONFIG
            assert stored.configuration.max_cost_cny == Decimal(5)
            assert await store.load_invocations(RUN_ID) == ()
            checkpoints = await store.load_checkpoints(RUN_ID)
            assert [(row.stage_id, row.status, row.attempt) for row in checkpoints] == [
                ("media", StageStatus.COMPLETED, 1)
            ]
            assert not (project / "runs" / RUN_ID / "semantic_timeline.json").exists()
            with pytest.raises(AppError):
                await store.load_completed_timeline(RUN_ID)
            recovery = await store.recover()
            assert recovery.interrupted_runs == () and recovery.integrity_issues == ()
        finally:
            await store.close()
        store = await SqliteTimelineStore.open(project)
        asr, vision = ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO)), WindowVision()
        try:
            result = await resume_analysis(
                prepared(source, project, resume=True),
                store,
                project,
                AnalysisPorts(media, asr, vision, store, lambda request: asr_metadata()),
            )
            assert result.event_count == 3 and media.calls == asr.calls == 1
            assert len(vision.stages) == 3
            assert (await store.load_run(RUN_ID)).status == RunStatus.COMPLETED
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "prompt,width",
    [
        ("phase0-vision-v2", 512),
        ("phase0-vision-v4", 512),
        ("phase0-vision-v5", 1280),
        ("phase0-vision-v6", 1280),
    ],
)
def test_preparation_preserves_analysis_extraction_identity(tmp_path, prompt, width):
    async def scenario():
        bundle, project, source = build_bundle(tmp_path)

        class CapturingMedia(WindowMedia):
            async def preprocess(self, source, output, parameters, context):
                assert parameters.max_width == width
                assert parameters.max_frames == CONFIG.max_input_frames
                assert (
                    parameters.interval_seconds.numerator == 1
                    and parameters.interval_seconds.denominator == 1
                )
                return await super().preprocess(source, output, parameters, context)

        store = await SqliteTimelineStore.open(project)
        try:
            await prepare_media(
                prepared(
                    source,
                    project,
                    config=replace(
                        CONFIG,
                        vision_prompt_version=prompt,
                        vision_prompt_hash=vision_prompt_fingerprint(prompt),
                    ),
                ),
                CapturingMedia(bundle),
                store,
                project,
                run_id=RUN_ID,
                asset=bundle.asset,
            )
        finally:
            await store.close()

    asyncio.run(scenario())


def test_coverage_counts_overlap_and_keeps_insufficient_config_without_invocations(tmp_path):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        config = replace(CONFIG, max_requests=2, max_input_frames=13)
        store = await SqliteTimelineStore.open(project)
        try:
            result = await prepare_media(
                prepared(source, project, config=config),
                WindowMedia(bundle),
                store,
                project,
                run_id=RUN_ID,
                asset=bundle.asset,
            )
            assert result.window_count == 3 and result.upload_frame_count == 15
            assert result.coverage_fits is False and await store.load_invocations(RUN_ID) == ()
            assert (await store.load_run(RUN_ID)).configuration.analysis == config
            assert (await store.load_run(RUN_ID)).status == RunStatus.PENDING
        finally:
            await store.close()

    asyncio.run(scenario())


def test_repeating_preparation_reuses_completed_media_and_original_configuration(tmp_path):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        media = WindowMedia(bundle)
        store = await SqliteTimelineStore.open(project)
        try:
            first = await prepare_media(
                prepared(source, project), media, store, project, run_id=RUN_ID, asset=bundle.asset
            )
            before = await store.load_run(RUN_ID)
            second = await prepare_media(
                prepared(source, project, resume=True), media, store, project, run_id=RUN_ID
            )
            after = await store.load_run(RUN_ID)
            assert first == second and media.calls == 1
            assert before.config_hash == after.config_hash
            assert (await store.load_checkpoints(RUN_ID))[0].attempt == 1
            assert await store.load_invocations(RUN_ID) == ()
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("cancelled", [False, True])
def test_failed_or_cancelled_preparation_can_resume_without_model_work(tmp_path, cancelled):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        outputs = []

        class InterruptedMedia(WindowMedia):
            async def preprocess(self, source, output, parameters, context):
                outputs.append(output)
                if cancelled:
                    raise asyncio.CancelledError
                raise AppError("media.timeout", "模拟超时。", ExitCode.INPUT)

        store = await SqliteTimelineStore.open(project)
        try:
            with pytest.raises(asyncio.CancelledError if cancelled else AppError):
                await prepare_media(
                    prepared(source, project),
                    InterruptedMedia(bundle),
                    store,
                    project,
                    run_id=RUN_ID,
                    asset=bundle.asset,
                )
            assert (await store.load_run(RUN_ID)).status == (
                RunStatus.CANCELLED if cancelled else RunStatus.FAILED
            )
            assert outputs[0].name.startswith("media-retry-")
            assert not (outputs[0] / "media-manifest.json").exists()
            result = await prepare_media(
                prepared(source, project, resume=True),
                WindowMedia(bundle),
                store,
                project,
                run_id=RUN_ID,
            )
            assert (
                result.image_count == 13 and (await store.load_checkpoints(RUN_ID))[0].attempt == 2
            )
            assert (await store.load_run(RUN_ID)).status == RunStatus.PENDING
            assert await store.load_invocations(RUN_ID) == ()
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change", ["path", "bytes", "config", "budget", "retry", "stage", "invocation", "completed"]
)
def test_offline_resume_refuses_source_changes_or_model_work_without_mutating_records(
    tmp_path, change
):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        try:
            media = WindowMedia(bundle)
            await prepare_media(
                prepared(source, project), media, store, project, run_id=RUN_ID, asset=bundle.asset
            )
            request = prepared(source, project, resume=True)
            if change == "path":
                other = tmp_path / "other.mp4"
                other.write_bytes(source.read_bytes())
                request = replace(request, video=other)
            elif change == "bytes":
                source.write_bytes(b"changed-source")
            elif change == "config":
                request = replace(request, config=replace(CONFIG, max_requests=99))
            elif change == "budget":
                request = replace(request, max_cost_cny=Decimal(99))
            elif change == "retry":
                request = replace(request, retry_uncertain=True)
            else:
                await store.begin_stage(RUN_ID, "asr", bundle.asset.sha256)
                if change == "invocation":
                    await store.begin_invocation(
                        "unknown-charge",
                        RUN_ID,
                        "asr",
                        "logical-asr",
                        replace(asr_metadata(), elapsed_ms=None),
                    )
                elif change == "completed":
                    await store.finish_stage(
                        RUN_ID, "asr", StageStatus.COMPLETED, bundle.asset.sha256
                    )
                    await store.begin_stage(RUN_ID, "vision", bundle.asset.sha256)
                    await store.finish_stage(
                        RUN_ID, "vision", StageStatus.COMPLETED, bundle.asset.sha256
                    )
                    await store.complete_run(RUN_ID)
            before = (
                await store.load_run(RUN_ID),
                await store.load_checkpoints(RUN_ID),
                await store.load_invocations(RUN_ID),
            )
            with pytest.raises(AppError):
                await prepare_media(request, media, store, project, run_id=RUN_ID)
            after = (
                await store.load_run(RUN_ID),
                await store.load_checkpoints(RUN_ID),
                await store.load_invocations(RUN_ID),
            )
            assert before == after and media.calls == 1
        finally:
            await store.close()

    asyncio.run(scenario())


def test_finish_preparation_cannot_hide_a_partial_or_started_analysis(tmp_path):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        try:
            await prepare_media(
                prepared(source, project),
                WindowMedia(bundle),
                store,
                project,
                run_id=RUN_ID,
                asset=bundle.asset,
            )
            await store.begin_stage(RUN_ID, "asr", bundle.asset.sha256)
            with pytest.raises(AppError) as refused:
                await store.finish_media_preparation(RUN_ID)
            assert refused.value.code == "storage.stage_state"
            assert (await store.load_run(RUN_ID)).status == RunStatus.RUNNING
        finally:
            await store.close()

    asyncio.run(scenario())
