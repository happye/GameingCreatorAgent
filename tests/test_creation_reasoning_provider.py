import asyncio
import json
from dataclasses import replace
from decimal import Decimal

import pytest
from test_deepseek_vision import Recorder

from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.creation_reasoning import ReasoningRequest
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext, ProviderStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.creation_reasoning_provider import (
    DeepSeekCreationReasoningProvider,
)
from gamingcreator.infrastructure.http_transport import (
    MAX_RESPONSE_BYTES,
    HttpResponse,
    TransportError,
)


class Transport:
    def __init__(self, response=None, failure=None):
        self.response = response or response_body()
        self.failure = failure
        self.calls = []

    async def post(self, payload, timeout_seconds):
        self.calls.append(payload)
        if self.failure:
            raise self.failure
        return self.response


def response_body(**changes):
    data = {
        "model": "deepseek-flash",
        "id": "request-123",
        "usage": None,
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"kind":"clarification"}'},
            }
        ],
    }
    data.update(changes)
    return HttpResponse(200, json.dumps(data).encode())


def setup(transport=None, approved=True, reservation=Decimal("3"), price=DEEPSEEK_FLASH_20261004):
    ledger = BudgetLedger(Decimal("10"), 3, 1)
    recorder = Recorder()
    sends = transport or Transport()
    approvals = []

    async def gate(request):
        approvals.append(request)
        assert not sends.calls
        return approved

    provider = DeepSeekCreationReasoningProvider(
        approval=gate,
        ledger=ledger,
        recorder=recorder,
        reservation_cny=reservation,
        price_snapshot=price,
        transport=sends,
    )
    return provider, ledger, recorder, sends, approvals


def call(provider, context=None, request=None):
    return asyncio.run(
        provider.complete(
            request or ReasoningRequest("text system", "text user"),
            context or CancellationContext("run", 1),
        )
    )


def test_success_payload_records_identity_and_unknown_price():
    provider, ledger, recorder, transport, approvals = setup()
    result = call(provider)
    assert len(transport.calls) == len(approvals) == 1
    payload = transport.calls[0]
    assert payload["model"] == "deepseek-flash"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["stream"] is False and payload["max_tokens"] == 2048
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert all(isinstance(m["content"], str) for m in payload["messages"])
    assert "JSON" in payload["messages"][0]["content"]
    assert result.metadata.actual_model == "deepseek-flash"
    assert result.metadata.request_id == "request-123"
    assert result.metadata.usage.input_tokens is None
    assert result.metadata.elapsed_ms is not None
    assert result.metadata.usage.cost_cny is None
    assert ledger.reserved_cny == 3 and ledger.requests == 1 and ledger.frames == 0
    assert len(recorder.records) == 1
    assert recorder.records[0].metadata == result.metadata
    details = json.loads(result.metadata.execution_details)
    assert len(details["requestHash"]) == 64 and details["reservationCny"] == "3"


@pytest.mark.parametrize("mode", ["denied", "cancelled", "no_budget", "zero", "missing", "small"])
def test_pre_send_gates(mode):
    reservation = {"zero": Decimal(0), "missing": None, "small": Decimal("0.000001")}.get(
        mode, Decimal("11") if mode == "no_budget" else Decimal("3")
    )
    provider, ledger, recorder, transport, approvals = setup(
        approved=mode != "denied", reservation=reservation, price=DEEPSEEK_FLASH_20261004
    )
    context = CancellationContext("run", 1)
    if mode == "cancelled":
        context.cancelled.set()
    with pytest.raises((PermissionError, asyncio.CancelledError, AppError, ValueError)):
        call(provider, context)
    assert not transport.calls and not recorder.records and ledger.requests == 0
    if mode == "cancelled":
        assert not approvals


