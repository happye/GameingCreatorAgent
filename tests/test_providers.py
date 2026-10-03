import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from gamingcreator.application.providers import (
    AsrProvider,
    AsrRequest,
    CancellationContext,
    CostStatus,
    InvocationMetadata,
    ProviderCapabilities,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.domain.models import EvidenceReference, TranscriptSegment
from gamingcreator.domain.time import SourceRange


def metadata() -> InvocationMetadata:
    return InvocationMetadata("local", "asr", None, None, "none", "v1", 1, ProviderUsage())


class NoSpeechProvider:
    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(audio=True)

    async def transcribe(
        self,
        request: AsrRequest,
        context: CancellationContext,
    ) -> ProviderResult[tuple[TranscriptSegment, ...]]:
        context.check_cancelled()
        status = (
            ProviderStatus.NO_AUDIO if request.audio_evidence is None else ProviderStatus.NO_SPEECH
        )
        return ProviderResult(status, (), metadata())


def test_asr_contract_can_report_no_audio_without_fabricating_text_or_usage() -> None:
    provider: AsrProvider = NoSpeechProvider()
    result = asyncio.run(
        provider.transcribe(AsrRequest("run", None, "v1"), CancellationContext("run", 5))
    )
    assert result.status == ProviderStatus.NO_AUDIO and result.output == ()
    assert result.metadata.usage.input_tokens is None
    assert result.metadata.usage.cost_cny is None
    assert result.metadata.usage.cost_status == CostStatus.UNVERIFIED


def test_provider_context_propagates_cancellation() -> None:
    context = CancellationContext("run", 5)
    context.cancelled.set()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(NoSpeechProvider().transcribe(AsrRequest("run", None, "v1"), context))


def test_asr_contract_distinguishes_silent_audio_from_absent_audio() -> None:
    evidence = EvidenceReference(
        "audio", "media", "audio", SourceRange(0, 10, 10), Path("audio.wav"), "hash", "v1"
    )
    result = asyncio.run(
        NoSpeechProvider().transcribe(
            AsrRequest("run", evidence, "v1"),
            CancellationContext("run", 5),
        )
    )
    assert result.status == ProviderStatus.NO_SPEECH and result.output == ()
    assert result.metadata.usage.input_tokens is None


@pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf")])
def test_cancellation_context_rejects_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ValueError):
        CancellationContext("run", timeout)


def test_provider_result_does_not_allow_failed_output_or_success_without_data() -> None:
    with pytest.raises(ValueError):
        ProviderResult(ProviderStatus.COMPLETED, None, metadata())
    with pytest.raises(ValueError):
        ProviderResult(ProviderStatus.COMPLETED, (), metadata(), ProviderFailure("network", True))
    with pytest.raises(ValueError):
        ProviderResult(ProviderStatus.FAILED, None, metadata())
    with pytest.raises(ValueError):
        ProviderResult(
            ProviderStatus.FAILED, ("invented",), metadata(), ProviderFailure("network", True)
        )
    failed: ProviderResult[str] = ProviderResult(
        ProviderStatus.FAILED,
        None,
        metadata(),
        ProviderFailure("network", True),
    )
    assert failed.metadata.usage.cost_cny is None


def test_usage_rejects_false_zero_or_unverifiable_confirmed_cost() -> None:
    with pytest.raises(ValueError):
        ProviderUsage(input_tokens=True)
    with pytest.raises(ValueError):
        ProviderUsage(input_tokens=2, cached_input_tokens=3)
    with pytest.raises(ValueError):
        ProviderUsage(cost_status=CostStatus.CONFIRMED)
    with pytest.raises(ValueError):
        ProviderUsage(original_cost=Decimal("NaN"), currency="CNY")
