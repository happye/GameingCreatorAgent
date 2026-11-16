"""Word-level ASR reuses official prepared audio and refuses preview-proxy evidence."""

from __future__ import annotations

import hashlib
import wave
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.asr_audio import (
    ASR_SCHEMA_VERSION,
    OFFICIAL_SAMPLE_RATE,
    audio_request_for_bundle,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import (
    AudioEvidence,
    AudioFrameMapping,
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
)
from gamingcreator.infrastructure.asr_audio import (
    prepared_asr_audio_request,
    verify_prepared_asr_audio,
)

TRANSFORM = "ffmpeg-evidence-v1-piecewise-audio-trim"
SAMPLES = 16000
DURATION_US = 1_000_000


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_wav(path: Path, frames: int = SAMPLES, rate: int = OFFICIAL_SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x00\x00" * frames)


def _bundle(tmp_path: Path, *, source: Path | None = None, audio: Path | None = None):
    source = source or (tmp_path / "source.mp4")
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        source.write_bytes(b"original-source-bytes")
    audio = audio or (tmp_path / "audio.wav")
    audio.parent.mkdir(parents=True, exist_ok=True)
    if not audio.exists():
        _write_wav(audio)
    asset = MediaAsset(
        "media",
        source,
        _hash(source),
        (
            MediaStream(0, "video", Fraction(1, OFFICIAL_SAMPLE_RATE), 0, SAMPLES),
            MediaStream(1, "audio", Fraction(1, OFFICIAL_SAMPLE_RATE), 0, SAMPLES),
        ),
        Fraction(0),
        DURATION_US,
        "fake-probe",
    )
    clock = AudioEvidence(
        "audio",
        audio,
        _hash(audio),
        OFFICIAL_SAMPLE_RATE,
        SAMPLES,
        (AudioFrameMapping(0, SAMPLES, 0, Fraction(1, OFFICIAL_SAMPLE_RATE)),),
    )
    return MediaPreprocessingResult(
        asset, (), clock, tmp_path / "media-manifest.json", TRANSFORM, "fake-processor"
    )


def test_prepared_request_reuses_existing_audio_sha_and_does_not_change_source(tmp_path):
    bundle = _bundle(tmp_path)
    source_before = bundle.asset.source_path.read_bytes()
    audio_before = bundle.audio.path.read_bytes()
    request = prepared_asr_audio_request("run-1", bundle)
    verify_prepared_asr_audio(request)
    assert request.schema_version == ASR_SCHEMA_VERSION
    assert request.audio_evidence is not None
    assert request.audio_evidence.sha256 == bundle.audio.sha256
    assert request.audio_clock is bundle.audio
    assert request.audio_clock.sample_rate == OFFICIAL_SAMPLE_RATE
    assert request.media_asset.source_path == bundle.asset.source_path
    assert bundle.asset.source_path.read_bytes() == source_before
    assert bundle.audio.path.read_bytes() == audio_before
    assert audio_request_for_bundle("run-1", bundle) == request


def test_editing_proxy_is_not_accepted_as_source_or_audio_evidence(tmp_path):
    proxy_dir = tmp_path / "proxies" / "abc"
    proxy_dir.mkdir(parents=True)
    proxy = proxy_dir / "proxy.mp4"
    proxy.write_bytes(b"proxy-bytes-not-source")
    (proxy_dir / "receipt.json").write_text("{}", encoding="utf-8")
    with pytest.raises(AppError) as source_error:
        prepared_asr_audio_request("run-1", _bundle(tmp_path, source=proxy))
    assert source_error.value.code == "media.proxy_not_source"
    assert "原片" in source_error.value.message
    assert proxy.read_bytes() == b"proxy-bytes-not-source"

    # Swap the audio evidence path to the proxy file.
    bundle = _bundle(tmp_path / "audio-proxy")
    object.__setattr__(bundle.audio, "path", proxy)
    object.__setattr__(bundle.audio, "sha256", _hash(proxy))
    with pytest.raises(AppError) as audio_error:
        prepared_asr_audio_request("run-1", bundle)
    assert audio_error.value.code == "media.proxy_not_source"
    assert (
        audio_error.value.message == "逐词识别必须使用原片准备的音频，不能把编辑代理当成原片证据。"
    )
    assert proxy.read_bytes() == b"proxy-bytes-not-source"


def test_tampered_prepared_audio_is_rejected_and_source_stays_unchanged(tmp_path):
    bundle = _bundle(tmp_path)
    request = prepared_asr_audio_request("run-1", bundle)
    source_before = bundle.asset.source_path.read_bytes()
    bundle.audio.path.write_bytes(bundle.audio.path.read_bytes() + b"x")
    with pytest.raises(AppError) as error:
        verify_prepared_asr_audio(request)
    assert error.value.code == "asr.input_integrity"
    assert bundle.asset.source_path.read_bytes() == source_before


def test_non_official_wav_layout_is_rejected(tmp_path):
    audio = tmp_path / "audio.wav"
    _write_wav(audio, frames=8000, rate=8000)
    bundle = _bundle(tmp_path, audio=audio)
    # The clock still claims the official layout; the file does not.
    request = prepared_asr_audio_request("run-1", bundle)
    with pytest.raises(AppError) as error:
        verify_prepared_asr_audio(request)
    assert error.value.code in {"media.audio_format", "asr.input_integrity"}
