"""Real ProRes overlay layers must preserve opacity and output-clock geometry."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from test_overlay_assets import png

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.creation_overlays import CreationOverlays, OverlayItem
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.overlay_assets import OverlayAsset
from gamingcreator.infrastructure.overlay_handoff import render_overlay_layers

TOOLS = Path(__file__).resolve().parents[1] / ".tools/ffmpeg/bin"


def sprite(tmp_path: Path) -> tuple[OverlayItem, OverlayAsset]:
    path = tmp_path / "sprite.png"
    path.write_bytes(png(4, 3))
    asset = OverlayAsset("b" * 32, "c" * 64, "image", 4, 3, path)
    # Scaling 4×3 to 10×8 forces the filter to normalize the sample aspect ratio.
    item = OverlayItem(
        "a" * 32, "image", 4, 12, 4250, 3667, 2500, 2, 2, asset.asset_id, asset.receipt_sha256
    )
    return item, asset


def test_real_overlay_layers_keep_transparency_fades_and_order(tmp_path: Path) -> None:
    item, asset = sprite(tmp_path)
    other = replace(
        item,
        overlay_id="d" * 32,
        start_frame=3,
        end_frame=5,
        x=0,
        y=0,
        fade_in_frames=0,
        fade_out_frames=0,
    )
    directory = tmp_path / "layers"
    directory.mkdir()

    async def encode():
        context = CancellationContext("overlay-handoff", 30)
        paths = await render_overlay_layers(
            TOOLS,
            directory,
            CreationOverlays((item, other)),
            (asset, asset),
            20,
            10,
            40,
            30,
            context,
        )
        decoded = []
        for path in paths:
            output = await run_media_process(
                [
                    str(TOOLS / "ffmpeg.exe"),
                    "-v",
                    "error",
                    "-i",
                    str(path),
                    "-vf",
                    "format=rgba",
                    "-threads",
                    "1",
                    "-f",
                    "rawvideo",
                    "-",
                ],
                context,
            )
            decoded.append(output.stdout)
        return paths, decoded

    paths, (main, extra) = asyncio.run(encode())
    assert [path.name for path in paths] == ["layer-01.mov", "layer-02.mov"]
    assert len(main) == 8 * 40 * 30 * 4 and len(extra) == 2 * 40 * 30 * 4

    def alpha(raw: bytes, frame: int, x: int, y: int) -> int:
        return raw[((frame * 30 + y) * 40 + x) * 4 + 3]

    assert alpha(main, 2, 16, 11) == alpha(main, 2, 17, 10) == 0
    assert [alpha(main, frame, 17, 11) for frame in (0, 2, 6)] == [0, 255, 255]
    assert all(120 <= alpha(main, frame, 17, 11) <= 136 for frame in (1, 7))
    assert alpha(extra, 0, 0, 0) == 255 and alpha(extra, 0, 17, 11) == 0


def test_existing_target_is_untouched_and_completed_layers_are_removed(tmp_path: Path) -> None:
    item, asset = sprite(tmp_path)
    directory = tmp_path / "layers"
    directory.mkdir()
    existing = directory / "layer-02.mov"
    existing.write_bytes(b"original")
    with pytest.raises(ValueError, match="新文件"):
        asyncio.run(
            render_overlay_layers(
                TOOLS,
                directory,
                CreationOverlays((item, replace(item, overlay_id="d" * 32))),
                (asset, asset),
                20,
                10,
                40,
                30,
                CancellationContext("overlay-cleanup", 30),
            )
        )
    assert list(directory.iterdir()) == [existing] and existing.read_bytes() == b"original"
