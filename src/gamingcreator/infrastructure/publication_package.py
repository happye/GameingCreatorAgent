"""Pinned local media transforms and measured package facts."""

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.ffmpeg_render import _filter_path, _watermark_ass
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.publication_assets import validate_png


def transform(value: dict[str, Any]) -> str:
    w, h = value["width"], value["height"]
    if value["fit"] == "crop":
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"


async def encode(
    repository: Path,
    video: Path,
    cover: Path,
    target: Path,
    profile: dict[str, Any],
    watermark: str | None = None,
    duration: Fraction | None = None,
) -> dict[str, Any]:
    """``watermark`` is redrawn after cropping/padding, so a package never loses the mark."""
    tools = repository / ".tools/ffmpeg/bin"
    video_filter = transform(profile["Fields"]["video"])
    mark = target / "watermark.ass"
    if watermark is not None:
        field = profile["Fields"]["video"]
        mark.write_text(
            _watermark_ass(
                watermark, field["width"], field["height"], duration or Fraction(359999)
            ),
            encoding="utf-8",
        )
        video_filter += f",ass=filename={_filter_path(mark)}"
    try:
        return await _encode(tools, video, cover, target, profile, video_filter)
    finally:
        mark.unlink(missing_ok=True)


async def _encode(
    tools: Path,
    video: Path,
    cover: Path,
    target: Path,
    profile: dict[str, Any],
    video_filter: str,
) -> dict[str, Any]:
    context = CancellationContext("platform-package", 1800)
    base = [
        str(tools / "ffmpeg.exe"),
        "-v",
        "error",
        "-xerror",
        "-nostdin",
        "-protocol_whitelist",
        "file,pipe",
    ]
    await run_media_process(
        [
            *base,
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-vf",
            video_filter,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-fps_mode",
            "passthrough",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "-n",
            str(target / "video.mp4"),
        ],
        context,
    )
    await run_media_process(
        [
            *base,
            "-i",
            str(cover),
            "-vf",
            transform(profile["Fields"]["cover"]),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-n",
            str(target / "cover.png"),
        ],
        context,
    )
    validate_png(
        target / "cover.png",
        profile["Fields"]["cover"]["width"],
        profile["Fields"]["cover"]["height"],
    )
    for name in ("video.mp4", "cover.png"):
        await run_media_process([*base, "-i", str(target / name), "-f", "null", "-"], context)
    result = await run_media_process(
        [
            str(tools / "ffprobe.exe"),
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(target / "video.mp4"),
        ],
        context,
    )
    data = json.loads(result.stdout)
    stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    num, den = map(int, stream["r_frame_rate"].split("/"))
    return {
        "width": stream["width"],
        "height": stream["height"],
        "codec": stream["codec_name"],
        "pixelFormat": stream["pix_fmt"],
        "frames": int(stream["nb_read_frames"]),
        "fps": {"numerator": num, "denominator": den},
        "durationMs": round(float(data["format"]["duration"]) * 1000),
        "sizeBytes": (target / "video.mp4").stat().st_size,
        "audioCodecs": [s["codec_name"] for s in data["streams"] if s["codec_type"] == "audio"],
    }
