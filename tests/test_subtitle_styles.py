"""Burned subtitle styles: standard stays byte-identical; large/boxed are real FFmpeg output."""

import asyncio
from fractions import Fraction

import pytest
from test_creation_render import ROOT, run_tool
from test_creation_subtitles import speech

from gamingcreator.application.creation_subtitles import build_subtitles
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_presentation import PresentationOptions
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import (
    FfmpegCreationRenderer,
    _burn_ass,
    burn_events,
)
from gamingcreator.ui.creation_jobs import expected_presentation_receipt

LEGACY_STYLE = (
    "Style: Default,Arial,60,&H00FFFFFF,&H00FFFFFF,&H00000000,"
    "&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,4,4,4,1\n"
)


def test_style_options_and_receipt():
    assert PresentationOptions.from_request({"subtitleMode": "burn"}) is None
    standard = PresentationOptions.from_request({"subtitleStyle": "standard"})
    assert standard is not None and not standard.enabled and standard.receipt() is None
    boxed = PresentationOptions.from_request({"subtitleStyle": "boxed"})
    assert boxed is not None and boxed.receipt()["subtitleStyle"] == "boxed"
    assert PresentationOptions.from_json(boxed.to_json()) == boxed
    with pytest.raises(ValueError):
        PresentationOptions(subtitle_style="neon")


def test_standard_ass_line_is_unchanged_and_styles_differ():
    cue = (SubtitleCue(Fraction(0), Fraction(1), "字幕"),)
    assert LEGACY_STYLE in _burn_ass(cue, 1920, 1080)
    assert _burn_ass(cue, 1920, 1080) == _burn_ass(cue, 1920, 1080, "standard")
    assert "Arial,83,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1," in _burn_ass(
        cue, 1920, 1080, "large"
    )
    assert ",0,0,3,6,0,2," in _burn_ass(cue, 1920, 1080, "boxed")


def test_font_and_rgb_style_are_frozen_only_for_burned_cues():
    request = {"subtitleStyle": "boxed", "subtitleFont": "simsun", "subtitleColor": "#44e0ff"}
    presentation = PresentationOptions.from_request(request)
    assert presentation is not None
    assert PresentationOptions.from_json(presentation.to_json()) == presentation
    actual = expected_presentation_receipt(request, True)
    assert actual is not None and all(actual[field] == value for field, value in request.items())
    assert expected_presentation_receipt(request, False) is None
    cue = (SubtitleCue(Fraction(0), Fraction(1), "中文"),)
    ass = _burn_ass(cue, 1920, 1080, "boxed", font="simsun", color="#44e0ff")
    assert "SimSun,60,&H00FFE044,&H00FFE044," in ass


@pytest.mark.parametrize(
    "request_fields", [{"subtitleFont": "System,Foo"}, {"subtitleColor": "#44e0ff\n"}]
)
def test_custom_presentation_rejects_noncanonical_ass_fields(request_fields):
    with pytest.raises(ValueError):
        PresentationOptions.from_request(request_fields)


def test_ass_text_between_output_frames_is_not_counted():
    cue = (SubtitleCue(Fraction(1, 100), Fraction(2, 100), "短字幕"),)
    assert list(burn_events(cue))
    assert not list(burn_events(cue, (30, 30)))


def test_real_burn_styles_change_pixels(tmp_path):
    source = tmp_path / "white.mp4"
    run_tool(
        ["-f", "lavfi", "-i", "color=c=white:s=320x180:r=10:d=1", "-c:v", "libx264", str(source)]
    )

    async def dark_pixels(style):
        context = CancellationContext("subtitle-style", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        plan = RenderPlan(
            (RenderClip(asset, SourceRange(0, 1_000_000, asset.duration_us), 10),), 10
        )
        cues = build_subtitles(plan, (speech(200_000, 700_000, "本地字幕样式", asset.media_id),))
        output = tmp_path / style
        result = await FfmpegCreationRenderer(ROOT).render(
            plan,
            output,
            (source,),
            context,
            320,
            180,
            "",
            cues,
            "burn",
            presentation=PresentationOptions(subtitle_style=style),
        )
        assert result.get("presentation", {}).get("subtitleStyle") == (
            None if style == "standard" else style
        )
        pixels = run_tool(
            ["-i", str(output / "video.mp4"), "-pix_fmt", "gray", "-f", "rawvideo", "-"]
        )
        frame = pixels[4 * 320 * 180 : 5 * 320 * 180]  # 0.4 s, cue visible
        assert len(frame) == 320 * 180
        # The translucent box blends with white, so include greys as well as the dark outline.
        return sum(value < 160 for value in frame[120 * 320 :])

    async def alternative_cues(name, segment_cues=(), burn_cues=()):
        context = CancellationContext("subtitle-style-empty", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        plan = RenderPlan(
            (RenderClip(asset, SourceRange(0, 1_000_000, asset.duration_us), 10),), 10
        )
        return await FfmpegCreationRenderer(ROOT).render(
            plan,
            tmp_path / name,
            (source,),
            context,
            320,
            180,
            "",
            segment_cues,
            "burn",
            burn_cues=burn_cues,
            presentation=PresentationOptions(subtitle_font="simsun", subtitle_color="#44e0ff"),
        )

    # Nothing burned: the receipt must not claim a subtitle style.
    assert "presentation" not in asyncio.run(alternative_cues("empty"))
    words = (SubtitleCue(Fraction(1, 5), Fraction(7, 10), "逐词字幕"),)
    word_only = asyncio.run(alternative_cues("word-only", burn_cues=words))
    assert word_only["subtitles"] == {"mode": "burn", "cueCount": 0, "burnedCueCount": 1}
    assert word_only["presentation"]["subtitleColor"] == "#44e0ff"
    short = (SubtitleCue(Fraction(1, 1000), Fraction(9, 1000), "不足一厘秒"),)
    srt_only = asyncio.run(alternative_cues("srt-only", segment_cues=short, burn_cues=short))
    assert srt_only["subtitles"] == {"mode": "burn", "cueCount": 1, "burnedCueCount": 0}
    assert "presentation" not in srt_only
    counts = {style: asyncio.run(dark_pixels(style)) for style in ("standard", "large", "boxed")}
    assert counts["standard"] > 0
    assert counts["large"] > counts["standard"] * 1.5
    assert counts["boxed"] > counts["standard"] * 2
