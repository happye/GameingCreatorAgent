"""Temporal profiles preserve source coverage and versioned resumable runs."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_analyze import RUN_ID, ScriptedAsr, asr_metadata, asr_result
from test_analyze_v2 import CONFIG, WindowMedia, WindowVision, window_bundle

from gamingcreator.application.analysis import (
    AnalysisPorts,
    resume_analysis,
    run_new_analysis,
    vision_windows,
)
from gamingcreator.application.inputs import PreparedAnalyze
from gamingcreator.application.providers import ProviderCapabilities, ProviderStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.local_files import LocalInputReader
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

TEMPORAL = replace(
    CONFIG,
    sampling_interval_ms=500,
    window_frames=9,
    window_overlap=2,
    vision_prompt_version="phase0-vision-v3",
    vision_prompt_hash="0" * 64,
)


def test_dense_windows_cover_the_source_and_keep_temporal_overlap(tmp_path: Path) -> None:
    bundle, _, _ = window_bundle(tmp_path)
    windows = vision_windows(bundle, TEMPORAL)
    assert [len(window) for window in windows] == [9, 6]
    assert windows[0][-2:] == windows[1][:2]
    assert {item.evidence_id for window in windows for item in window} == {
        image.evidence_id for image in bundle.images
    }
    assert all(
        first.source_time.time_us < second.source_time.time_us
        for window in windows
        for first, second in zip(window, window[1:], strict=False)
    )


@pytest.mark.parametrize(
    "prompt_version",
    ["phase0-vision-v3", "phase0-vision-v4", "phase0-vision-v5", "phase0-vision-v6"],
)
def test_temporal_run_resumes_only_missing_windows_with_new_pipeline_identity(
    tmp_path: Path,
    prompt_version: str,
) -> None:
    profile = replace(TEMPORAL, vision_prompt_version=prompt_version)

    class TemporalVision(WindowVision):
        capabilities = ProviderCapabilities(
            image_sequence=True, structured_output=True, max_images=9, max_image_width=1280
        )

        async def analyze(self, request, context):
            assert request.prompt_version == prompt_version
            assert request.schema_version == (
                "temporal-actions-v1"
                if prompt_version in ("phase0-vision-v4", "phase0-vision-v5", "phase0-vision-v6")
                else "semantic-events-v1"
            )
            assert len(request.evidence) in (9, 6)
            return await super().analyze(request, context)

    async def scenario() -> None:
        bundle, project, source = window_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)

        class CheckedMedia(WindowMedia):
            async def preprocess(self, source, output, parameters, context):
                assert parameters.max_width == (
                    1280 if prompt_version in ("phase0-vision-v5", "phase0-vision-v6") else 512
                )
                return await super().preprocess(source, output, parameters, context)

        media = CheckedMedia(bundle)
        asr = ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO))
        vision = TemporalVision("vision-000001")
        try:
            with pytest.raises(AppError, match="视觉窗口"):
                await run_new_analysis(
                    PreparedAnalyze(source, project, profile, Decimal(5), None),
                    AnalysisPorts(media, asr, vision, store, lambda request: asr_metadata()),
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                )
            stored = await store.load_run(RUN_ID)
            expected_version = {
                "phase0-vision-v5": "phase0-analyze-detailed-v1",
                "phase0-vision-v6": "phase0-analyze-detailed-v2",
            }.get(prompt_version, "phase0-analyze-temporal-v1")
            assert stored.configuration.pipeline_version == expected_version
            assert stored.configuration.analysis == profile
            resumed = TemporalVision()
            result = await resume_analysis(
                PreparedAnalyze(source, project, None, None, RUN_ID),
                store,
                project,
                AnalysisPorts(media, asr, resumed, store, lambda request: asr_metadata()),
            )
            assert resumed.stages == ["vision-000001"]
            assert media.calls == asr.calls == 1
            assert result.event_count == 2
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("prompt", "frames", "overlap", "accepted"),
    [
        ("phase0-vision-v3", 9, 2, True),
        ("phase0-vision-v4", 9, 2, True),
        ("phase0-vision-v4", 10, 2, False),
        ("phase0-vision-v5", 9, 2, True),
        ("phase0-vision-v5", 1, 0, False),
        ("phase0-vision-v5", 10, 2, False),
        ("phase0-vision-v6", 9, 2, True),
        ("phase0-vision-v6", 1, 0, False),
        ("phase0-vision-v6", 10, 2, False),
        ("phase0-vision-v3", 2, 1, True),
        ("phase0-vision-v3", 1, 0, False),
        ("phase0-vision-v3", 10, 2, False),
        ("phase0-vision-v3", 9, 9, False),
        ("phase0-vision-v2", 9, 2, False),
        ("phase0-vision-v2", 5, 1, True),
    ],
)
def test_config_enables_larger_windows_only_for_temporal_prompt(
    tmp_path: Path, prompt: str, frames: int, overlap: int, accepted: bool
) -> None:
    raw = {
        "schemaVersion": 2,
        "vision": {
            "provider": "deepseek",
            "model": "deepseek-flash",
            "priceVersion": "deepseek-flash-cny-2026-10-04",
            "maxOutputTokens": 2048,
            "promptVersion": prompt,
            "promptHash": "0" * 64,
        },
        "sampling": {"intervalMs": 500, "windowFrames": frames, "windowOverlap": overlap},
        "limits": {"maxRequests": 10, "maxInputFrames": 100},
        "asr": {"language": "zh"},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    if accepted:
        config = LocalInputReader().load_config(path)
        assert config.window_frames == frames and config.vision_prompt_version == prompt
    else:
        with pytest.raises(AppError, match="配置文件无效"):
            LocalInputReader().load_config(path)


def test_detailed_profile_pins_a_new_prompt_and_preserves_previous_example() -> None:
    from gamingcreator.infrastructure.deepseek_vision import vision_prompt_fingerprint

    repository = Path(__file__).resolve().parents[1]
    detailed = LocalInputReader().load_config(repository / "config.detailed.example.json")
    legacy = LocalInputReader().load_config(repository / "config.temporal.example.json")
    assert detailed.vision_prompt_version == "phase0-vision-v5"
    assert detailed.vision_prompt_hash == vision_prompt_fingerprint("phase0-vision-v5")
    assert detailed.max_output_tokens == 4096
    assert legacy.vision_prompt_version == "phase0-vision-v4"
    assert legacy.vision_prompt_hash == vision_prompt_fingerprint("phase0-vision-v4")