@pytest.mark.parametrize(
    "response",
    [
        HttpResponse(503, b"error"),
        HttpResponse(200, b"{"),
        HttpResponse(200, b" "),
        HttpResponse(200, b"x" * (MAX_RESPONSE_BYTES + 1)),
        response_body(
            choices=[{"finish_reason": "length", "message": {"role": "assistant", "content": "{}"}}]
        ),
        response_body(
            choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": "  "}}]
        ),
        response_body(
            choices=[{"finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}]
        ),
    ],
)
def test_bad_responses_single_send_keep_reservation(response):
    provider, ledger, recorder, transport, _ = setup(Transport(response))
    result = call(provider)
    assert result.status == ProviderStatus.FAILED and result.output is None
    assert len(transport.calls) == len(recorder.records) == 1
    assert ledger.reserved_cny == 3 and ledger.unresolved_attempts == 1
    assert recorder.records[0].error_code


@pytest.mark.parametrize(
    "failure",
    [
        TransportError("provider.timeout"),
        TransportError("provider.network"),
        RuntimeError("secret"),
    ],
)
def test_transport_errors_are_not_retried_or_logged(failure):
    provider, ledger, recorder, transport, _ = setup(Transport(failure=failure))
    result = call(provider)
    assert result.status == ProviderStatus.FAILED
    assert len(transport.calls) == 1 and ledger.reserved_cny == 3
    assert "secret" not in str(recorder.records)


@pytest.mark.parametrize(
    "changes",
    [
        {"usage": None},
        {"model": "unrecognized-model"},
        {"model": None},
        {"usage": {"prompt_tokens": 20, "completion_tokens": 10}},
    ],
)
def test_unknowns_remain_unknown(changes):
    provider, ledger, _, _, _ = setup(
        Transport(response_body(**changes)), price=DEEPSEEK_FLASH_20261004
    )
    result = call(provider)
    assert result.status == ProviderStatus.COMPLETED
    assert result.metadata.usage.cost_cny is None and ledger.reserved_cny == 3
    if changes.get("usage", False) is None:
        assert result.metadata.usage.input_tokens is None
    if "usage" in changes and changes["usage"]:
        assert result.metadata.usage.cached_input_tokens is None


def test_mid_send_cancel_records_unknown_and_never_retries():
    provider, ledger, recorder, transport, _ = setup()

    async def run():
        context = CancellationContext("run", 1)

        async def cancelling_post(payload, timeout_seconds):
            transport.calls.append(payload)
            context.cancelled.set()
            await asyncio.sleep(10)

        transport.post = cancelling_post
        return await provider.complete(ReasoningRequest("system", "user"), context)

    result = asyncio.run(run())
    assert result.status == ProviderStatus.CANCELLED
    assert len(transport.calls) == len(recorder.records) == 1
    assert ledger.reserved_cny == 3 and result.metadata.usage.cost_cny is None


def test_invalid_request_version_never_approves():
    provider, ledger, _, transport, approvals = setup()
    with pytest.raises(ValueError):
        call(provider, request=replace(ReasoningRequest("sys", "usr"), schema_version="other"))
    assert not transport.calls and not approvals and ledger.requests == 0


def test_known_usage_estimate_settles_after_recording():
    provider, ledger, recorder, transport, approvals = setup(
        Transport(
            response_body(
                usage={"prompt_tokens": 20, "completion_tokens": 10, "prompt_cache_hit_tokens": 0}
            )
        ),
        price=DEEPSEEK_FLASH_20261004,
    )
    original_post = transport.post

    async def checked_post(payload, timeout_seconds):
        assert len(approvals) == len(recorder.records) == ledger.requests == 1
        assert ledger.reserved_cny == 3
        assert recorder.records[0].status.value == "running"
        return await original_post(payload, timeout_seconds)

    transport.post = checked_post
    result = call(provider)
    assert result.metadata.usage.cost_cny > 0
    assert result.metadata.usage.cost_status.value == "estimated"
    assert ledger.known_cost_cny == result.metadata.usage.cost_cny
    assert ledger.reserved_cny == 0


def test_actual_timeout_records_unknown_once():
    provider, ledger, recorder, transport, _ = setup()

    async def slow_post(payload, timeout_seconds):
        transport.calls.append(payload)
        await asyncio.sleep(1)

    transport.post = slow_post
    result = call(provider, CancellationContext("run", 0.01))
    assert result.status == ProviderStatus.FAILED and result.error.code == "provider.timeout"
    assert len(transport.calls) == len(recorder.records) == 1
    assert ledger.reserved_cny == 3


def test_recorder_failure_does_not_send_or_release_reservation():
    provider, ledger, recorder, transport, _ = setup()

    async def failing_begin(*args):
        raise OSError("record unavailable")

    recorder.begin_invocation = failing_begin
    with pytest.raises(OSError):
        call(provider)
    assert not transport.calls and ledger.reserved_cny == 3


@pytest.mark.parametrize(
    "price",
    [
        None,
        replace(
            DEEPSEEK_FLASH_20261004,
            peak_uncached_input_per_million=Decimal(0),
            peak_output_per_million=Decimal(0),
        ),
        replace(DEEPSEEK_FLASH_20261004, version="invented"),
    ],
)
def test_unknown_or_forged_price_never_sends(price):
    provider, ledger, recorder, transport, _ = setup(price=price)
    with pytest.raises(ValueError, match="official pilot price"):
        call(provider)
    assert not transport.calls and not recorder.records and ledger.requests == 0


def test_tiny_reservation_cannot_send():
    provider, ledger, recorder, transport, _ = setup(reservation=Decimal("1e-12"))
    with pytest.raises(ValueError, match="upper bound"):
        call(provider)
    assert not transport.calls and not recorder.records and ledger.requests == 0


def test_bad_usage_preserves_valid_response_identities_and_unknown_reservation():
    provider, ledger, recorder, transport, _ = setup(
        Transport(response_body(usage={"prompt_tokens": True}))
    )
    result = call(provider)
    assert result.status == ProviderStatus.FAILED
    assert result.metadata.actual_model == "deepseek-flash"
    assert result.metadata.request_id == "request-123"
    assert result.metadata.usage.cost_cny is None
    assert result.metadata.usage.input_tokens is None
    assert recorder.records[0].metadata == result.metadata
    assert ledger.reserved_cny == 3 and len(transport.calls) == 1


@pytest.mark.parametrize(
    "prompt,schema",
    [
        ("plan-reasoning-prompt-v1", "creation-reasoning-v1"),
        ("creation-reasoning-prompt-v1", "plan-proposal-v1"),
        ("invented", "plan-proposal-v1"),
    ],
)
def test_plan_and_edit_versions_must_be_explicit_pairs(prompt, schema):
    provider, ledger, recorder, transport, approvals = setup()
    with pytest.raises(ValueError, match="version"):
        call(provider, request=ReasoningRequest("system", "user", prompt, schema))
    assert not transport.calls and not approvals
    assert ledger.requests == 0
