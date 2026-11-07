"""Real output-clock oracle across speed, crossfade, CJK and final decorations."""

import asyncio
import shutil
import struct
import subprocess
import zlib
from fractions import Fraction
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_overlays import CreationOverlays
from gamingcreator.domain.creation_presentation import PresentationOptions
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary

WIDTH, HEIGHT, FPS = 320, 180, 30


def tool(ffmpeg, *args):
    return subprocess.run(
        [str(ffmpeg), "-v", "error", *map(str, args)], check=True, capture_output=True
    ).stdout


def red_png():
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 9, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\0\0\xff" * 16) * 9))
        + chunk(b"IEND", b"")
    )


async def registered_overlays(repository):
    library = OverlayAssetLibrary(repository)
    red = await library.register_png(red_png())
    text = await library.register_text("组合字幕测试")
    common = dict(x=0, y=0, width=10000, fadeInFrames=0, fadeOutFrames=0)
    return CreationOverlays.from_json(
        {
            "schemaVersion": "creation-overlays-v1",
            "items": [
                dict(
                    common,
                    overlayId="a" * 32,
                    kind="image",
                    startFrame=48,
                    endFrame=64,
                    assetId=red.asset_id,
                    assetReceiptSha256=red.receipt_sha256,
                ),
                dict(
                    common,
                    overlayId="b" * 32,
                    kind="text",
                    text=text.text,
                    startFrame=52,
                    endFrame=62,
                    x=2500,
                    y=3000,
                    width=5000,
                    assetId=text.asset_id,
                    assetReceiptSha256=text.receipt_sha256,
                ),
            ],
        }
    )


async def render_composition(repository):
    tools = repository / ".tools/ffmpeg/bin"
    tools.mkdir(parents=True)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        shutil.copyfile(Path(".tools/ffmpeg/bin") / name, tools / name)
    ffmpeg = tools / "ffmpeg.exe"
    paths = []
    for color in ("green", "blue"):
        path = repository / f"{color}.mkv"
        tool(
            ffmpeg,
            "-f",
            "lavfi",
            "-i",
            f"color={color}:s=320x180:r=30:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            path,
        )
        paths.append(path)
    context = CancellationContext("overlay-composition", 120)
    processor = FfmpegMediaProcessor(repository)
    assets = [await processor.probe(path, context) for path in paths]
    clips = tuple(
        RenderClip(asset, SourceRange(0, 1_000_000, asset.duration_us), frames, speed)
        for asset, frames, speed in zip(
            assets, (60, 15), (Fraction(1, 2), Fraction(2)), strict=True
        )
    )
    plan = RenderPlan(clips, FPS, (0, 6))
    assert plan.start_frames == (0, 54) and plan.frames == 69
    overlays = await registered_overlays(repository)
    renderer = FfmpegCreationRenderer(repository)
    outputs = {}
    for name in ("bare", "sprites", "decorated"):
        decorated = name == "decorated"
        result = await renderer.render(
            plan,
            repository / name,
            tuple(paths),
            context,
            WIDTH,
            HEIGHT,
            overlays=overlays if name != "bare" else None,
            cues=(SubtitleCue(Fraction(0), Fraction(69, FPS), "BURN SUBTITLE"),)
            if decorated
            else (),
            subtitle_mode="burn" if decorated else "none",
            watermark="WATERMARK" if decorated else None,
            presentation=PresentationOptions(badge_text="BADGE", badge_corner="top-left")
            if decorated
            else None,
        )
        assert result["frames"] == 69 and result["videoDuration"] == "23/10"
        if name != "bare":
            assert result["overlays"] == overlays.to_json()
        outputs[name] = tool(
            ffmpeg,
            "-i",
            result["video"],
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-threads",
            "1",
            "-",
        )
    return outputs


def pixel(raw, frame, x, y):
    offset = (frame * WIDTH * HEIGHT + y * WIDTH + x) * 3
    return tuple(raw[offset : offset + 3])


def bright_pixels(raw, frame, box, threshold):
    left, top, right, bottom = box
    return sum(
        min(pixel(raw, frame, x, y)) > threshold
        for y in range(top, bottom)
        for x in range(left, right)
    )


def test_real_mixed_speed_crossfade_overlay_and_decoration_order(tmp_path):
    outputs = asyncio.run(render_composition(tmp_path))
    for raw in outputs.values():
        assert len(raw) == 69 * WIDTH * HEIGHT * 3
    bare, sprites, decorated = (outputs[name] for name in ("bare", "sprites", "decorated"))
    # Green slow clip lasts 60 frames; the fast blue clip begins at frame 54.
    assert pixel(bare, 48, 160, 100)[1] > 110
    red, green, blue = pixel(bare, 57, 160, 100)
    assert red < 15 and green > 35 and blue > 80
    assert pixel(bare, 63, 160, 100)[2] > 235
    # Output-frame [48,64) covers slow footage, the entire crossfade and fast footage.
    assert pixel(sprites, 47, 160, 100)[1] > 110
    for frame in (48, 51, 54, 57, 59, 60, 63):
        red, green, blue = pixel(sprites, frame, 160, 100)
        assert red > 235 and max(green, blue) < 15, (frame, (red, green, blue))
    assert pixel(sprites, 64, 160, 100)[2] > 235
    assert pixel(sprites, 68, 160, 100)[2] > 235
    # The registered Chinese transparent sprite is independently timed [52,62).
    text_box = (80, 54, 240, 94)
    for frame in (51, 62):
        assert bright_pixels(sprites, frame, text_box, 200) == 0
    for frame in (52, 57, 61):
        assert bright_pixels(sprites, frame, text_box, 200) > 50
    # The full-canvas opaque red PNG would hide these decorations if ordered last.
    for box, threshold in (
        ((0, 0, 100, 35), 200),  # opaque top-left badge
        ((200, 0, 320, 35), 90),  # semi-transparent top-right watermark
        ((60, 145, 260, 180), 200),  # bottom burned subtitle
    ):
        assert bright_pixels(sprites, 57, box, threshold) == 0
        assert bright_pixels(decorated, 57, box, threshold) > 10, (box, threshold)
    assert bright_pixels(decorated, 57, text_box, 200) > 50
