"""Independent single-frame static-observation provider; source identities never come from the model."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic
from typing import cast

from gamingcreator.application.pricing import PriceSnapshot, pricing_period
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.application.static_observation_generation import (
    MAX_FRAME_PARTS_PER_ACTOR,
    MAX_FRAME_PARTS_PER_GROUP,
    MAX_STATIC_GENERATION_RESPONSE_CONTENT_BYTES,
    STATIC_GENERATION_PROMPT,
    STATIC_GENERATION_PROMPT_VERSION,
    STATIC_GENERATION_SCHEMA_VERSION,
    STATIC_PART_GROUP_KINDS,
    StaticObservationOutput,
    StaticObservationRequest,
)
from gamingcreator.domain.actor_details import AttributeKind, AttributeStatus
from gamingcreator.domain.static_observations import (
    MAX_STATIC_OBSERVATION_ACTORS,
    StaticActor,
    StaticAttribute,
)

# Reuse only the bounded response/usage primitives, never old prompts or event parsing.
from gamingcreator.infrastructure.deepseek_vision import (
    _json,
    _SchemaError,
    _usage,
)
from gamingcreator.infrastructure.http_transport import (
    MAX_RESPONSE_BYTES,
    TransportError,
    VisionTransport,
)

PROMPT_VERSION = STATIC_GENERATION_PROMPT_VERSION
SCHEMA_VERSION = STATIC_GENERATION_SCHEMA_VERSION
_PART_GROUPS = frozenset(STATIC_PART_GROUP_KINDS)
_RESPONSE_ID = re.compile(r"[A-Za-z0-9_.:/-]{1,256}\Z")


class _ContentError(ValueError):
    """A bounded, whitelisted parse failure; never carries model text."""


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise _ContentError("duplicate")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    del value
    raise _ContentError("nonfinite")


def _content_object(content: str) -> dict[str, object]:
    if type(content) is not str or len(content.encode("utf-8")) > (
        MAX_STATIC_GENERATION_RESPONSE_CONTENT_BYTES
    ):
        raise _ContentError("size")
    try:
        decoded: object = json.loads(
            content, object_pairs_hook=_pairs, parse_constant=_invalid_constant
        )
    except (json.JSONDecodeError, RecursionError):
        raise _ContentError("json") from None
    if type(decoded) is not dict or set(cast(dict[str, object], decoded)) != {"actors"}:
        raise _ContentError("object")
    return cast(dict[str, object], decoded)


def _load_parts(value: object) -> tuple[StaticAttribute, ...]:
    if type(value) is not list or not 1 <= len(value) <= MAX_FRAME_PARTS_PER_ACTOR:
        raise _ContentError("parts")
    attributes: list[StaticAttribute] = []
    used_indexes: dict[str, set[int]] = {}
    for raw in cast(list[object], value):
        if type(raw) is not dict or set(cast(dict[str, object], raw)) != {
            "partGroup",
            "partIndex",
            "attributes",
        }:
            raise _ContentError("part")
        part = cast(dict[str, object], raw)
        group = part["partGroup"]
        if type(group) is not str or group not in _PART_GROUPS:
            raise _ContentError("part_group")
        index = part["partIndex"]
        maximum_index = MAX_FRAME_PARTS_PER_GROUP[group]
        if type(index) is not int or not 1 <= index <= maximum_index:
            raise _ContentError("part_index")
        group_indexes = used_indexes.setdefault(group, set())
        if index in group_indexes:
            raise _ContentError("part_duplicate")
        group_indexes.add(index)
        raw_attributes = part["attributes"]
        if type(raw_attributes) is not dict:
            raise _ContentError("part_attributes")
        attribute_map = cast(dict[str, object], raw_attributes)
        allowed = STATIC_PART_GROUP_KINDS[group]
        if not attribute_map or len(attribute_map) > len(allowed):
            raise _ContentError("part_attribute_count")
        part_id = f"{group}-{index}"
        for key, attribute_value in attribute_map.items():
            if type(attribute_value) is not str:
                raise _ContentError("part_attribute_value")
            kind = AttributeKind(key)
            if kind not in allowed:
                raise _ContentError("part_attribute_kind")
            attributes.append(
                StaticAttribute(group, part_id, kind, attribute_value, AttributeStatus.OBSERVED)
            )
    return tuple(attributes)


def parse_static_frame_observation(content: str) -> tuple[StaticActor, ...]:
    """Accept only this frame's actors and their explicit bounded local parts."""
    document = _content_object(content)
    raw_actors = document["actors"]
    if type(raw_actors) is not list or len(raw_actors) > MAX_STATIC_OBSERVATION_ACTORS:
        raise _ContentError("actors")
    actors: list[StaticActor] = []
    indexes: set[int] = set()
    for raw in cast(list[object], raw_actors):
        if type(raw) is not dict or set(cast(dict[str, object], raw)) != {
            "actorIndex",
            "parts",
        }:
            raise _ContentError("actor")
        actor = cast(dict[str, object], raw)
        index = actor["actorIndex"]
        if type(index) is not int or not 1 <= index <= MAX_STATIC_OBSERVATION_ACTORS:
            raise _ContentError("actor_index")
        if index in indexes:
            raise _ContentError("actor_duplicate")
        indexes.add(index)
        actors.append(StaticActor(f"actor-{index}", _load_parts(actor["parts"])))
    return tuple(sorted(actors, key=lambda item: item.actor_id))


