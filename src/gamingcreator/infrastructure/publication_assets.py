"""Extract one actual output frame using the pinned local FFmpeg."""

import struct
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.media_process import run_media_process


async def extract_cover(
    repository: Path, video: Path, output: Path, frame: int, width: int, height: int
) -> None:
    ffmpeg = str(repository / ".tools/ffmpeg/bin/ffmpeg.exe")
    context = CancellationContext("publication-cover", 300)
    await run_media_process(
        [
            ffmpeg,
            "-v",
            "error",
            "-xerror",
            "-nostdin",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(video),
            "-vf",
            f"select=eq(n\\,{frame})",
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
    )
    validate_png(output, width, height)
    await run_media_process(
        [
            ffmpeg,
            "-v",
            "error",
            "-xerror",
            "-nostdin",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(output),
            "-f",
            "null",
            "-",
        ],
        context,
    )


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
