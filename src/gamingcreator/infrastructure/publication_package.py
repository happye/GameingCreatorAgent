"""Pinned local media transforms and measured package facts."""

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.ffmpeg_render import _filter_path, _watermark_ass
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.publication_assets import extract_cover, validate_png


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
    cover_card: tuple[int, str] | None = None,
) -> dict[str, Any]:
    """``watermark`` is redrawn after cropping/padding, so a package never loses the mark."""
    tools = repository / ".tools/ffmpeg/bin"
    fields = profile["Fields"]
    field = fields["video"]
    video_filter = transform(field)
    variant = fields.get("variant")
    ranges = variant.get("ranges") if variant else None
    trim_args = []
    if variant and not ranges:
        if duration is None or duration <= 0:
            raise ValueError("Short package requires a valid output duration")
        video_filter = f"trim=end_frame={variant['durationFrames']},{video_filter}"
        audio_filter = f"atrim=duration={float(duration):.12f}"
        if start := variant.get("startFrame"):
            if output_clock is None:
                raise ValueError("Offset package requires a verified output clock")
            frames, fps = output_clock
            end = start + frames
            video_filter = (
                f"trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS,{transform(field)}"
            )
            audio_filter = (
                f"atrim=start={float(start / fps):.12f}:end={float(end / fps):.12f},"
                "asetpts=PTS-STARTPTS"
            )
        trim_args = ["-af", audio_filter, "-movie_timescale", "48000"]
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
        if ranges:
            if output_clock is None:
                raise ValueError("Joined package requires a verified output clock")
            media_args = _range_media_args(
                ranges, video_filter, *output_clock, await _has_audio(tools, video)
            )
        else:
            media_args = ["-map", "0:v:0", "-map", "0:a?", "-vf", video_filter, *trim_args]
        return await _encode(repository, video, cover, target, profile, media_args, cover_card)
    finally:
        mark.unlink(missing_ok=True)
        if publication_text is not None:
            text_path.unlink(missing_ok=True)


async def _has_audio(tools: Path, video: Path) -> bool:
    result = await run_media_process(
        [
            str(tools / "ffprobe.exe"),
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(video),
        ],
        CancellationContext("platform-package-audio", 15),
    )
    return bool(json.loads(result.stdout)["streams"])


def _range_media_args(
    ranges: list[dict[str, int]], video_filter: str, frames: int, fps: Fraction, audio: bool
) -> list[str]:
    parts, video_pads, audio_pads = [], [], []
    for i, span in enumerate(ranges):
        start, end = span["startFrame"], span["endFrame"]
        video_pads.append(f"[v{i}]")
        parts.append(f"[0:v:0]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS[v{i}]")
        if audio:
            audio_pads.append(f"[a{i}]")
            first, last = round(start * 48_000 / fps), round(end * 48_000 / fps)
            parts.append(
                f"[0:a:0]aresample=48000,atrim=start_sample={first}:end_sample={last},"
                f"asetpts=N/SR/TB[a{i}]"
            )
    count = len(ranges)
    parts.append(
        f"{''.join(video_pads)}concat=n={count}:v=1:a=0,"
        f"settb=1/{fps.numerator},setpts=N*{fps.denominator},{video_filter}[joined_video]"
    )
    if audio:
        samples = round(frames * 48_000 / fps)
        parts.append(
            f"{''.join(audio_pads)}concat=n={count}:v=0:a=1,"
            f"apad=whole_len={samples},atrim=end_sample={samples},asetpts=N/SR/TB[joined_audio]"
        )
    return [
        "-filter_complex",
        ";".join(parts),
        "-map",
        "[joined_video]",
        *(["-map", "[joined_audio]"] if audio else []),
        "-movie_timescale",
        "48000",
    ]


async def _encode(
    repository: Path,
    video: Path,
    cover: Path,
    target: Path,
    profile: dict[str, Any],
    media_args: list[str],
    cover_card: tuple[int, str] | None,
) -> dict[str, Any]:
    tools = repository / ".tools/ffmpeg/bin"
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
            *media_args,
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
    field = profile["Fields"]["cover"]
    image = target / "cover.png"
    if cover_card is not None:
        frame, title = cover_card
        await extract_cover(
            repository,
            video,
            image,
            frame,
            field["width"],
            field["height"],
            title=title,
            fit_filter=transform(field),
        )
    else:
        await run_media_process(
            [
                *base,
                "-i",
                str(cover),
                "-vf",
                transform(field),
                "-frames:v",
                "1",
                "-update",
                "1",
                "-n",
                str(image),
            ],
            context,
        )
        validate_png(image, field["width"], field["height"])
        await run_media_process([*base, "-i", str(image), "-f", "null", "-"], context)
    await run_media_process([*base, "-i", str(target / "video.mp4"), "-f", "null", "-"], context)
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
