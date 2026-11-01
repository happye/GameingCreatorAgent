"""Byte-capped safe-area crop and static corner badge presentation tests."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_presentation import (
    PresentationOptions,
    safe_area_crop_filter,
)
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"


def run_tool(arguments: list[str]) -> None:
    subprocess.run(
        [str(FFMPEG), "-v", "error", "-nostdin", "-n", *arguments],
        check=True,
        capture_output=True,
    )


def test_safe_area_crop_filter_even_dims() -> None:
    assert safe_area_crop_filter(320, 180, 0) == ""
    assert safe_area_crop_filter(320, 180, 10) == "crop=256:144:32:18,scale=320:180"


def test_presentation_options_reject_bad_values() -> None:
    with pytest.raises(ValueError):
        PresentationOptions(safe_area_margin_percent=41)
    with pytest.raises(ValueError):
        PresentationOptions(badge_text="x" * 25)
    with pytest.raises(ValueError):
        PresentationOptions(badge_text="bad{text}")
    with pytest.raises(ValueError):
        PresentationOptions(badge_text="ok", badge_corner="middle")


def test_presentation_from_request_omits_when_absent() -> None:
    assert PresentationOptions.from_request({"requestId": "a"}) is None
    options = PresentationOptions.from_request({"safeAreaMarginPercent": 5, "badgeText": "DEMO"})
    assert options is not None
    assert options.safe_area_margin_percent == 5
    assert options.badge_text == "DEMO"
    assert options.badge_corner == "bottom-left"


def test_real_render_safe_area_and_badge_receipt(tmp_path: Path) -> None:
    source = tmp_path / "black.mp4"
    run_tool(
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:r=10:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ]
    )

    async def scenario() -> dict[str, object]:
        context = CancellationContext("presentation-render", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        plan = RenderPlan((RenderClip(asset, SourceRange(0, 500_000, asset.duration_us), 5),), 10)
        presentation = PresentationOptions(10, "DEMO", "bottom-left")
        return await FfmpegCreationRenderer(ROOT).render(
            plan,
            tmp_path / "out",
            (source,),
            context,
            320,
            180,
            presentation=presentation,
        )

    result = asyncio.run(scenario())
    assert result["presentation"] == {
        "version": "creation-presentation-v1",
        "safeArea": {"marginPercent": 10},
        "badge": {"text": "DEMO", "corner": "bottom-left"},
    }
    assert "safe-area center crop then scale" in result["limitations"]
    assert "static corner badge overlay" in result["limitations"]
    video = Path(str(result["video"]))
    assert video.is_file()
    assert video.stat().st_size < 500_000
    frame = subprocess.run(
        [
            str(FFMPEG),
            "-v",
            "error",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert len(frame) == 320 * 180
    bottom_left = max(frame[y * 320 + x] for y in range(140, 180) for x in range(0, 120))
    top_right = max(frame[y * 320 + x] for y in range(0, 40) for x in range(200, 320))
    center = max(frame[y * 320 + x] for y in range(70, 110) for x in range(120, 200))
    assert bottom_left > 60
    assert bottom_left > top_right + 20
    assert bottom_left > center + 20


def test_real_render_without_presentation_omits_receipt_field(tmp_path: Path) -> None:
    source = tmp_path / "black.mp4"
    run_tool(
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x48:r=10:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ]
    )

    async def scenario() -> dict[str, object]:
        context = CancellationContext("plain-render", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        plan = RenderPlan((RenderClip(asset, SourceRange(0, 500_000, asset.duration_us), 5),), 10)
        return await FfmpegCreationRenderer(ROOT).render(
            plan, tmp_path / "plain", (source,), context, 64, 48
        )

    result = asyncio.run(scenario())
    assert "presentation" not in result
    assert result["limitations"][2] == "no overlays"
    assert Path(str(result["video"])).stat().st_size < 200_000
