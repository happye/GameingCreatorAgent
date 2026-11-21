"""Render verified overlay sprites as independent, transparent editing media."""

import json
from contextlib import suppress
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.creation_overlays import (
    CreationOverlays,
    OverlayItem,
    overlay_pixel_geometry,
)
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.media_process import MediaOutputLimit, run_media_process
from gamingcreator.infrastructure.overlay_assets import OverlayAsset

MAX_LAYER_BYTES = 96 * 1024 * 1024


def _layer_filter(item: OverlayItem, asset: OverlayAsset, width: int, height: int) -> str:
    x, y, sprite_width, sprite_height = overlay_pixel_geometry(
        item, width, height, asset.width, asset.height
    )
    filters = ["format=rgba", f"scale={sprite_width}:{sprite_height}"]
    frames = item.end_frame - item.start_frame
    if item.fade_in_frames:
        filters.append(f"fade=t=in:start_frame=0:nb_frames={item.fade_in_frames}:alpha=1")
    if item.fade_out_frames:
        filters.append(
            f"fade=t=out:start_frame={frames - item.fade_out_frames}:"
            f"nb_frames={item.fade_out_frames}:alpha=1"
        )
    filters.extend(
        [f"pad={width}:{height}:{x}:{y}:color=black@0", "setsar=1", "format=yuva444p10le"]
    )
    return ",".join(filters)


async def _verify_layer(
    bin_dir: Path,
    path: Path,
    frames: int,
    fps: int,
    width: int,
    height: int,
    context: CancellationContext,
) -> None:
    output = await run_media_process(
        [
            str(bin_dir / "ffprobe.exe"),
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-f",
            "mov",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,codec_name,codec_tag_string,pix_fmt,width,height,"
            "sample_aspect_ratio,r_frame_rate,nb_read_frames",
            "-of",
            "json",
            str(path),
        ],
        context,
        max_stdout_bytes=65_536,
    )
    streams = json.loads(output.stdout).get("streams", [])
    if len(streams) != 1:
        raise ValueError("图层交接需要单路透明视频。")
    stream = streams[0]
    if (
        stream.get("codec_type") != "video"
        or stream.get("codec_name") != "prores"
        or stream.get("codec_tag_string") != "ap4h"
        or not stream.get("pix_fmt", "").startswith("yuva444p")
        or (stream.get("width"), stream.get("height")) != (width, height)
        or stream.get("sample_aspect_ratio") != "1:1"
        or stream.get("r_frame_rate") != f"{fps}/1"
        or stream.get("nb_read_frames") != str(frames)
    ):
        raise ValueError("图层的帧数、尺寸、帧率或透明通道未通过校验。")


async def _encode_layer(
    bin_dir: Path,
    source: Path,
    filters: str,
    frames: int,
    fps: int,
    limit: MediaOutputLimit,
    context: CancellationContext,
) -> None:
    await run_media_process(
        [
            str(bin_dir / "ffmpeg.exe"),
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-protocol_whitelist",
            "file",
            "-f",
            "image2",
            "-pattern_type",
            "none",
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-c:v",
            "png",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-filter_threads",
            "1",
            "-vf",
            filters,
            "-frames:v",
            str(frames),
            "-c:v",
            "prores_ks",
            "-threads:v",
            "2",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            "-alpha_bits",
            "16",
            "-fs",
            str(limit.max_bytes),
            "-f",
            "mov",
            str(limit.path),
        ],
        context,
        output_limit=limit,
    )


async def render_overlay_layers(
    bin_dir: Path,
    directory: Path,
    overlays: CreationOverlays,
    assets: tuple[OverlayAsset, ...],
    total_frames: int,
    fps: int,
    width: int,
    height: int,
    context: CancellationContext,
) -> tuple[Path, ...]:
    """Produce one full-canvas ProRes 4444 MOV per layer, in stacking order."""
    overlays.validate_duration(total_frames)
    if type(fps) is not int or fps <= 0:
        raise ValueError("图层交接需要有效的帧率。")
    paths: list[Path] = []
    remaining = MAX_LAYER_BYTES
    try:
        for index, (item, asset) in enumerate(zip(overlays.items, assets, strict=True), 1):
            context.check_cancelled()
            if (item.asset_id, item.asset_receipt_sha256, item.kind) != (
                asset.asset_id,
                asset.receipt_sha256,
                asset.kind,
            ):
                raise ValueError("图层素材与登记身份不匹配。")
            path = directory / f"layer-{index:02}.mov"
            if path.exists() or is_link(path):
                raise ValueError("图层交接目标必须是新文件。")
            paths.append(path)
            frames = item.end_frame - item.start_frame
            limit = MediaOutputLimit(path, remaining, directory_max_bytes=MAX_LAYER_BYTES)
            await _encode_layer(
                bin_dir,
                asset.path,
                _layer_filter(item, asset, width, height),
                frames,
                fps,
                limit,
                context,
            )
            size = path.stat().st_size
            if not 0 < size < remaining:
                raise ValueError("图层交接超过容量上限或产物为空。")
            remaining -= size
            await _verify_layer(bin_dir, path, frames, fps, width, height, context)
    except BaseException:
        for path in paths:
            with suppress(OSError):
                path.unlink(missing_ok=True)
        raise
    return tuple(paths)
