"""Local beat grid for a registered music track: decode with project FFmpeg, estimate tempo.

Offline and deterministic. The result is an estimate (bpm, beat times, confidence), cached by
the track's audio SHA-256 and algorithm version; it never changes the track's receipt or its
public identity in render receipts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.file_sharing import retry_file_sharing
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.music_library import _FORMATS, MusicTrack

ALGORITHM = "onset-autocorr-v2-first-audio"
SCHEMA = "music-beats-v1"
RATE = 11025
HOP = 256
FFT = 1024
MIN_BPM, MAX_BPM = 60.0, 180.0
MAX_ANALYSIS_SECONDS = 600


def _cache(repository: Path, sha256: str, max_seconds: int) -> Path:
    suffix = "" if max_seconds == MAX_ANALYSIS_SECONDS else f"-{max_seconds}s"
    return repository / ".cache/workspace/music-beats" / f"{sha256}-{ALGORITHM}{suffix}.json"


def estimate_beats(samples: Any, rate: int = RATE) -> dict[str, Any]:
    """Tempo and beat phase from mono float samples (numpy array)."""
    import numpy as np

    if samples.size < FFT * 8:
        raise ValueError("音乐太短，无法估计节拍。")
    frames = 1 + (samples.size - FFT) // HOP
    index = np.arange(FFT)[None, :] + HOP * np.arange(frames)[:, None]
    spectrum = np.abs(np.fft.rfft(samples[index] * np.hanning(FFT), axis=1))
    del index
    # Quiet, periodic leakage from sustained tones can have high autocorrelation.
    lowest_onset_bin = int(np.ceil(60 * FFT / rate))
    difference = np.diff(spectrum[:, lowest_onset_bin:], axis=0)
    np.maximum(difference, 0, out=difference)
    transients = difference.sum(axis=1)
    del difference
    average_level = float(spectrum.sum(axis=1).mean())
    if not average_level > 0 or np.percentile(transients, 95) < average_level * 0.025:
        return {"bpm": None, "beatsUs": [], "confidence": 0.0}
    flux = np.maximum(np.diff(np.log1p(spectrum * 100), axis=0), 0).sum(axis=1)
    onset = flux - flux.mean()
    frame_rate = rate / HOP
    lags = np.arange(int(frame_rate * 60 / MAX_BPM), int(frame_rate * 60 / MIN_BPM) + 1)
    energy = float(np.dot(onset, onset)) or 1.0
    score = np.array([np.dot(onset[:-lag], onset[lag:]) for lag in lags]) / energy
    # Mild preference for the 120 BPM region avoids picking half or double tempo.
    bpm_of = 60 * frame_rate / lags
    weighted = score * np.exp(-0.5 * (np.log2(bpm_of / 120.0) / 1.0) ** 2)
    best = int(np.argmax(weighted))
    lag = int(lags[best])
    # Refine the period around the best integer lag with the onset comb.
    candidates = np.linspace(lag - 1, lag + 1, 41)
    positive = np.maximum(onset, 0)

    def comb(period: float, phase: float) -> float:
        points = np.arange(phase, positive.size, period).astype(int)
        points = points[points < positive.size]
        return float(positive[points].sum()) / max(1, points.size)

    period = float(max(candidates, key=lambda p: max(comb(p, ph) for ph in range(int(p)))))
    phase = float(max(np.arange(0, period, 0.25), key=lambda ph: comb(period, ph)))
    # Flux frame k compares windows starting at k and k+1 hops; a Hann window registers an onset
    # near its centre, so the beat time is the next window's start plus half a window.
    beats = ((np.arange(phase, positive.size, period) + 1) * HOP + FFT / 2) / rate
    return {
        "bpm": round(60 * frame_rate / period, 2),
        "beatsUs": [int(round(t * 1_000_000)) for t in beats],
        "confidence": round(float(max(0.0, min(1.0, score[best]))), 3),
    }


async def analyze_track(
    repository: Path,
    track: MusicTrack,
    context: CancellationContext,
    tools: Path | None = None,
    *,
    max_seconds: int = MAX_ANALYSIS_SECONDS,
) -> dict[str, Any]:
    if not 1 <= max_seconds <= MAX_ANALYSIS_SECONDS:
        raise ValueError("无效的节拍分析时长。")
    cache = _cache(repository, track.sha256, max_seconds)
    try:
        cached = json.loads(read_bounded(cache))
    except ValueError:
        cached = None
    if (
        isinstance(cached, dict)
        and cached.get("schemaVersion") == SCHEMA
        and cached.get("mediaSha256") == track.sha256
    ):
        return {**cached, "trackId": track.track_id}
    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - numpy ships with the retrieval extra
        raise ValueError("节拍分析需要 numpy（检索组件）。") from error
    ffmpeg = (tools or repository / ".tools/ffmpeg/bin") / "ffmpeg.exe"
    full_window = track.duration_us / 1_000_000 + 1
    seconds = min(max_seconds, full_window)
    limit = int(seconds * RATE * 4) + 4096
    result = await run_media_process(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-nostdin",
            "-protocol_whitelist",
            "file",
            "-f",
            _FORMATS[track.path.suffix.lower()],
            "-t",
            f"{seconds:.3f}",
            "-i",
            str(track.path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(RATE),
            "-f",
            "f32le",
            "-",
        ],
        context,
        max_stdout_bytes=limit,
    )
    if hash_file(track.path) != track.sha256:
        raise ValueError("配乐内容在节拍分析期间发生变化。")
    samples = np.frombuffer(result.stdout, dtype="<f4").astype(np.float64)
    grid = estimate_beats(samples)
    document = {
        "schemaVersion": SCHEMA,
        "algorithm": ALGORITHM,
        "mediaSha256": track.sha256,
        "trackId": track.track_id,
        "durationUs": track.duration_us,
        "analyzedSeconds": samples.size / RATE,
        "complete": full_window <= max_seconds and samples.size < int(seconds * RATE),
        **grid,
        "status": "local-estimate-unreviewed",
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_name(f"{cache.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(document, stream)
        retry_file_sharing(lambda: temporary.replace(cache))
    finally:
        temporary.unlink(missing_ok=True)
    return document
