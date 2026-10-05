"""Independent, single-send actor refinement. Source identities never come from the model."""

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from gamingcreator.application.detail_refinement import (
    REFINEMENT_SCHEMA_VERSION,
    DetailRefinementRequest,
    RefinementIdentity,
    request_hash,
)
from gamingcreator.application.pricing import PriceSnapshot, pricing_period
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.domain.actor_details import (
    ActorDetail,
    AttributeKind,
    AttributeStatus,
    CandidateDetail,
    DetailAttribute,
    ShotDetail,
    source_range_for_evidence,
)

# Reuse only the existing bounded JPEG/JSON/usage primitives, never base prompts/event parsing.
from gamingcreator.infrastructure.deepseek_vision import _jpeg_width, _json, _SchemaError, _usage
from gamingcreator.infrastructure.http_transport import (
    MAX_RESPONSE_BYTES,
    TransportError,
    VisionTransport,
)

PROMPT_VERSION = "actor-detail-refinement-v2"
PROMPT = """Observe only the supplied registered image IDs within one candidate.
Return a JSON object with exactly shots and notes arrays, no source times or identities.
shots has at most 9 objects with exactly shotId, evidenceIds, environment, actors.
Use distinct local shot IDs; each frame belongs to at most one continuous shot.
Keep cuts separate; never link actor identity across shots. Frames may remain unassigned.
actors has at most 8 objects with exactly actorId, description, attributes.
Use distinct actor IDs within each shot and a neutral visible description of at most 500 characters.
Do not infer a controlled player, character name, weapon class, or action from game context.
environment and attributes have at most 16 objects with exactly partId, kind, value, status, evidenceIds.
Use the same local partId only for the same visible body/garment/held object within one actor.
All evidenceIds must be supplied IDs, ordered by source time and within their shot.
status is observed or uncertain. Omit invisible/unknown attributes; uncertain is never a positive fact.
hair_color and clothing_color values: white, black, red, blue, brown, orange, gray, green, yellow, purple, light, dark.
clothing_shape values: upper_garment, coat, scarf, shorts, trousers, armor, gloves.
held_shape values: flat_object, blue_flat_object, long_rod, curved_object.
held_class values: weapon, staff, tool; shape alone does not establish class.
action values: look_up, move, run, jump, raise_item, shoot; cite at least two different frames showing the action.
effect values: light_arc, light_ring, projectile.
environment values: water, stone_platform, sandy_ground, indoors, outdoors; only environment may contain this kind.
No actor attribute may use environment. Static attributes may cite one frame; never extrapolate across gaps.
notes has at most 16 nonempty strings of at most 500 characters. Use Chinese descriptions/notes.
When evidence is insufficient return {"shots":[],"notes":["视觉证据不足，待核对。"]}.
"""


def provider_refinement_identity() -> RefinementIdentity:
    return RefinementIdentity(
        PROMPT_VERSION,
        hashlib.sha256(PROMPT.encode()).hexdigest(),
        REFINEMENT_SCHEMA_VERSION,
        "deepseek",
        "deepseek-flash",
    )


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Unexpected refinement fields.")
    return value


def _list(value: object, maximum: int) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        raise ValueError("Invalid refinement collection.")
    return value


def _string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("Expected a refinement string.")
    return value


def parse_detail(content: str, request: DetailRefinementRequest) -> CandidateDetail:
    """Reject model clocks and foreign IDs; derive every interval from registered frames."""
    value = _object(_json(content), {"shots", "notes"})
    evidence = {item.evidence_id: item for item in request.evidence}

    def ids(raw: object) -> tuple[str, ...]:
        entries = _list(raw, 9)
        if not entries or any(type(item) is not str or item not in evidence for item in entries):
            raise ValueError("Unknown frame reference.")
        return tuple(entries)  # type: ignore[arg-type]

    def attributes(raw: object) -> tuple[DetailAttribute, ...]:
        result = []
        for item in _list(raw, 16):
            attr = _object(item, {"partId", "kind", "value", "status", "evidenceIds"})
            refs = ids(attr["evidenceIds"])
            result.append(
                DetailAttribute(
                    _string(attr["partId"]),
                    AttributeKind(_string(attr["kind"])),
                    _string(attr["value"]),
                    AttributeStatus(_string(attr["status"])),
                    refs,
                    source_range_for_evidence(tuple(evidence[ref] for ref in refs)),
                )
            )
        return tuple(result)

    shots = []
    for item in _list(value["shots"], 9):
        shot = _object(item, {"shotId", "evidenceIds", "environment", "actors"})
        refs = ids(shot["evidenceIds"])
        actors = []
        for raw in _list(shot["actors"], 8):
            actor = _object(raw, {"actorId", "description", "attributes"})
            actors.append(
                ActorDetail(
                    _string(shot["shotId"]),
                    _string(actor["actorId"]),
                    _string(actor["description"]),
                    attributes(actor["attributes"]),
                )
            )
        shots.append(
            ShotDetail(
                _string(shot["shotId"]),
                source_range_for_evidence(tuple(evidence[ref] for ref in refs)),
                refs,
                attributes(shot["environment"]),
                tuple(actors),
            )
        )
    if request.base_prompt_hash is None:
        raise ValueError("Missing base prompt identity.")
    return CandidateDetail(
        request.run_id,
        request.event_id.split(":")[1],
        request.event_id,
        request.candidate_id,
        request.event_fingerprint,
        request.media_sha256,
        request.configuration_hash,
        request.pipeline_version,
        request.base_prompt_version,
        request.base_prompt_hash,
        request.identity.prompt_hash,
        request.source_range,
        request.evidence,
        tuple(shots),
        tuple(_list(value["notes"], 16)),  # type: ignore[arg-type]
    )


