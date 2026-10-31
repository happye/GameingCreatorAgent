"""Validated narration identity and a bounded output-clock mix graph."""

import json
from fractions import Fraction
from typing import Any

from gamingcreator.application.narration import NarrationArtifact
from gamingcreator.domain.creation_narration import NarrationSelection
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.sapi_narration import read_narration_artifact


def verify_narration(
    selection: NarrationSelection, artifact: NarrationArtifact
) -> NarrationArtifact:
    NarrationSelection.from_json(selection.to_json())
    if any(is_link(p) for p in (artifact.directory, *artifact.directory.parents)):
        raise ValueError("Narration asset directory cannot use links.")
    checked = read_narration_artifact(artifact.directory, selection.receipt_sha256)
    receipt = json.loads(checked.receipt_path.read_text(encoding="utf-8"))
    if checked != artifact or receipt["jobId"] != selection.asset_job_id:
        raise ValueError("Narration asset identity differs from its selection.")
    return checked


def narration_receipt(
    selection: NarrationSelection, artifact: NarrationArtifact, fps: int
) -> dict[str, Any]:
    return {
        "selection": selection.to_json(),
        "assetReceiptSha256": artifact.receipt_sha256,
        "wavSha256": artifact.wav_sha256,
        "textSha256": artifact.text_sha256,
        "voice": {
            "voiceId": artifact.voice.voice_id,
            "description": artifact.voice.description,
            "language": artifact.voice.language,
            "engine": artifact.voice.engine,
        },
        "sampleRate": artifact.sample_rate,
        "channels": artifact.channels,
        "sampleWidth": artifact.sample_width,
        "sampleCount": artifact.sample_count,
        "startSample": round(Fraction(selection.start_frame * 48000, fps)),
        "rounding": "nearest-ties-to-even-48000",
        "licenseStatus": "unknown",
        # The narration stage always ends in this limiter, even without BGM.
        "mixPolicy": {
            "version": "creation-narration-mix-v1",
            "ducking": selection.ducking,
            "duckingDetector": "raw-narration-rms"
            if selection.ducking == "narration-v1"
            else "none",
            "compressor": {"threshold": 0.015, "ratio": 12, "attackMs": 10, "releaseMs": 200}
            if selection.ducking == "narration-v1"
            else None,
            "normalize": False,
            "limiter": "0.95-level-false-latency-compensated",
        },
    }


def narration_filter(selection: NarrationSelection, frames: int, fps: int, index: int) -> str:
    start = round(Fraction(selection.start_frame * 48000, fps))
    total = round(Fraction(frames * 48000, fps))
    voice = (
        f"[{index}:a:0]aresample=48000,aformat=channel_layouts=stereo,asetpts=N/SR/TB,"
        f"adelay={start}S:all=1,apad,atrim=end_sample={total},asplit=2[nraw][nkey];"
        f"[nraw]volume={selection.gain_db}dB[nvoice];"
    )
    if selection.ducking == "narration-v1":
        voice += (
            "[bed][nkey]sidechaincompress=threshold=0.015:ratio=12:attack=10:"
            "release=200:makeup=1:knee=1:detection=rms[nducked];"
        )
        bed = "nducked"
    else:
        voice += "[nkey]anullsink;"
        bed = "bed"
    return (
        voice
        + f"[{bed}][nvoice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        + f"alimiter=limit=0.95:level=false:latency=true,atrim=end_sample={total}[mixed]"
    )
