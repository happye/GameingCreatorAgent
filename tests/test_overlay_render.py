"""Real frame oracle for output-clock sprites, fades, layering and music inputs."""

import asyncio
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest
from test_overlay_assets import chunk, png

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_audio import AudioMix, BgmSelection
from gamingcreator.domain.creation_overlays import CreationOverlays
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.infrastructure.music_library import MusicLibrary
from gamingcreator.infrastructure.overlay_assets import OverlayAsset, OverlayAssetLibrary
from gamingcreator.infrastructure.overlay_render import overlay_filters


def run(tool, args):
    return subprocess.run([str(tool), "-v", "error", *args], check=True, capture_output=True).stdout


async def render_scene(repository, with_music):
    tools = repository / ".tools/ffmpeg/bin"
    tools.mkdir(parents=True)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        shutil.copyfile(Path(".tools/ffmpeg/bin") / name, tools / name)
    ffmpeg = tools / "ffmpeg.exe"
    source = repository / "black.mp4"
    run(
        ffmpeg,
        ["-f", "lavfi", "-i", "color=black:s=160x96:r=10:d=2", "-pix_fmt", "yuv420p", str(source)],
    )
    context = CancellationContext("overlay-oracle", 60)
    library = OverlayAssetLibrary(repository)
    red = await library.register_png(png())
    blue_png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\0\0\xff\xff" * 2) * 2))
        + chunk(b"IEND", b"")
    )
    blue = await library.register_png(blue_png)
    item = dict(
        overlayId="a" * 32,
        kind="image",
        startFrame=4,
        endFrame=16,
        x=1000,
        y=1000,
        width=2000,
        fadeInFrames=4,
        fadeOutFrames=4,
        assetId=red.asset_id,
        assetReceiptSha256=red.receipt_sha256,
    )
    overlays = CreationOverlays.from_json(
        {
            "schemaVersion": "creation-overlays-v1",
            "items": [
                item,
                {
                    **item,
                    "overlayId": "b" * 32,
                    "assetId": blue.asset_id,
                    "assetReceiptSha256": blue.receipt_sha256,
                    "startFrame": 9,
                    "endFrame": 12,
                    "fadeInFrames": 0,
                    "fadeOutFrames": 0,
                },
            ],
        }
    )
    music, mix = None, AudioMix()
    if with_music:
        wav = repository / "tone.wav"
        run(ffmpeg, ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav)])
        music = await MusicLibrary(repository).register(
            wav, "Tone", "Generated", "user_declared", None, context
        )
        mix = AudioMix(bgm=BgmSelection(music.track_id, music.receipt_sha256, -12))
    media = await FfmpegMediaProcessor(repository).probe(source, context)
    plan = RenderPlan((RenderClip(media, SourceRange(0, 2_000_000, media.duration_us), 20),), 10)
    result = await FfmpegCreationRenderer(repository).render(
        plan,
        repository / "out",
        (source,),
        context,
        160,
        96,
        overlays=overlays,
        music=music,
        audio_mix=mix,
    )
    assert result["frames"] == 20 and result["overlays"] == overlays.to_json()
    return run(
        ffmpeg, ["-i", result["video"], "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "1", "-"]
    )


@pytest.mark.parametrize("with_music", [False, True])
def test_real_overlay_frames_geometry_fade_and_receipt(tmp_path, with_music):
    raw = asyncio.run(render_scene(tmp_path, with_music))
    assert len(raw) == 20 * 160 * 96 * 3

    def pixel(frame, x=24, y=20):
        offset = (frame * 160 * 96 + y * 160 + x) * 3
        return tuple(raw[offset : offset + 3])

    for frame in (0, 3, 4, 16, 19):
        assert max(pixel(frame)) < 15, (frame, pixel(frame))
    for frame in (6, 14):
        assert 105 < pixel(frame)[0] < 150, (frame, pixel(frame))
    assert pixel(8)[0] > 235 and max(pixel(8)[1:]) < 15
    assert pixel(9)[2] > 235 and max(pixel(9)[:2]) < 15
    assert pixel(11)[2] > 235
    assert pixel(12)[0] > 235
    assert 40 < pixel(15)[0] < 85
    assert max(pixel(8, 5, 5)) < 15


def test_real_compositor_keeps_odd_pixel_coordinates():
    item = dict(
        overlayId="a" * 32,
        kind="image",
        startFrame=0,
        endFrame=1,
        x=4250,
        y=3667,
        width=1000,
        fadeInFrames=0,
        fadeOutFrames=0,
        assetId="b" * 32,
        assetReceiptSha256="c" * 64,
    )
    overlays = CreationOverlays.from_json(
        {"schemaVersion": "creation-overlays-v1", "items": [item]}
    )
    asset = OverlayAsset("b" * 32, "c" * 64, "image", 2, 2, Path("unused.png"))
    _, graph = overlay_filters(overlays, (asset,), 1, 1, 1, 40, 30, "null", "")
    raw = run(
        Path(".tools/ffmpeg/bin/ffmpeg.exe"),
        [
            "-f",
            "lavfi",
            "-i",
            "color=black:s=40x30:r=1:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=4x4:r=1:d=1,format=rgba",
            "-filter_complex_threads",
            "1",
            "-filter_complex",
            graph,
            "-map",
            "[overlay-video]",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
    )
    points = [(x, y) for y in range(30) for x in range(40) if raw[(y * 40 + x) * 3] > 180]
    assert (min(x for x, _ in points), min(y for _, y in points)) == (17, 11)
    assert (max(x for x, _ in points), max(y for _, y in points)) == (20, 14)
