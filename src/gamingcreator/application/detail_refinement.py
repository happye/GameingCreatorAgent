"""Frozen refinement request, result, and ports. No HTTP, SQLite, or file writes."""

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from gamingcreator.application.providers import CancellationContext, ProviderResult
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.actor_details import CandidateDetail, DetailEvidence, MatchStatus
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.time import SourceInstant, SourceRange

REFINEMENT_PROMPT_VERSION = "actor-detail-refinement-v1"
REFINEMENT_SCHEMA_VERSION = "actor-detail-refinement-schema-v1"
REFINEMENT_SETTINGS_VERSION = "actor-detail-refinement-settings-v1"
REFINEMENT_PROMPT = """Observe only the supplied candidate interval and its registered image ids.
Record visible actor and environment attributes supported by those frames.
Do not invent attributes when the candidate has no usable visual evidence.
Do not reuse a base vision prompt or extend the original source interval.
"""


def _hash(value: object) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Refinement identities require lowercase SHA-256 hashes.")


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def event_fingerprint(event: SemanticEvent) -> str:
    """Hash the original event text, tags, uncertainty, interval, and evidence ids."""
    if type(event) is not SemanticEvent or type(event.source_range) is not SourceRange:
        raise ValueError("An event fingerprint requires the stored semantic event.")
    payload = {
        "observableFacts": list(event.observable_facts),
        "mechanicTags": list(event.mechanic_tags),
        "uncertainty": event.uncertainty,
        "startUs": event.source_range.start_us,
        "endUs": event.source_range.end_us,
        "durationUs": event.source_range.duration_us,
        "evidenceIds": list(event.evidence_ids),
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def registered_candidate_id(run_id: str, event_id: str) -> str:
    """Same clip id retrieval stores for an event document. Not a new formula."""
    if type(run_id) is not str or type(event_id) is not str or not run_id or not event_id:
        raise ValueError("Candidate identity needs the stored run and event.")
    digest = hashlib.sha256(f"{run_id}:event:{event_id}".encode()).hexdigest()
    return f"clip-{digest[:24]}"


@dataclass(frozen=True, slots=True)
class RefinementSettings:
    max_images: int = 9
    max_image_width: int = 1280
    max_image_bytes: int = 3_145_728
    image_detail: str = "original"
    timeout_seconds: int = 90
    max_output_tokens: int = 2048
    version: str = REFINEMENT_SETTINGS_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.max_images) is not int
            or not 1 <= self.max_images <= 9
            or type(self.max_image_width) is not int
            or not 2 <= self.max_image_width <= 1280
            or type(self.max_image_bytes) is not int
            or not 1 <= self.max_image_bytes <= 3_145_728
            or self.image_detail != "original"
            or type(self.timeout_seconds) is not int
            or self.timeout_seconds <= 0
            or type(self.max_output_tokens) is not int
            or not 1 <= self.max_output_tokens <= 4096
            or type(self.version) is not str
            or self.version != REFINEMENT_SETTINGS_VERSION
        ):
            raise ValueError("Refinement settings are outside the frozen image contract.")


@dataclass(frozen=True, slots=True)
class RefinementIdentity:
    prompt_version: str
    prompt_hash: str
    schema_version: str
    provider: str
    requested_model: str

    def __post_init__(self) -> None:
        if (
            type(self.prompt_version) is not str
            or not self.prompt_version
            or self.prompt_version.startswith("phase0-vision-")
            or type(self.schema_version) is not str
            or self.schema_version != REFINEMENT_SCHEMA_VERSION
            or type(self.provider) is not str
            or not self.provider
            or type(self.requested_model) is not str
            or not self.requested_model
        ):
            raise ValueError("Refinement identity must stay separate from a base vision prompt.")
        _hash(self.prompt_hash)


def default_refinement_identity() -> RefinementIdentity:
    return RefinementIdentity(
        REFINEMENT_PROMPT_VERSION,
        hashlib.sha256(REFINEMENT_PROMPT.encode("utf-8")).hexdigest(),
        REFINEMENT_SCHEMA_VERSION,
        "deepseek",
        "deepseek-flash",
    )


@dataclass(frozen=True, slots=True)
class DetailRefinementRequest:
    run_id: str
    media_sha256: str
    configuration_hash: str
    pipeline_version: str
    event_fingerprint: str
    candidate_id: str
    event_id: str
    source_range: SourceRange
    evidence: tuple[DetailEvidence, ...]
    settings: RefinementSettings
    identity: RefinementIdentity
    base_prompt_version: str
    base_prompt_hash: str | None

    def __post_init__(self) -> None:
        _hash(self.media_sha256)
        _hash(self.configuration_hash)
        _hash(self.event_fingerprint)
        if self.base_prompt_hash is not None:
            _hash(self.base_prompt_hash)
        if (
            type(self.source_range) is not SourceRange
            or type(self.evidence) is not tuple
            or not self.evidence
            or any(type(item) is not DetailEvidence for item in self.evidence)
            or type(self.settings) is not RefinementSettings
            or type(self.identity) is not RefinementIdentity
            or self.identity.prompt_hash == self.base_prompt_hash
            or self.candidate_id != registered_candidate_id(self.run_id, self.event_id)
        ):
            raise ValueError("Refinement request does not match the stored candidate.")
        if self.identity.prompt_version == self.base_prompt_version:
            raise ValueError("Refinement prompt version must stay separate from the base prompt.")


