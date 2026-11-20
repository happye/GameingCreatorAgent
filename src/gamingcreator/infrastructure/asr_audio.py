"""Reuse a run's official prepared audio as ASR evidence; never treat a preview proxy as the source."""

from __future__ import annotations

import wave
from pathlib import Path

from gamingcreator.application.asr_audio import (
    OFFICIAL_SAMPLE_RATE,
    audio_request_for_bundle,
)
from gamingcreator.application.providers import AsrRequest
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import MediaPreprocessingResult
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.proxy_media import (
    is_editing_proxy_file,
    reject_editing_proxy_source,
)


def reject_proxy_audio_evidence(path: Path) -> None:
    if is_editing_proxy_file(path):
        raise AppError(
            "media.proxy_not_source",
            "逐词识别必须使用原片准备的音频，不能把编辑代理当成原片证据。",
            ExitCode.INPUT,
        )


def prepared_asr_audio_request(run_id: str, bundle: MediaPreprocessingResult) -> AsrRequest:
    """Bind the existing official WAV and its SHA. Does not rewrite the source recording."""
    reject_editing_proxy_source(bundle.asset.source_path)
    if bundle.audio is not None:
        reject_proxy_audio_evidence(bundle.audio.path)
    return audio_request_for_bundle(run_id, bundle)


def verify_prepared_asr_audio(request: AsrRequest) -> None:
    """Re-read hashes and the official 16 kHz mono layout. Files are not modified."""
    evidence, asset, clock = request.audio_evidence, request.media_asset, request.audio_clock
    if asset is not None:
        reject_editing_proxy_source(asset.source_path)
        if hash_file(asset.source_path) != asset.sha256:
            raise AppError(
                "asr.input_integrity",
                "原片或已准备音频的内容与记录不一致。",
                ExitCode.INPUT,
            )
    if evidence is None or clock is None:
        return
    reject_proxy_audio_evidence(evidence.artifact_path)
    reject_proxy_audio_evidence(clock.path)
    if (
        asset is None
        or evidence.kind != "audio"
        or evidence.evidence_id != clock.evidence_id
        or evidence.media_id != asset.media_id
        or evidence.artifact_path.resolve() != clock.path.resolve()
        or evidence.sha256 != clock.sha256
        or hash_file(clock.path) != clock.sha256
    ):
        raise AppError(
            "asr.input_integrity",
            "原片或已准备音频的内容与记录不一致。",
            ExitCode.INPUT,
        )
    try:
        with wave.open(str(clock.path), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getcomptype() != "NONE"
                or audio.getframerate() != OFFICIAL_SAMPLE_RATE
                or clock.sample_rate != OFFICIAL_SAMPLE_RATE
                or audio.getnframes() != clock.sample_count
            ):
                raise AppError("media.audio_format", "音频输出格式不符合合同。", ExitCode.INPUT)
    except (wave.Error, EOFError):
        raise AppError("media.audio_format", "音频输出格式不符合合同。", ExitCode.INPUT) from None