def _image_media_type(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    return "application/octet-stream"


def _execution_details(
    *,
    request_hash: str,
    prompt_hash: str,
    requested_at: datetime,
    period: str,
    basis: str,
    dispatch_attempted: bool,
    http_status: int | None = None,
    response_sha256: str | None = None,
    response_bytes: int | None = None,
    content_bytes: int | None = None,
) -> str:
    document: dict[str, object] = {
        "requestHash": request_hash,
        "promptHash": prompt_hash,
        "inputFrames": 1,
        "period": period,
        "periodBasis": basis,
        "requestedAtUtc": requested_at.isoformat(),
        "dispatchAttempted": dispatch_attempted,
    }
    if http_status is not None:
        document["httpStatus"] = http_status
    if response_sha256 is not None:
        document["responseSha256"] = response_sha256
    if response_bytes is not None:
        document["responseBytes"] = response_bytes
    if content_bytes is not None:
        document["contentBytes"] = content_bytes
    return json.dumps(document, sort_keys=True)


class DeepSeekStaticObservationProvider:
    """One explicit image per request; a legal empty actor list is a successful observation."""

    def __init__(
        self,
        transport: VisionTransport,
        *,
        price_snapshot: PriceSnapshot | None = None,
    ) -> None:
        self._transport = transport
        self._price_snapshot = price_snapshot

    def _payload(self, request: StaticObservationRequest) -> dict[str, object]:
        identity = request.identity
        if (
            identity.prompt_version != PROMPT_VERSION
            or identity.schema_version != SCHEMA_VERSION
            or identity.prompt_hash != hashlib.sha256(STATIC_GENERATION_PROMPT.encode()).hexdigest()
        ):
            raise ValueError("Unsupported static observation identity.")
        evidence = request.evidence
        if evidence.kind != "image" or request.image_path != evidence.artifact_path.resolve():
            raise ValueError("Static observation request is not its registered frame.")
        try:
            if request.image_path.is_symlink() or not request.image_path.is_file():
                raise ValueError("Static observation image is missing.")
            with request.image_path.open("rb") as stream:
                data = stream.read(request.parameters.max_image_bytes + 1)
        except OSError:
            raise ValueError("Static observation image is unreadable.") from None
        if (
            len(data) > request.parameters.max_image_bytes
            or hashlib.sha256(data).hexdigest() != evidence.sha256
        ):
            raise ValueError("Changed or oversized static observation image.")
        image_url = f"data:{_image_media_type(data)};base64," + base64.b64encode(data).decode(
            "ascii"
        )
        blocks: list[dict[str, object]] = [
            {"type": "text", "text": json.dumps({"frame": 1})},
            {
                "type": "image_url",
                "image_url": {"url": image_url, "detail": request.parameters.image_detail},
            },
        ]
        return {
            "model": identity.model,
            "messages": [
                {"role": "system", "content": STATIC_GENERATION_PROMPT},
                {"role": "user", "content": blocks},
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "max_tokens": request.parameters.max_output_tokens,
            "temperature": 0,
            "stream": False,
        }

    async def observe(
        self, request: StaticObservationRequest, context: CancellationContext
    ) -> ProviderResult[StaticObservationOutput]:
        started = monotonic()
        requested_at = datetime.now(UTC)
        period, basis = pricing_period(requested_at)
        identity = request.identity
        metadata = InvocationMetadata(
            provider=identity.provider,
            requested_model=identity.model,
            actual_model=None,
            model_revision=None,
            prompt_version=identity.prompt_version,
            schema_version=identity.schema_version,
            attempt=0,
            usage=ProviderUsage(),
            price_version=None if self._price_snapshot is None else self._price_snapshot.version,
            execution_details=_execution_details(
                request_hash=request.proposal_sha256,
                prompt_hash=identity.prompt_hash,
                requested_at=requested_at,
                period=period,
                basis=basis,
                dispatch_attempted=False,
            ),
        )
        output: StaticObservationOutput | None = None
        error: ProviderFailure | None = None
        status = ProviderStatus.COMPLETED
        response_body: bytes | None = None
        response_status: int | None = None
        content_bytes: int | None = None
        try:
            context.check_cancelled()
            if request.run_id != context.run_id:
                raise ValueError("Wrong cancellation context.")
            payload = self._payload(request)
            remaining = request.parameters.timeout_seconds - (monotonic() - started)
            if remaining <= 0:
                raise TransportError("provider.timeout")
            metadata = replace(
                metadata,
                attempt=1,
                execution_details=_execution_details(
                    request_hash=request.proposal_sha256,
                    prompt_hash=identity.prompt_hash,
                    requested_at=requested_at,
                    period=period,
                    basis=basis,
                    dispatch_attempted=True,
                ),
            )
            pending = asyncio.create_task(self._transport.post(payload, remaining))
            cancelled = asyncio.create_task(context.cancelled.wait())
            try:
                done, _ = await asyncio.wait(
                    (pending, cancelled),
                    timeout=remaining,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancelled in done or context.cancelled.is_set():
                    raise asyncio.CancelledError
                if pending not in done:
                    raise TransportError("provider.timeout")
                response = pending.result()
            finally:
                pending.cancel()
                cancelled.cancel()
                await asyncio.gather(pending, cancelled, return_exceptions=True)
            response_body = response.body
            response_status = response.status_code
            if response.status_code != 200:
                code = (
                    "provider.auth"
                    if response.status_code in (401, 403)
                    else "provider.rate_limit"
                    if response.status_code == 429
                    else "provider.http"
                )
                error = ProviderFailure(
                    code, response.status_code == 429 or response.status_code >= 500
                )
            else:
                if len(response.body) > MAX_RESPONSE_BYTES:
                    raise TransportError("provider.response_limit")
                decoded = _json(response.body)
                actual = cast(str, decoded.get("model"))
                request_id = cast(str, decoded.get("id"))
                if any(
                    type(item) is not str or not _RESPONSE_ID.fullmatch(item)
                    for item in (actual, request_id)
                ):
                    raise ValueError("Missing response identity.")
                metadata = replace(metadata, actual_model=actual, request_id=request_id)
                usage = _usage(decoded)
                if self._price_snapshot is not None:
                    usage = self._price_snapshot.estimate_usage(
                        usage, actual, identity.model, period=period
                    )
                metadata = replace(metadata, usage=usage)
                choices = decoded.get("choices")
                if type(choices) is not list or len(choices) != 1:
                    raise ValueError("Invalid response choices.")
                choice = choices[0]
                if type(choice) is not dict:
                    raise ValueError("Invalid response choice.")
                choice_map = cast(dict[str, object], choice)
                if (
                    choice_map.get("finish_reason") != "stop"
                    or type(choice_map.get("message")) is not dict
                ):
                    raise ValueError("Incomplete response.")
                message = cast(dict[str, object], choice_map["message"])
                content = message.get("content")
                if message.get("role") != "assistant" or type(content) is not str:
                    raise ValueError("Invalid response message.")
                content_bytes = len(content.encode("utf-8"))
                output = StaticObservationOutput(parse_static_frame_observation(content))
        except asyncio.CancelledError:
            status, error = ProviderStatus.CANCELLED, ProviderFailure("provider.cancelled", False)
        except TransportError as failure:
            error = ProviderFailure(failure.code, failure.retryable)
        except (ValueError, TypeError, KeyError, _SchemaError):
            error = ProviderFailure(
                "provider.input" if metadata.attempt == 0 else "provider.schema", False
            )
        except OSError:
            error = ProviderFailure("provider.input", False)
        except Exception:
            error = ProviderFailure("provider.transport", False)
        if error is not None and status != ProviderStatus.CANCELLED:
            status = ProviderStatus.FAILED
        metadata = replace(
            metadata,
            elapsed_ms=max(0, int((monotonic() - started) * 1000)),
            execution_details=_execution_details(
                request_hash=request.proposal_sha256,
                prompt_hash=identity.prompt_hash,
                requested_at=requested_at,
                period=period,
                basis=basis,
                dispatch_attempted=metadata.attempt == 1,
                http_status=response_status,
                response_sha256=(
                    None if response_body is None else hashlib.sha256(response_body).hexdigest()
                ),
                response_bytes=None if response_body is None else len(response_body),
                content_bytes=content_bytes,
            ),
        )
        if output is not None:
            return ProviderResult(ProviderStatus.COMPLETED, output, metadata)
        if status is ProviderStatus.CANCELLED:
            return ProviderResult(
                ProviderStatus.CANCELLED,
                None,
                metadata,
                ProviderFailure("provider.cancelled", False),
            )
        return ProviderResult(
            ProviderStatus.FAILED,
            None,
            metadata,
            error if error is not None else ProviderFailure("provider.transport", False),
        )
