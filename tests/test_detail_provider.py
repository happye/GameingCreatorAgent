"""Single-send refinement transport fixtures, never paid HTTP or human acceptance."""

import asyncio
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_deepseek_vision import request_fixture
from test_detail_budget_sidecar import EVENT, timeline

from gamingcreator.application.actor_detail_matching import match_actor_details
from gamingcreator.application.detail_refinement import prepare_refinement
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext, CostStatus, ProviderStatus
from gamingcreator.domain.actor_details import (
    AttributeConstraint,
    AttributeKind,
    MatchStatus,
    QueryConstraint,
)
from gamingcreator.infrastructure.deepseek_detail_refinement import (
    PROMPT,
    DeepSeekDetailRefinementProvider,
    parse_detail,
    provider_refinement_identity,
)
from gamingcreator.infrastructure.http_transport import HttpResponse, TransportError


def prepared_fixture(tmp_path: Path):
    images = request_fixture(tmp_path, frames=3).evidence
    stored = timeline()
    registered = []
    for image, original in zip(images, stored.evidence[:3], strict=True):
        registered.append(replace(original, artifact_path=image.artifact_path, sha256=image.sha256))
    stored = replace(stored, evidence=(*registered, *stored.evidence[3:]))
    request = prepare_refinement(stored, EVENT, identity=provider_refinement_identity()).request
    assert request is not None
    return request, {item.evidence_id: item.artifact_path for item in registered}


def visible_detail(request):
    ids = [item.evidence_id for item in request.evidence]
    return {
        "shots": [
            {
                "shotId": "shot-1",
                "evidenceIds": ids,
                "environment": [],
                "actors": [
                    {
                        "actorId": "actor-1",
                        "description": "左侧可见主体，控制身份待核对。",
                        "attributes": [
                            {
                                "partId": "hair",
                                "kind": "hair_color",
                                "value": "white",
                                "status": "observed",
                                "evidenceIds": [ids[0]],
                            },
                            {
                                "partId": "held-1",
                                "kind": "held_shape",
                                "value": "blue_flat_object",
                                "status": "observed",
                                "evidenceIds": [ids[0]],
                            },
                            {
                                "partId": "held-1",
                                "kind": "held_class",
                                "value": "weapon",
                                "status": "uncertain",
                                "evidenceIds": [ids[0]],
                            },
                        ],
                    }
                ],
            }
        ],
        "notes": ["不能确认持有物用途。"],
    }


def response(content, *, model="deepseek-flash", usage=True, finish="stop"):
    value = {
        "id": "refine-request-1",
        "model": model,
        "choices": [
            {
                "finish_reason": finish,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content, ensure_ascii=False),
                },
            }
        ],
    }
    if usage:
        value["usage"] = {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_cache_hit_tokens": 10,
        }
    return HttpResponse(200, json.dumps(value, ensure_ascii=False).encode())


