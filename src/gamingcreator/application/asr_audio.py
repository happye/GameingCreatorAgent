"""Build an ASR request from a run's official prepared audio bundle."""

from __future__ import annotations

from gamingcreator.application.providers import AsrRequest
from gamingcreator.domain.media import MediaPreprocessingResult
from gamingcreator.domain.models import EvidenceReference

ASR_SCHEMA_VERSION = "transcript-v1"
OFFICIAL_SAMPLE_RATE = 16000


def audio_request_for_bundle(run_id: str, bundle: MediaPreprocessingResult) -> AsrRequest:
    audio = bundle.audio
    reference = None
    if audio is not None:
        coverage = audio.map_interval(0, audio.sample_count, bundle.asset)
        reference = EvidenceReference(
            audio.evidence_id,
            bundle.asset.media_id,
            "audio",
            coverage.source_range,
            audio.path,
            audio.sha256,
            bundle.transform_version,
        )
    return AsrRequest(
        run_id,
        reference,
        ASR_SCHEMA_VERSION,
        media_asset=bundle.asset,
        audio_clock=audio,
    )
