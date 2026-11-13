"""Approved single-send DeepSeek text reasoning with conservative billing records."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from decimal import Decimal
from hashlib import sha256
from time import monotonic
from typing import Any

from gamingcreator.application.brief_reasoning import PROMPT_VERSION as BRIEF_PROMPT_VERSION
from gamingcreator.application.brief_reasoning import SCHEMA_VERSION as BRIEF_SCHEMA_VERSION
from gamingcreator.application.budget import BudgetLedger, InvocationRecorder
from gamingcreator.application.creation_overlay_proposals import (
    PROMPT_VERSION as OVERLAY_PROMPT_VERSION,
)
from gamingcreator.application.creation_overlay_proposals import (
    SCHEMA_VERSION as OVERLAY_SCHEMA_VERSION,
)
from gamingcreator.application.creation_proposals import SCHEMA_VERSION, canonical
from gamingcreator.application.creation_reasoning import PROMPT_VERSION, ReasoningRequest
from gamingcreator.application.narration_reasoning import PROMPT_VERSION as NARRATION_PROMPT_VERSION
from gamingcreator.application.narration_reasoning import SCHEMA_VERSION as NARRATION_SCHEMA_VERSION
from gamingcreator.application.plan_proposals import SCHEMA_VERSION as PLAN_SCHEMA_VERSION
from gamingcreator.application.plan_reasoning import PROMPT_VERSION as PLAN_PROMPT_VERSION
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004, PriceSnapshot
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.application.publish_copy import PROMPT_VERSION as COPY_PROMPT_VERSION
from gamingcreator.application.publish_copy import SCHEMA_VERSION as COPY_SCHEMA_VERSION
from gamingcreator.application.storage import InvocationStatus
from gamingcreator.infrastructure.deepseek_vision import _json, _SchemaError, _usage
from gamingcreator.infrastructure.http_transport import (
    MAX_RESPONSE_BYTES,
    HttpResponse,
    HttpxVisionTransport,
    TransportError,
    VisionTransport,
)

ApprovalGate = Callable[[ReasoningRequest], Awaitable[bool]]
MODEL = "deepseek-flash"


def _price_hash(price: PriceSnapshot) -> str:
    return sha256(json.dumps(asdict(price), default=str, sort_keys=True).encode()).hexdigest()


_PILOT_PRICE_HASH = _price_hash(DEEPSEEK_FLASH_20261004)


def trusted_price_snapshot(price: PriceSnapshot | None) -> PriceSnapshot:
    """Pin every field of the pilot's official, versioned price snapshot."""
    if not isinstance(price, PriceSnapshot) or _price_hash(price) != _PILOT_PRICE_HASH:
        raise ValueError("An identified official pilot price snapshot is required.")
    return price


def _identity(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,200}", value):
        raise ValueError("Invalid response identity.")
    return value