class Transport:
    def __init__(self, reply):
        self.reply = reply
        self.payloads = []

    async def post(self, payload, timeout_seconds):
        self.payloads.append(payload)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def execute(request, paths, reply):
    transport = Transport(reply)
    provider = DeepSeekDetailRefinementProvider(
        transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    result = asyncio.run(provider.refine(request, CancellationContext(request.run_id, 5)))
    return result, transport


def test_independent_prompt_and_registered_images_with_program_source_clock(tmp_path):
    request, paths = prepared_fixture(tmp_path)
    result, transport = execute(request, paths, response(visible_detail(request)))
    assert result.status == ProviderStatus.COMPLETED and result.output is not None
    assert request.identity.prompt_hash == hashlib.sha256(PROMPT.encode()).hexdigest()
    assert request.identity.prompt_hash != request.base_prompt_hash
    assert len(transport.payloads) == 1
    payload = transport.payloads[0]
    assert payload["messages"][0]["content"] == PROMPT
    blocks = payload["messages"][1]["content"]
    assert [
        json.loads(block["text"])["evidenceId"] for block in blocks if block["type"] == "text"
    ] == [item.evidence_id for item in request.evidence]
    assert all(
        block["image_url"]["detail"] == "original"
        for block in blocks
        if block["type"] == "image_url"
    )
    attribute = result.output.shots[0].actors[0].attributes[0]
    assert (attribute.source_range.start_us, attribute.source_range.end_us) == (
        28_000_000,
        28_000_001,
    )
    assert result.output.source_range == request.source_range
    assert result.metadata.actual_model == "deepseek-flash"
    assert result.metadata.request_id == "refine-request-1" and result.metadata.attempt == 1
    assert result.metadata.elapsed_ms is not None
    assert result.metadata.usage.cost_status == CostStatus.ESTIMATED
    query = QueryConstraint((AttributeConstraint(AttributeKind.HELD_CLASS, "weapon", "held"),))
    assert match_actor_details(result.output, query).status != MatchStatus.FULL


@pytest.mark.parametrize(
    "mutation",
    [
        "model_clock",
        "foreign",
        "cross_shot",
        "duplicate",
        "reverse",
        "single_action",
        "static_action",
        "unknown_value",
        "unknown_field",
    ],
)
def test_schema_rejects_untrusted_support_and_keeps_returned_usage(tmp_path, mutation):
    request, paths = prepared_fixture(tmp_path)
    content = visible_detail(request)
    shot = content["shots"][0]
    attr = shot["actors"][0]["attributes"][0]
    if mutation == "model_clock":
        attr["sourceRange"] = {"startUs": 0, "endUs": 1}
    elif mutation == "foreign":
        attr["evidenceIds"] = ["another:media:image:000000"]
    elif mutation == "cross_shot":
        shot["evidenceIds"] = shot["evidenceIds"][1:]
    elif mutation == "duplicate":
        shot["evidenceIds"].append(shot["evidenceIds"][0])
    elif mutation == "reverse":
        shot["evidenceIds"].reverse()
    elif mutation in ("single_action", "static_action"):
        attr.update(kind="action", value="jump")
        if mutation == "static_action":
            attr["evidenceIds"] = shot["evidenceIds"][:2]  # Equal JPEG content cannot prove motion.
    elif mutation == "unknown_value":
        attr["value"] = "rainbow"
    else:
        content["accepted"] = True
    result, transport = execute(request, paths, response(content))
    assert result.status == ProviderStatus.FAILED and result.output is None
    assert result.error.code == "provider.schema" and len(transport.payloads) == 1
    assert result.metadata.usage.input_tokens == 100 and result.metadata.usage.cost_cny is not None


def test_separate_actors_do_not_satisfy_a_compound_query(tmp_path):
    request, _paths = prepared_fixture(tmp_path)
    value = visible_detail(request)
    actor = value["shots"][0]["actors"][0]
    held = actor["attributes"][1:]
    actor["attributes"] = actor["attributes"][:1]
    value["shots"][0]["actors"].append(
        {"actorId": "actor-2", "description": "另一个主体。", "attributes": held}
    )
    detail = parse_detail(json.dumps(value), request)
    query = QueryConstraint(
        (
            AttributeConstraint(AttributeKind.HAIR_COLOR, "white", "hair"),
            AttributeConstraint(AttributeKind.HELD_SHAPE, "blue_flat_object", "held"),
        )
    )
    assert match_actor_details(detail, query).status == MatchStatus.PARTIAL


def test_action_interval_uses_two_different_registered_frames(tmp_path):
    request, _ = prepared_fixture(tmp_path)
    request = replace(
        request,
        evidence=tuple(
            replace(item, image_sha256=str(index + 1) * 64)
            for index, item in enumerate(request.evidence)
        ),
    )
    value = visible_detail(request)
    attr = value["shots"][0]["actors"][0]["attributes"][0]
    attr.update(
        kind="action", value="jump", evidenceIds=[item.evidence_id for item in request.evidence[:2]]
    )
    detail = parse_detail(json.dumps(value), request)
    interval = detail.shots[0].actors[0].attributes[0].source_range
    assert (interval.start_us, interval.end_us) == (28_000_000, 28_500_001)


@pytest.mark.parametrize("damage", ["hash", "width", "bytes", "missing", "identity"])
def test_bad_input_never_sends(tmp_path, damage):
    request, paths = prepared_fixture(tmp_path)
    first = paths[request.evidence[0].evidence_id]
    if damage == "hash":
        first.write_bytes(b"changed")
    elif damage == "width":
        request = replace(request, settings=replace(request.settings, max_image_width=256))
    elif damage == "bytes":
        request = replace(request, settings=replace(request.settings, max_image_bytes=10))
    elif damage == "missing":
        paths = {}
    else:
        request = replace(request, identity=replace(request.identity, prompt_hash="a" * 64))
    result, transport = execute(request, paths, response(visible_detail(request)))
    assert result.status == ProviderStatus.FAILED and result.error.code == "provider.input"
    assert not transport.payloads and result.metadata.attempt == 0


@pytest.mark.parametrize(
    "reply",
    [HttpResponse(429, b""), HttpResponse(503, b""), TransportError("provider.network", True)],
)
def test_retryable_failure_is_one_call_with_unknown_cost(tmp_path, reply):
    request, paths = prepared_fixture(tmp_path)
    result, transport = execute(request, paths, reply)
    assert result.status == ProviderStatus.FAILED and result.error.retryable
    assert len(transport.payloads) == 1 and result.metadata.usage.cost_cny is None


@pytest.mark.parametrize("model,usage", [("unknown-model", True), ("deepseek-flash", False)])
def test_unknown_tariff_or_usage_keeps_cost_null(tmp_path, model, usage):
    request, paths = prepared_fixture(tmp_path)
    result, _ = execute(request, paths, response(visible_detail(request), model=model, usage=usage))
    assert result.status == ProviderStatus.COMPLETED
    assert (
        result.metadata.usage.cost_cny is None
        and result.metadata.usage.cost_status == CostStatus.UNVERIFIED
    )


def test_truncated_response_preserves_usage_and_does_not_publish(tmp_path):
    request, paths = prepared_fixture(tmp_path)
    result, _ = execute(request, paths, response(visible_detail(request), finish="length"))
    assert result.status == ProviderStatus.FAILED and result.output is None
    assert result.metadata.usage.output_tokens == 20


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_or_context_cancel_closes_transport_without_retry(tmp_path, cancel):
    request, paths = prepared_fixture(tmp_path)
    entered = asyncio.Event()
    closed = []

    class Waiting:
        async def post(self, payload, timeout_seconds):
            entered.set()
            try:
                await asyncio.Future()
            finally:
                closed.append(True)

    async def run():
        context = CancellationContext(request.run_id, 0.1)
        task = asyncio.create_task(
            DeepSeekDetailRefinementProvider(Waiting(), paths).refine(request, context)
        )
        await entered.wait()
        if cancel:
            context.cancelled.set()
        return await task

    result = asyncio.run(run())
    assert result.status == (ProviderStatus.CANCELLED if cancel else ProviderStatus.FAILED)
    assert result.error.code == ("provider.cancelled" if cancel else "provider.timeout")
    assert closed == [True] and result.metadata.usage.cost_cny is None