class DeepSeekDetailRefinementProvider:
    _prompt = PROMPT
    _identity = staticmethod(provider_refinement_identity)
    _parse = staticmethod(parse_detail)

    def __init__(
        self,
        transport: VisionTransport,
        image_paths: dict[str, Path],
        *,
        price_snapshot: PriceSnapshot | None = None,
    ) -> None:
        self._transport = transport
        self._image_paths = dict(image_paths)
        self._price_snapshot = price_snapshot

    def _payload(self, request: DetailRefinementRequest) -> dict[str, object]:
        if request.identity != self._identity():
            raise ValueError("Unsupported refinement prompt identity.")
        source_range_for_evidence(request.evidence)
        media_id = request.event_id.split(":")[1]
        if not re.fullmatch(
            re.escape(f"{request.run_id}:{media_id}:event:") + r"[0-9a-f]{24}", request.event_id
        ):
            raise ValueError("Invalid candidate namespace.")
        if len(request.evidence) > request.settings.max_images:
            raise ValueError("Too many refinement frames.")
        blocks: list[dict[str, object]] = []
        for item in request.evidence:
            if (
                not request.source_range.start_us
                <= item.source_time.time_us
                < request.source_range.end_us
                or item.source_time.duration_us != request.source_range.duration_us
                or not item.evidence_id.startswith(f"{request.run_id}:{media_id}:image:")
            ):
                raise ValueError("Evidence outside candidate.")
            with self._image_paths[item.evidence_id].open("rb") as stream:
                data = stream.read(request.settings.max_image_bytes + 1)
            if (
                len(data) > request.settings.max_image_bytes
                or hashlib.sha256(data).hexdigest() != item.image_sha256
                or _jpeg_width(data) > request.settings.max_image_width
            ):
                raise ValueError("Changed or oversized refinement image.")
            blocks.extend(
                [
                    {"type": "text", "text": json.dumps({"evidenceId": item.evidence_id})},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,"
                            + base64.b64encode(data).decode("ascii"),
                            "detail": request.settings.image_detail,
                        },
                    },
                ]
            )
        return {
            "model": request.identity.requested_model,
            "messages": [
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": blocks},
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "max_tokens": request.settings.max_output_tokens,
            "temperature": 0,
            "stream": False,
        }

    async def refine(
        self,
        request: DetailRefinementRequest,
        context: CancellationContext,
    ) -> ProviderResult[CandidateDetail]:
        started = monotonic()
        requested_at = datetime.now(UTC)
        period, basis = pricing_period(requested_at)
        metadata = InvocationMetadata(
            request.identity.provider,
            request.identity.requested_model,
            None,
            None,
            request.identity.prompt_version,
            request.identity.schema_version,
            0,
            ProviderUsage(),
            price_version=None if self._price_snapshot is None else self._price_snapshot.version,
            execution_details=json.dumps(
                {
                    "requestHash": request_hash(request),
                    "promptHash": request.identity.prompt_hash,
                    "inputFrames": len(request.evidence),
                    "period": period,
                    "periodBasis": basis,
                    "requestedAtUtc": requested_at.isoformat(),
                },
                sort_keys=True,
            ),
        )
        output = None
        error = None
        status = ProviderStatus.COMPLETED
        try:
            context.check_cancelled()
            if request.run_id != context.run_id:
                raise ValueError("Wrong cancellation context.")
            payload = self._payload(request)
            remaining = min(context.timeout_seconds, request.settings.timeout_seconds) - (
                monotonic() - started
            )
            if remaining <= 0:
                raise TransportError("provider.timeout")
            metadata = replace(metadata, attempt=1)
            pending = asyncio.create_task(self._transport.post(payload, remaining))
            cancelled = asyncio.create_task(context.cancelled.wait())
            try:
                done, _ = await asyncio.wait(
                    (pending, cancelled), timeout=remaining, return_when=asyncio.FIRST_COMPLETED
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
                actual, request_id = _string(decoded.get("model")), _string(decoded.get("id"))
                if any(
                    type(item) is not str or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", item)
                    for item in (actual, request_id)
                ):
                    raise ValueError("Missing response identity.")
                metadata = replace(metadata, actual_model=actual, request_id=request_id)
                usage = _usage(decoded)
                if self._price_snapshot is not None:
                    usage = self._price_snapshot.estimate_usage(
                        usage, actual, request.identity.requested_model, period=period
                    )
                metadata = replace(metadata, usage=usage)
                choices = _list(decoded["choices"], 1)
                if len(choices) != 1 or type(choices[0]) is not dict:
                    raise ValueError("Invalid response choices.")
                choice = choices[0]
                if choice.get("finish_reason") != "stop" or type(choice.get("message")) is not dict:
                    raise ValueError("Incomplete response.")
                message = choice["message"]
                if message.get("role") != "assistant" or type(message.get("content")) is not str:
                    raise ValueError("Invalid response message.")
                output = self._parse(message["content"], request)
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
        metadata = replace(metadata, elapsed_ms=max(0, int((monotonic() - started) * 1000)))
        return ProviderResult(status, output, metadata, error)
