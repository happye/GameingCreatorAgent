"""Extract a publication cover from the rendered video with the pinned FFmpeg."""

import struct
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.publication import validate_cover_title
from gamingcreator.infrastructure.ffmpeg_filters import filter_path
from gamingcreator.infrastructure.media_process import MediaOutputLimit, run_media_process


def _cover_title_ass(title: str, width: int, height: int) -> str:
    size = max(1, min(width // 22, height // 10))
    return (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cover,Arial,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        f"1,0,0,0,100,100,0,0,1,0,0,2,{width // 22},{width // 22},{height // 11},1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:01.00,Cover,,0,0,0,,{title}\n"
    )


async def extract_cover(
    repository: Path,
    video: Path,
    output: Path,
    frame: int,
    width: int,
    height: int,
    *,
    title: str = "",
    fit_filter: str = "",
) -> None:
    ffmpeg = str(repository / ".tools/ffmpeg/bin/ffmpeg.exe")
    context = CancellationContext("publication-cover", 300)
    base = [ffmpeg, "-v", "error", "-xerror", "-nostdin", "-protocol_whitelist", "file,pipe"]
    cover_filter = f"select=eq(n\\,{frame})"
    if fit_filter:
        cover_filter += "," + fit_filter
    ass = None
    try:
        output_limit = None
        if title:
            validate_cover_title(title)
            sidecar = output.with_name("cover-title.ass")
            with sidecar.open("x", encoding="utf-8", newline="\n") as handle:
                ass = sidecar
                handle.write(_cover_title_ass(title, width, height))
            cover_filter += (
                ",setpts=PTS-STARTPTS,drawbox=x=0:y=ih*0.72:w=iw:h=ih*0.28:color=black@0.64:t=fill"
                f",ass=filename={filter_path(ass)}"
            )
            output_limit = MediaOutputLimit(output, 64 * 1024**2, minimum_free_bytes=256 * 1024**2)
        await run_media_process(
            [
                *base,
                "-i",
                str(video),
                "-vf",
                cover_filter,
                "-fps_mode",
                "vfr",
                "-frames:v",
                "1",
                "-update",
                "1",
                "-n",
                str(output),
            ],
            context,
            output_limit=output_limit,
        )
    finally:
        if ass is not None:
            ass.unlink(missing_ok=True)
    validate_png(output, width, height)
    await run_media_process([*base, "-i", str(output), "-f", "null", "-"], context)


def validate_png(path: Path, width: int, height: int) -> None:
    with path.open("rb") as handle:
        header = handle.read(24)
    if (
        header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
        or len(header) != 24
        or struct.unpack(">II", header[16:24]) != (width, height)
    ):
        raise ValueError("Invalid cover PNG or dimensions")
