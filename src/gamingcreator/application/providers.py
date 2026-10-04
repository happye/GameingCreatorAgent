import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from math import isfinite
from typing import Protocol

from gamingcreator.domain.media import AudioEvidence, MediaAsset
from gamingcreator.domain.models import (
    Embedding,
    EvidenceReference,
    SemanticEvent,
    TranscriptSegment,
)


class CostStatus(StrEnum):
    UNVERIFIED = "unverified"
    ESTIMATED = "estimated"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    original_cost: Decimal | None = None
    currency: str | None = None
    cost_cny: Decimal | None = None
    cost_status: CostStatus = CostStatus.UNVERIFIED

    def __post_init__(self) -> None:
        if not isinstance(self.cost_status, CostStatus):
            raise ValueError("Unknown cost status.")
        for count in (self.input_tokens, self.output_tokens, self.cached_input_tokens):
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError("Usage counts must be nonnegative integers or unknown.")
        if (
            self.input_tokens is not None
            and self.cached_input_tokens is not None
            and self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("Cached usage cannot exceed total input usage.")
        for amount in (self.original_cost, self.cost_cny):
            if amount is not None and (
                not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0
            ):
                raise ValueError("Cost must be finite, nonnegative or unknown.")
        if self.original_cost is not None and not self.currency:
            raise ValueError("Original cost needs a currency.")
        if self.cost_status != CostStatus.UNVERIFIED and self.original_cost is None:
            raise ValueError("Verified or estimated cost needs an original amount.")


@dataclass(frozen=True, slots=True)
class InvocationMetadata:
    provider: str
    requested_model: str
    actual_model: str | None
    model_revision: str | None
    prompt_version: str
    schema_version: str
    attempt: int
    usage: ProviderUsage
    elapsed_ms: int | None = None
    price_version: str | None = None
    request_id: str | None = None
    execution_details: str | None = None


class ProviderStatus(StrEnum):
    COMPLETED = "completed"
    NO_AUDIO = "no_audio"
    NO_SPEECH = "no_speech"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    code: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ProviderResult[T]:
    status: ProviderStatus
    output: T | None
    metadata: InvocationMetadata
    error: ProviderFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProviderStatus):
            raise ValueError("Unknown provider status.")
        if self.status in (ProviderStatus.FAILED, ProviderStatus.CANCELLED):
            if self.output is not None or self.error is None:
                raise ValueError("Failed results need an error and no output.")
        elif self.output is None or self.error is not None:
            raise ValueError("Completed/empty-modality results need typed output and no error.")


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    image_sequence: bool = False
    native_video: bool = False
    audio: bool = False
    structured_output: bool = False
    max_images: int | None = None
    max_image_width: int | None = None
    local_time_semantics: str | None = None


@dataclass(frozen=True, slots=True)
class CancellationContext:
    run_id: str
    timeout_seconds: float
    cancelled: asyncio.Event = field(default_factory=asyncio.Event, compare=False, repr=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("Timeout must be finite and positive.")

    def check_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise asyncio.CancelledError


@dataclass(frozen=True, slots=True)
class VisionRequest:
    run_id: str
    evidence: tuple[EvidenceReference, ...]
    prompt_version: str
    schema_version: str
    max_output_tokens: int
    language: str = "zh"
    game_terms: tuple[str, ...] = ()
    stage_id: str = "vision"


@dataclass(frozen=True, slots=True)
class AsrRequest:
    run_id: str
    audio_evidence: EvidenceReference | None
    schema_version: str
    language: str = "zh"
    game_terms: tuple[str, ...] = ()
    media_asset: MediaAsset | None = None
    audio_clock: AudioEvidence | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    run_id: str
    texts: tuple[str, ...]
    schema_version: str


class VisionProvider(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def analyze(
        self, request: VisionRequest, context: CancellationContext
    ) -> ProviderResult[tuple[SemanticEvent, ...]]: ...


class AsrProvider(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def transcribe(
        self, request: AsrRequest, context: CancellationContext
    ) -> ProviderResult[tuple[TranscriptSegment, ...]]: ...


class EmbeddingProvider(Protocol):
    async def embed(
        self, request: EmbeddingRequest, context: CancellationContext
    ) -> ProviderResult[tuple[Embedding, ...]]: ...