def canonical_request_json(request: DetailRefinementRequest) -> str:
    """Stable request identity. Base prompt fields stay beside it, not inside it."""
    if type(request) is not DetailRefinementRequest:
        raise ValueError("A typed refinement request is required.")
    settings = request.settings
    identity = request.identity
    return _canonical(
        {
            "baseRunId": request.run_id,
            "mediaSha256": request.media_sha256,
            "configurationHash": request.configuration_hash,
            "pipelineVersion": request.pipeline_version,
            "eventFingerprint": request.event_fingerprint,
            "candidateId": request.candidate_id,
            "interval": {
                "startUs": request.source_range.start_us,
                "endUs": request.source_range.end_us,
                "durationUs": request.source_range.duration_us,
            },
            "evidence": [
                {
                    "evidenceId": item.evidence_id,
                    "sha256": item.image_sha256,
                    "sourceUs": item.source_time.time_us,
                    "durationUs": item.source_time.duration_us,
                }
                for item in request.evidence
            ],
            "settings": {
                "version": settings.version,
                "maxImages": settings.max_images,
                "maxImageWidth": settings.max_image_width,
                "maxImageBytes": settings.max_image_bytes,
                "imageDetail": settings.image_detail,
                "timeoutSeconds": settings.timeout_seconds,
                "maxOutputTokens": settings.max_output_tokens,
            },
            "promptVersion": identity.prompt_version,
            "promptHash": identity.prompt_hash,
            "schemaVersion": identity.schema_version,
            "provider": identity.provider,
            "requestedModel": identity.requested_model,
        }
    )


def request_hash(request: DetailRefinementRequest) -> str:
    return hashlib.sha256(canonical_request_json(request).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DetailRefinementResult:
    """No provider output yet. Missing visual evidence stays unverified and empty."""

    status: MatchStatus
    event_fingerprint: str
    request: DetailRefinementRequest | None = None
    request_hash: str | None = None
    shots: tuple[()] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not MatchStatus or self.shots:
            raise ValueError("Preparation cannot invent attributes or shots.")
        _hash(self.event_fingerprint)
        if self.status == MatchStatus.UNVERIFIED and self.request is None:
            if self.request_hash is not None:
                raise ValueError("An unverified candidate has no refinement request.")
            return
        if (
            self.status != MatchStatus.UNVERIFIED
            or self.request is None
            or self.request_hash != request_hash(self.request)
            or self.event_fingerprint != self.request.event_fingerprint
        ):
            raise ValueError("A prepared refinement must retain its canonical request hash.")


@dataclass(frozen=True, slots=True)
class StoredRefinementRequest:
    run_id: str
    request_hash: str
    canonical_json: str

    def __post_init__(self) -> None:
        _hash(self.request_hash)
        if type(self.canonical_json) is not str or not self.canonical_json:
            raise ValueError("A stored refinement request needs its canonical JSON.")


@runtime_checkable
class DetailRefinementProvider(Protocol):
    async def refine(
        self, request: DetailRefinementRequest, context: CancellationContext
    ) -> ProviderResult[CandidateDetail]: ...


@runtime_checkable
class DetailRefinementStore(Protocol):
    async def load_request(
        self, run_id: str, request_hash: str
    ) -> StoredRefinementRequest | None: ...

    async def save_request(self, record: StoredRefinementRequest) -> None: ...


def _images(timeline: StoredTimeline, event: SemanticEvent) -> tuple[DetailEvidence, ...]:
    registered = {item.evidence_id: item for item in timeline.evidence}
    selected: list[DetailEvidence] = []
    for evidence_id in event.evidence_ids:
        item = registered.get(evidence_id)
        if item is None or item.kind != "image" or not isinstance(item.source_time, SourceInstant):
            continue
        if not event.source_range.start_us <= item.source_time.time_us < event.source_range.end_us:
            continue
        selected.append(DetailEvidence(item.evidence_id, item.sha256, item.source_time))
    selected.sort(key=lambda item: (item.source_time.time_us, item.evidence_id))
    return tuple(selected)


def prepare_refinement(
    timeline: StoredTimeline,
    event_id: str,
    *,
    settings: RefinementSettings | None = None,
    identity: RefinementIdentity | None = None,
) -> DetailRefinementResult:
    """Freeze one stored candidate. This function never calls a provider."""
    if type(timeline) is not StoredTimeline or type(event_id) is not str:
        raise ValueError("Refinement preparation needs a stored timeline and event id.")
    event = next((item for item in timeline.events if item.event_id == event_id), None)
    if event is None or event.run_id != timeline.run.run_id:
        raise ValueError("Refinement candidate is not in this timeline.")
    fingerprint = event_fingerprint(event)
    images = _images(timeline, event)
    if event.modality != "visual" or not images:
        return DetailRefinementResult(MatchStatus.UNVERIFIED, fingerprint)
    analysis = timeline.run.configuration.analysis
    request = DetailRefinementRequest(
        timeline.run.run_id,
        timeline.run.asset.sha256,
        timeline.run.config_hash,
        timeline.run.configuration.pipeline_version,
        fingerprint,
        registered_candidate_id(timeline.run.run_id, event.event_id),
        event.event_id,
        event.source_range,
        images,
        settings or RefinementSettings(),
        identity or default_refinement_identity(),
        analysis.vision_prompt_version,
        analysis.vision_prompt_hash,
    )
    return DetailRefinementResult(
        MatchStatus.UNVERIFIED, fingerprint, request, request_hash(request)
    )