async def _send(
    transport: VisionTransport,
    payload: dict[str, object],
    context: CancellationContext,
) -> HttpResponse:
    context.check_cancelled()
    pending = asyncio.create_task(transport.post(payload, context.timeout_seconds))
    cancelled = asyncio.create_task(context.cancelled.wait())
    try:
        done, _ = await asyncio.wait(
            (pending, cancelled),
            timeout=context.timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        context.check_cancelled()
        if pending not in done:
            raise TransportError("provider.timeout")
        return pending.result()
    finally:
        pending.cancel()
        cancelled.cancel()
        await asyncio.gather(pending, cancelled, return_exceptions=True)


class DeepSeekCreationReasoningProvider:
    def __init__(
        self,
        *,
        approval: ApprovalGate,
        ledger: BudgetLedger,
        recorder: InvocationRecorder,
        reservation_cny: Decimal | None,
        price_snapshot: PriceSnapshot | None = None,
        transport: VisionTransport | None = None,
        model: str = MODEL,
        max_output_tokens: int = 2048,
    ) -> None:
        if (
            model != MODEL
            or type(max_output_tokens) is not int
            or not 1 <= max_output_tokens <= 8192
        ):
            raise ValueError("Unsupported pilot model or output token limit.")
        self._approval = approval
        self._ledger = ledger
        self._recorder = recorder
        self._reservation = reservation_cny
        self._price = price_snapshot
        self._transport = transport if transport is not None else HttpxVisionTransport()
        self._model = model
        self._max_output_tokens = max_output_tokens

    def _payload(self, request: ReasoningRequest) -> dict[str, object]:
        if (request.prompt_version, request.schema_version) not in {
            (PROMPT_VERSION, SCHEMA_VERSION),
            (OVERLAY_PROMPT_VERSION, OVERLAY_SCHEMA_VERSION),
            (PLAN_PROMPT_VERSION, PLAN_SCHEMA_VERSION),
            ("plan-reasoning-prompt-v2", "plan-proposal-v2"),
            ("plan-reasoning-prompt-v3", "plan-proposal-v3"),
            (COPY_PROMPT_VERSION, COPY_SCHEMA_VERSION),
            (BRIEF_PROMPT_VERSION, BRIEF_SCHEMA_VERSION),
            (NARRATION_PROMPT_VERSION, NARRATION_SCHEMA_VERSION),
        }:
            raise ValueError("Unsupported reasoning request version.")
        if any(not isinstance(s, str) or not s.strip() for s in (request.system, request.user)):
            raise ValueError("Reasoning messages must be nonempty text.")
        if len(request.system.encode()) + len(request.user.encode()) > 200_000:
            raise ValueError("Reasoning request exceeds text limit.")
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system + "\nReturn valid JSON only."},
                {"role": "user", "content": request.user},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "stream": False,
            "max_tokens": self._max_output_tokens,
        }

    def _check_reservation(self) -> None:
        price = trusted_price_snapshot(self._price)
        minimum = price.reservation_cny(price.context_limit_tokens, self._max_output_tokens)
        if (
            not isinstance(self._reservation, Decimal)
            or not self._reservation.is_finite()
            or self._reservation < minimum
        ):
            raise ValueError("Reservation is below the conservative request upper bound.")

    def _decode(
        self,
        response: HttpResponse,
        metadata: InvocationMetadata,
    ) -> tuple[dict[str, Any], InvocationMetadata]:
        if len(response.body) > MAX_RESPONSE_BYTES:
            raise TransportError("provider.response_limit")
        if response.status_code != 200:
            raise ValueError("Non-success response.")
        decoded = _json(response.body)
        actual, request_id = _identity(decoded.get("model")), _identity(decoded.get("id"))
        metadata = replace(metadata, actual_model=actual, request_id=request_id)
        return dict(decoded), metadata

    @staticmethod
    def _content(decoded: dict[str, Any]) -> dict[str, Any]:
        choices = decoded.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ValueError("Invalid completion choices.")
        choice = choices[0]
        message = choice.get("message")
        if choice.get("finish_reason") != "stop" or not isinstance(message, dict):
            raise ValueError("Incomplete completion.")
        content = message.get("content")
        if (
            message.get("role") != "assistant"
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError("Missing assistant JSON.")
        parsed = _json(content)
        if not parsed:
            raise ValueError("Empty reasoning JSON.")
        return dict(parsed)

    async def complete(
        self,
        request: ReasoningRequest,
        context: CancellationContext,
    ) -> ProviderResult[dict[str, Any]]:
        payload = self._payload(request)
        context.check_cancelled()
        if await self._approval(request) is not True:
            raise PermissionError("Explicit request approval is required before sending.")
        context.check_cancelled()
        self._check_reservation()
        reservation = self._ledger.reserve(frames=0, reservation_cny=self._reservation)
        digest = sha256(
            canonical({"request": asdict(request), "payload": payload}).encode()
        ).hexdigest()
        metadata = InvocationMetadata(
            "deepseek",
            self._model,
            None,
            None,
            request.prompt_version,
            request.schema_version,
            1,
            ProviderUsage(),
            price_version=None if self._price is None else self._price.version,
            execution_details=json.dumps(
                {
                    "requestHash": digest,
                    "inputFrames": 0,
                    "reservationCny": str(reservation.reservation_cny),
                }
            ),
        )
        cost_cny = None
        try:
            await self._recorder.begin_invocation(
                reservation.reservation_id, context.run_id, "creation-reasoning", digest, metadata
            )
            result = await self._invoke(payload, context, metadata, reservation.reservation_id)
            cost_cny = result.metadata.usage.cost_cny
            return result
        finally:
            # Finish/recorder failures and cancellation must never free unknown charges.
            self._ledger.settle(reservation, cost_cny)

    async def _invoke(
        self,
        payload: dict[str, object],
        context: CancellationContext,
        metadata: InvocationMetadata,
        invocation_id: str,
    ) -> ProviderResult[dict[str, Any]]:
        started = monotonic()
        status = ProviderStatus.COMPLETED
        output: dict[str, Any] | None = None
        error: ProviderFailure | None = None
        try:
            response = await _send(self._transport, payload, context)
            decoded, metadata = self._decode(response, metadata)
            usage = _usage(decoded)
            price = trusted_price_snapshot(self._price)
            metadata = replace(
                metadata,
                usage=price.estimate_usage(
                    usage, metadata.actual_model, self._model, period="peak"
                ),
            )
            output = self._content(decoded)
        except asyncio.CancelledError:
            status, error = ProviderStatus.CANCELLED, ProviderFailure("provider.cancelled", False)
        except (TransportError, TimeoutError) as failure:
            status = ProviderStatus.FAILED
            code = failure.code if isinstance(failure, TransportError) else "provider.timeout"
            error = ProviderFailure(code, False)
        except (ValueError, TypeError, KeyError, _SchemaError):
            status, error = ProviderStatus.FAILED, ProviderFailure("provider.schema", False)
        except Exception:
            status, error = ProviderStatus.FAILED, ProviderFailure("provider.transport", False)
        metadata = replace(metadata, elapsed_ms=max(0, int((monotonic() - started) * 1000)))
        await self._recorder.finish_invocation(
            invocation_id,
            InvocationStatus(status.value),
            metadata,
            None if error is None else error.code,
        )
        return ProviderResult(status, output, metadata, error)
