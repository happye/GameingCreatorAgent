"""Low-resolution audio peaks for the Studio waveform lane (stage C, 2026-11-11).

Project FFmpeg decodes one source range to 1 kHz mono 16-bit PCM on stdout; peaks are the
maximum absolute sample per bucket, scaled to 0..1. Display only: nothing is written to disk
and no analysis or evidence depends on it.
"""

from __future__ import annotations

import array
import subprocess
from pathlib import Path

SAMPLE_RATE = 1000
MAX_RANGE_US = 600_000_000  # ten minutes per request
MAX_BUCKETS = 2000
TIMEOUT_SECONDS = 30


def peaks_from_pcm(pcm: bytes, buckets: int) -> list[float]:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return []
    count = len(samples)
    result = []
    for index in range(buckets):
        start, end = index * count // buckets, (index + 1) * count // buckets
        chunk = samples[start : max(end, start + 1)]
        result.append(round(max(abs(v) for v in chunk) / 32768, 3) if chunk else 0.0)
    return result


def audio_peaks(
    repository: Path, source: Path, start_us: int, end_us: int, buckets: int
) -> list[float] | None:
    """Peaks for [start_us, end_us) of the source, or None when it has no audio stream."""
    if not (0 <= start_us < end_us and end_us - start_us <= MAX_RANGE_US):
        raise ValueError("Waveform range must be positive and at most ten minutes.")
    if not 1 <= buckets <= MAX_BUCKETS:
        raise ValueError("Waveform buckets out of range.")
    ffmpeg = repository.resolve() / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-ss",
        f"{start_us / 1e6:.6f}",
        "-t",
        f"{(end_us - start_us) / 1e6:.6f}",
        "-i",
        str(source),
        "-map",
        "0:a:0?",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "pipe:1",
    ]
    completed = subprocess.run(command, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
    if completed.returncode != 0:
        if b"does not contain any stream" in completed.stderr:
            return None  # the optional audio map matched nothing: a silent recording
        raise ValueError("FFmpeg could not read this range.")
    if not completed.stdout:
        return None
    return peaks_from_pcm(completed.stdout, buckets)
