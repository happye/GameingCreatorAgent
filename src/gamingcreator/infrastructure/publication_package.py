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


def _publication_text_ass(
    text: dict[str, str], width: int, height: int, frames: int, fps: Fraction
) -> str:
    window = min(int(2 * fps), frames // 2 if len(text) == 2 else frames)
    if window < 1:
        raise ValueError("Platform video text requires a valid output frame window")

    def clock(frame: int) -> str:
        # Match the doubled PTS used for ASS so centiseconds distinguish adjacent frames.
        seconds, cs = divmod(int(200 * frame / fps), 100)
        minutes, sec = divmod(seconds, 60)
        hours, minute = divmod(minutes, 60)
        return f"{hours}:{minute:02d}:{sec:02d}.{cs:02d}"

    size = max(1, min(width // 27, height // 16))
    padding = max(1, size // 5)
    margin = height // 8
    style = f"Arial,{size},&H00FFFFFF,&H00FFFFFF,&H20000000,&H20000000,1,0,0,0,100,100,0,0,3,{padding},0"
    events = {
        "opening": (0, window, "Opening"),
        "closing": (frames - window, frames, "Closing"),
    }
    return (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Opening,{style},8,0,0,{margin},1\n"
        f"Style: Closing,{style},2,0,0,{margin},1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "".join(
            f"Dialogue: 0,{clock(start)},{clock(end)},{name},,0,0,0,,{text[key]}\n"
            for key, (start, end, name) in events.items()
            if key in text
        )
    )


async def encode(
    repository: Path,
    video: Path,
    cover: Path,
    target: Path,
    profile: dict[str, Any],
    watermark: str | None = None,
    duration: Fraction | None = None,
    *,
    output_clock: tuple[int, Fraction] | None = None,
) -> dict[str, Any]:
    """``watermark`` is redrawn after cropping/padding, so a package never loses the mark."""
    tools = repository / ".tools/ffmpeg/bin"
    fields = profile["Fields"]
    field = fields["video"]
    video_filter = transform(field)
    trim_args = []
    if variant := fields.get("variant"):
        if duration is None or duration <= 0:
            raise ValueError("Short package requires a valid output duration")
        video_filter = f"trim=end_frame={variant['durationFrames']},{video_filter}"
        trim_args = ["-af", f"atrim=duration={float(duration):.12f}", "-movie_timescale", "48000"]
    mark = target / "watermark.ass"
    text_path = target / "publication-text.ass"
    publication_text = fields.get("publicationText")
    try:
        if publication_text is not None:
            if output_clock is None:
                raise ValueError("Platform video text requires a verified output clock")
            text_path.write_text(
                _publication_text_ass(
                    publication_text, field["width"], field["height"], *output_clock
                ),
                encoding="utf-8",
            )
            video_filter += f",setpts=PTS*2,ass=filename={_filter_path(text_path)},setpts=PTS/2"
        if watermark is not None:
            mark.write_text(
                _watermark_ass(
                    watermark, field["width"], field["height"], duration or Fraction(359999)
                ),
                encoding="utf-8",
            )
            video_filter += f",ass=filename={_filter_path(mark)}"
        return await _encode(tools, video, cover, target, profile, video_filter, trim_args)
    finally:
        mark.unlink(missing_ok=True)
        if publication_text is not None:
            text_path.unlink(missing_ok=True)


async def _encode(
    tools: Path,
    video: Path,
    cover: Path,
    target: Path,
    profile: dict[str, Any],
    video_filter: str,
    trim_args: list[str],
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
            *trim_args,
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
