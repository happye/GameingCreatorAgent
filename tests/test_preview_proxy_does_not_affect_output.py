"""B12: after preview uses a proxy, frame grabs and renders still read the original."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from test_preview_clock_align_browser import plant_playable_proxy

from gamingcreator.application.browser_source_clock import runtime_clock_document
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan, output_start_frames
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_fullres import FfmpegFullResolutionFrames
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.infrastructure.ffmpeg_shots import FfmpegShotDetector
from gamingcreator.infrastructure.proxy_media import (
    is_editing_proxy_file,
    load_proxy_receipt,
    reject_editing_proxy_source,
)

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
PREVIEW_JS = ROOT / "src/gamingcreator/ui/static/studio/preview.js"


def run_tool(*arguments: object) -> bytes:
    return subprocess.run(
        [str(FFMPEG), "-v", "error", "-nostdin", "-n", *map(str, arguments)],
        check=True,
        capture_output=True,
    ).stdout


def make_color(
    path: Path, color: str, duration: float = 2, rate: int = 30, offset: float | None = None
) -> None:
    arguments = ["-f", "lavfi", "-i", f"color=c={color}:s=64x48:r={rate}:d={duration}"]
    if offset is not None:
        arguments += ["-output_ts_offset", str(offset)]
    run_tool(*arguments, "-c:v", "libx264", "-pix_fmt", "yuv420p", path)


def first_pixel(path: Path) -> bytes:
    pixel = run_tool(
        "-i",
        path,
        "-frames:v",
        "1",
        "-vf",
        "scale=1:1",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "-",
    )
    assert len(pixel) == 3
    return pixel


def is_red(pixel: bytes) -> bool:
    red, green, blue = pixel
    return red > blue + 100 and red > green + 100


def is_blue(pixel: bytes) -> bool:
    red, green, blue = pixel
    return blue > red + 100 and blue > green + 100


async def planted_project(tmp_path: Path, context: CancellationContext):
    original = tmp_path / "original-red.mp4"
    proxy_body = tmp_path / "proxy-blue.mp4"
    make_color(original, "red", offset=2.5)
    make_color(proxy_body, "blue")
    assert is_red(first_pixel(original))
    assert is_blue(first_pixel(proxy_body))
    asset = await FfmpegMediaProcessor(ROOT).probe(original, context)
    plant_playable_proxy(
        tmp_path,
        original,
        asset.sha256,
        asset.duration_us,
        body=proxy_body.read_bytes(),
    )
    receipt = load_proxy_receipt(tmp_path, asset.sha256)
    assert receipt is not None
    proxy = Path(receipt["path"])
    assert is_editing_proxy_file(proxy)
    assert not is_editing_proxy_file(original)
    return original, proxy, asset


def test_output_clock_rule_is_unchanged():
    # Official JS editTimeline: out -= transitionIn.frames, then start = out, then out += frames.
    assert output_start_frames((30, 30, 24), (0, 10, 6)) == (0, 20, 44)
    text = PREVIEW_JS.read_text(encoding="utf-8")
    assert "out -= clip.transitionIn?.frames || 0;" in text
    assert (
        "BigInt(clip.endUs - clip.startUs) * BigInt(fps) * BigInt(denominator)) "
        "/ (1000000n * BigInt(numerator))"
    ) in text.replace("\n", " ")


def test_frame_grab_and_render_use_original_when_a_different_proxy_exists(tmp_path):
    async def scenario():
        context = CancellationContext("b12-proxy-output", 90)
        original, proxy, asset = await planted_project(tmp_path, context)
        official = runtime_clock_document(asset)
        proxy_clock = runtime_clock_document(await FfmpegMediaProcessor(ROOT).probe(proxy, context))
        assert official["originUs"] >= 2_000_000
        assert proxy_clock["originUs"] < 500_000
        assert official["originUs"] != proxy_clock["originUs"]

        frames = await FfmpegFullResolutionFrames(ROOT).extract(
            asset, Fraction(1, 2), 1, tmp_path / "fullres", context
        )
        assert len(frames) == 1
        grabbed = first_pixel(frames[0][2])
        assert is_red(grabbed)
        assert not is_blue(grabbed)
        assert is_blue(first_pixel(proxy))

        plan = RenderPlan(
            (RenderClip(asset, SourceRange(0, 500_000, asset.duration_us), 15),),
            30,
        )
        rendered = tmp_path / "rendered"
        result = await FfmpegCreationRenderer(ROOT).render(
            plan, rendered, (original,), context, 64, 48
        )
        assert result["frames"] == 15
        pixel = first_pixel(rendered / "video.mp4")
        assert is_red(pixel)
        assert not is_blue(pixel)
        assert asset.source_path.resolve() == original.resolve()

    asyncio.run(scenario())


def test_forged_proxy_source_is_rejected_for_grab_shots_and_render(tmp_path):
    async def scenario():
        context = CancellationContext("b12-proxy-reject", 90)
        original, proxy, asset = await planted_project(tmp_path, context)
        forged = replace(asset, source_path=proxy)
        with pytest.raises(AppError, match="不能使用编辑代理"):
            reject_editing_proxy_source(proxy)
        with pytest.raises(AppError, match="不能使用编辑代理"):
            await FfmpegFullResolutionFrames(ROOT).extract(
                forged, Fraction(1, 2), 1, tmp_path / "fullres-forged", context
            )
        with pytest.raises(AppError, match="不能使用编辑代理"):
            await FfmpegShotDetector(ROOT).samples(forged, context)
        plan = RenderPlan(
            (RenderClip(forged, SourceRange(0, 500_000, forged.duration_us), 15),),
            30,
        )
        with pytest.raises(AppError, match="不能使用编辑代理"):
            await FfmpegCreationRenderer(ROOT).render(
                plan, tmp_path / "forged-render", (original,), context, 64, 48
            )
        reject_editing_proxy_source(original)

    asyncio.run(scenario())
