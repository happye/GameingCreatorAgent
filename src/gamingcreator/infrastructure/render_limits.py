"""Scratch-media limits sized from the validated output, with a 2 GiB ceiling."""

from pathlib import Path

from gamingcreator.infrastructure.media_process import MediaOutputLimit


def render_output_limit(
    path: Path, frames: int, fps: int, width: int, height: int
) -> MediaOutputLimit:
    if any(type(n) is not int or n <= 0 for n in (frames, fps, width, height)):
        raise ValueError("Render budget needs positive integer output dimensions and clock.")
    raw_video = width * height * 3 * frames // 2
    raw_audio = ((frames * 48000 + fps - 1) // fps) * 4
    # FFV1 may exceed raw video for incompressible frames. Include room for mux overhead.
    budget = min(2 * 1024**3, max(8 * 1024**2, 2 * (raw_video + raw_audio) + 1024**2))
    return MediaOutputLimit(path, budget)
