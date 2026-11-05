import asyncio
from types import SimpleNamespace

import pytest
from test_creation_proposals import fixture, output

from gamingcreator.application.creation_reasoning import propose_creation, reasoning_request
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.requests = []

    async def complete(self, request, context):
        self.requests.append(request)
        return self.result


def metadata():
    return InvocationMetadata(
        "fake",
        "fake",
        None,
        None,
        "creation-reasoning-prompt-v1",
        "creation-reasoning-v1",
        1,
        ProviderUsage(),
    )


def test_arbitrary_language_forwarded_once_without_sentence_rules():
    snapshot, _, _, _ = fixture()
    provider = FakeProvider(ProviderResult(ProviderStatus.COMPLETED, output(snapshot), metadata()))
    instruction = "这段呼吸感不够，让节奏舒展一些，再保留最后的爆发点"
    result = asyncio.run(
        propose_creation(provider, snapshot, instruction, CancellationContext("run", 2))
    )
    assert result.proposal is not None
    assert len(provider.requests) == 1
    assert instruction in provider.requests[0].user
    assert result.metadata.usage.cost_cny is None
    assert result.metadata.provider == "fake"


def test_context_has_no_media_paths_or_arbitrary_metadata():
    snapshot, root, _, _ = fixture()
    assert "sourcePath" in str(root)
    request = reasoning_request(snapshot, "删掉 logo，无法定位就问我")
    assert "sourcePath" not in request.user
    assert "sourceSha256" not in request.user
    assert request.schema_version == "creation-reasoning-v1"
    assert request.prompt_version == "creation-reasoning-prompt-v1"


@pytest.mark.parametrize("status", [ProviderStatus.FAILED, ProviderStatus.CANCELLED])
def test_model_failure_preserves_metadata_no_retry(status):
    snapshot, _, _, _ = fixture()
    provider = FakeProvider(
        ProviderResult(status, None, metadata(), ProviderFailure("failed", True))
    )
    result = asyncio.run(
        propose_creation(provider, snapshot, "调整", CancellationContext("run", 2))
    )
    assert result.proposal is None
    assert result.status == status
    assert len(provider.requests) == 1


def test_pre_cancelled_does_not_call_model():
    snapshot, _, _, _ = fixture()
    context = CancellationContext("run", 2)
    context.cancelled.set()
    provider = FakeProvider(None)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(propose_creation(provider, snapshot, "调整", context))
    assert provider.requests == []


def test_missing_output_fails_closed():
    snapshot, _, _, _ = fixture()
    provider = FakeProvider(
        SimpleNamespace(status=ProviderStatus.COMPLETED, output=None, metadata=metadata())
    )
    with pytest.raises(ValueError, match="without output"):
        asyncio.run(propose_creation(provider, snapshot, "调整", CancellationContext("run", 2)))


def test_logo_ambiguity_is_clarification_without_edit():
    snapshot, _, _, _ = fixture()
    response = output(snapshot)
    response.update(
        kind="clarification",
        clips=[],
        questions=["logo 在哪个镜头？"],
        message="仅凭文字无法识别 logo，请指定镜头。",
    )
    provider = FakeProvider(ProviderResult(ProviderStatus.COMPLETED, response, metadata()))
    result = asyncio.run(
        propose_creation(provider, snapshot, "把带 logo 的删掉", CancellationContext("run", 2))
    )
    assert not result.proposal.response["clips"]
    assert result.proposal.response["kind"] == "clarification"


def test_cancellation_during_request_discards_output():
    snapshot, _, _, _ = fixture()

    class CancellingProvider(FakeProvider):
        async def complete(self, request, context):
            context.cancelled.set()
            return self.result

    provider = CancellingProvider(
        ProviderResult(ProviderStatus.COMPLETED, output(snapshot), metadata())
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(propose_creation(provider, snapshot, "调整", CancellationContext("run", 2)))


def test_timeout_does_not_retry():
    snapshot, _, _, _ = fixture()

    class SlowProvider(FakeProvider):
        async def complete(self, request, context):
            self.requests.append(request)
            await asyncio.sleep(1)
            return self.result

    provider = SlowProvider(None)
    with pytest.raises(TimeoutError):
        asyncio.run(propose_creation(provider, snapshot, "调整", CancellationContext("run", 0.01)))
    assert len(provider.requests) == 1


def test_cancelled_provider_result_keeps_metadata_when_context_event_is_set():
    snapshot, _, _, _ = fixture()
    expected = metadata()

    class CancellingProvider(FakeProvider):
        async def complete(self, request, context):
            context.cancelled.set()
            return ProviderResult(
                ProviderStatus.CANCELLED,
                None,
                expected,
                ProviderFailure("provider.cancelled", False),
            )

    outcome = asyncio.run(
        propose_creation(CancellingProvider(None), snapshot, "调整", CancellationContext("run", 2))
    )
    assert outcome.status == ProviderStatus.CANCELLED
    assert outcome.metadata is expected and outcome.proposal is None
