"""Nested parts preserve source evidence and avoid cross-item matches; no real HTTP."""

import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest
from test_detail_budget_sidecar import EVENT, OTHER, timeline
from test_detail_provider import Transport, prepared_fixture, response

from gamingcreator.application.actor_detail_matching import match_actor_details
from gamingcreator.application.detail_refinement import prepare_refinement, request_hash
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext, CostStatus, ProviderStatus
from gamingcreator.domain.actor_details import (
    AttributeConstraint,
    AttributeKind,
    MatchStatus,
    QueryConstraint,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar
from gamingcreator.infrastructure.deepseek_detail_parts import (
    PROMPT,
    DeepSeekDetailPartsProvider,
    parse_parts_detail,
    provider_parts_identity,
)
from gamingcreator.infrastructure.deepseek_detail_refinement import (
    PROMPT as V2_PROMPT,
)
from gamingcreator.infrastructure.deepseek_detail_refinement import (
    DeepSeekDetailRefinementProvider,
    provider_refinement_identity,
)
from gamingcreator.infrastructure.deepseek_vision import _SchemaError
from gamingcreator.infrastructure.http_transport import (
    MAX_RESPONSE_BYTES,
    HttpResponse,
    TransportError,
)


def parts_fixture(tmp_path):
    request, paths = prepared_fixture(tmp_path)
    return replace(request, identity=provider_parts_identity()), paths


def attribute(kind, value, frame_id, *, status="observed"):
    return {"kind": kind, "value": value, "status": status, "evidenceIds": [frame_id]}


def visible_parts(request):
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
                        "description": "左侧可见白发主体，控制身份待核对。",
                        "parts": [
                            {
                                "partId": "hair-1",
                                "partGroup": "hair",
                                "attributes": [attribute("hair_color", "white", ids[0])],
                            },
                            {
                                "partId": "coat-1",
                                "partGroup": "clothing",
                                "attributes": [
                                    attribute("clothing_shape", "coat", ids[0]),
                                    attribute("clothing_color", "red", ids[0]),
                                ],
                            },
                            {
                                "partId": "held-1",
                                "partGroup": "held_item",
                                "attributes": [
                                    attribute("held_shape", "blue_flat_object", ids[0]),
                                    attribute("held_class", "weapon", ids[0], status="uncertain"),
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
        "notes": ["不能确认持有物用途。"],
    }


def parse(request, content):
    return parse_parts_detail(json.dumps(content, ensure_ascii=False), request)


def coat_query(color="red"):
    return QueryConstraint(
        (
            AttributeConstraint(AttributeKind.CLOTHING_SHAPE, "coat", "garment"),
            AttributeConstraint(AttributeKind.CLOTHING_COLOR, color, "garment"),
        )
    )


def execute(request, paths, reply):
    transport = Transport(reply)
    provider = DeepSeekDetailPartsProvider(transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004)
    result = asyncio.run(provider.refine(request, CancellationContext(request.run_id, 5)))
    return result, transport


def test_same_nested_garment_matches_shape_and_color_without_changing_domain(tmp_path):
    request, _ = parts_fixture(tmp_path)
    detail = parse(request, visible_parts(request))
    match = match_actor_details(detail, coat_query())
    assert match.status == MatchStatus.FULL
    attributes = detail.shots[0].actors[0].attributes
    assert [item.part_id for item in attributes[1:3]] == ["coat-1", "coat-1"]
    assert attributes[1].source_range == attributes[2].source_range
    assert attributes[1].source_range.start_us == 28_000_000
    assert attributes[1].source_range.end_us == 28_000_001
    assert detail.detail_identity_hash == request.identity.prompt_hash
    assert detail.source_range == request.source_range


def test_shape_and_color_in_different_parts_are_not_merged(tmp_path):
    request, _ = parts_fixture(tmp_path)
    content = visible_parts(request)
    parts = content["shots"][0]["actors"][0]["parts"]
    color = parts[1]["attributes"].pop()
    parts.append({"partId": "scarf-1", "partGroup": "clothing", "attributes": [color]})
    assert match_actor_details(parse(request, content), coat_query()).status == MatchStatus.PARTIAL


def test_identical_colors_of_two_garments_do_not_merge_shape_attributes(tmp_path):
    request, _ = parts_fixture(tmp_path)
    content = visible_parts(request)
    parts = content["shots"][0]["actors"][0]["parts"]
    frame = request.evidence[0].evidence_id
    parts.append(
        {
            "partId": "scarf-1",
            "partGroup": "clothing",
            "attributes": [
                attribute("clothing_shape", "scarf", frame),
                attribute("clothing_color", "red", frame),
            ],
        }
    )
    detail = parse(request, content)
    query = QueryConstraint(
        (
            AttributeConstraint(AttributeKind.CLOTHING_SHAPE, "coat", "garment"),
            AttributeConstraint(AttributeKind.CLOTHING_SHAPE, "scarf", "garment"),
            AttributeConstraint(AttributeKind.CLOTHING_COLOR, "red", "garment"),
        )
    )
    assert match_actor_details(detail, query).status == MatchStatus.PARTIAL
    assert {item.part_id for item in detail.shots[0].actors[0].attributes} >= {"coat-1", "scarf-1"}


@pytest.mark.parametrize("split_scope", ["actor", "shot"])
def test_separate_actor_or_shot_cannot_supply_other_conditions(tmp_path, split_scope):
    request, _ = parts_fixture(tmp_path)
    content = visible_parts(request)
    shot = content["shots"][0]
    actor = shot["actors"][0]
    other = {"actorId": "actor-2", "description": "另一个主体。", "parts": actor["parts"][1:]}
    actor["parts"] = actor["parts"][:1]
    if split_scope == "actor":
        shot["actors"].append(other)
    else:
        later = request.evidence[1].evidence_id
        shot["evidenceIds"] = shot["evidenceIds"][:1]
        for part in other["parts"]:
            for item in part["attributes"]:
                item["evidenceIds"] = [later]
        content["shots"].append(
            {"shotId": "shot-2", "evidenceIds": [later], "environment": [], "actors": [other]}
        )
    query = QueryConstraint(
        (
            AttributeConstraint(AttributeKind.HAIR_COLOR, "white", "hair"),
            *coat_query().actor_all,
        )
    )
    assert match_actor_details(parse(request, content), query).status == MatchStatus.PARTIAL


def test_same_part_without_common_support_frame_does_not_match(tmp_path):
    request, _ = parts_fixture(tmp_path)
    content = visible_parts(request)
    attributes = content["shots"][0]["actors"][0]["parts"][1]["attributes"]
    attributes[0]["evidenceIds"] = [
        request.evidence[0].evidence_id,
        request.evidence[2].evidence_id,
    ]
    attributes[1]["evidenceIds"] = [request.evidence[1].evidence_id]
    # The derived time hulls intersect, but no frame supports both properties.
    assert match_actor_details(parse(request, content), coat_query()).status == MatchStatus.PARTIAL


def test_uncertain_class_and_missing_property_never_become_positive(tmp_path):
    request, _ = parts_fixture(tmp_path)
    detail = parse(request, visible_parts(request))
    query = QueryConstraint((AttributeConstraint(AttributeKind.HELD_CLASS, "weapon", "held"),))
    assert match_actor_details(detail, query).status != MatchStatus.FULL
    unknown = {"shots": [], "notes": ["证据不足，待核对。"]}
    assert (
        match_actor_details(parse(request, unknown), coat_query()).status == MatchStatus.UNVERIFIED
    )
    assert parse(request, unknown).unassigned_evidence_ids == tuple(
        item.evidence_id for item in request.evidence
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_group",
        "wrong_group",
        "group_type",
        "duplicate_part",
        "empty_part",
        "flat_actor",
        "nested_part_id",
        "model_clock",
        "foreign",
        "cross_shot",
        "duplicate_ref",
        "reverse_ref",
        "unknown_kind",
        "unknown_value",
        "unknown_status",
        "actor_environment",
        "part_field",
        "actor_field",
        "shot_field",
        "top_field",
        "parts_limit",
        "actor_attributes_limit",
        "shot_limit",
        "actor_limit",
        "notes_limit",
        "description_limit",
        "notes_length",
        "environment_limit",
    ],
)
def test_untrusted_or_unbounded_nested_parts_are_rejected(tmp_path, mutation):
    request, paths = parts_fixture(tmp_path)
    content = visible_parts(request)
    shot = content["shots"][0]
    actor = shot["actors"][0]
    part = actor["parts"][1]
    attr = part["attributes"][0]
    if mutation == "unknown_group":
        part["partGroup"] = "body"
    elif mutation == "wrong_group":
        part["partGroup"] = "held_item"
    elif mutation == "group_type":
        part["partGroup"] = ["clothing"]
    elif mutation == "duplicate_part":
        actor["parts"].append(deepcopy(part))
    elif mutation == "empty_part":
        part["attributes"] = []
    elif mutation == "flat_actor":
        actor["attributes"] = actor.pop("parts")
    elif mutation == "nested_part_id":
        attr["partId"] = "borrowed"
    elif mutation == "model_clock":
        attr["startUs"] = 0
    elif mutation == "foreign":
        attr["evidenceIds"] = ["other:media:image:000000"]
    elif mutation == "cross_shot":
        shot["evidenceIds"] = shot["evidenceIds"][1:]
    elif mutation == "duplicate_ref":
        attr["evidenceIds"] *= 2
    elif mutation == "reverse_ref":
        attr["evidenceIds"] = list(reversed(shot["evidenceIds"]))
    elif mutation == "unknown_kind":
        attr["kind"] = "hat_color"
    elif mutation == "unknown_value":
        attr["value"] = "cape"
    elif mutation == "unknown_status":
        attr["status"] = "confirmed"
    elif mutation == "actor_environment":
        part["partGroup"] = "environment"
        attr.update(kind="environment", value="indoors")
    elif mutation == "part_field":
        part["actorId"] = "another-actor"
    elif mutation == "actor_field":
        actor["shotId"] = "other-shot"
    elif mutation == "shot_field":
        shot["durationUs"] = 1
    elif mutation == "top_field":
        content["accepted"] = True
    elif mutation == "parts_limit":
        actor["parts"] = [dict(part, partId=f"part-{index}") for index in range(17)]
    elif mutation == "actor_attributes_limit":
        actor["parts"] = [
            dict(part, partId=f"part-{index}", attributes=part["attributes"][:1])
            for index in range(16)
        ]
        actor["parts"][-1]["attributes"] = part["attributes"]
    elif mutation == "shot_limit":
        content["shots"] *= 10
    elif mutation == "actor_limit":
        shot["actors"] *= 9
    elif mutation == "notes_limit":
        content["notes"] *= 17
    elif mutation == "description_limit":
        actor["description"] = "x" * 501
    elif mutation == "notes_length":
        content["notes"] = ["x" * 501]
    else:
        shot["environment"] = [
            {
                "partId": "ground",
                **attribute("environment", "sandy_ground", request.evidence[0].evidence_id),
            }
        ] * 17
    result, transport = execute(request, paths, response(content))
    assert result.status == ProviderStatus.FAILED and result.output is None
    assert result.error.code == "provider.schema" and len(transport.payloads) == 1
    assert result.metadata.usage.input_tokens == 100 and result.metadata.usage.cost_cny is not None


@pytest.mark.parametrize("support", ["single", "same_image", "different_images"])
def test_action_still_requires_two_actual_distinct_frames(tmp_path, support):
    request, _ = parts_fixture(tmp_path)
    content = visible_parts(request)
    ids = [item.evidence_id for item in request.evidence]
    part = content["shots"][0]["actors"][0]["parts"][0]
    part["partGroup"] = "action"
    part["attributes"] = [{**attribute("action", "jump", ids[0]), "evidenceIds": ids[:2]}]
    if support == "single":
        part["attributes"][0]["evidenceIds"] = ids[:1]
    if support == "different_images":
        request = replace(
            request,
            evidence=tuple(
                replace(item, image_sha256=str(index + 1) * 64)
                for index, item in enumerate(request.evidence)
            ),
        )
        detail = parse(request, content)
        attr = detail.shots[0].actors[0].attributes[0]
        assert (attr.source_range.start_us, attr.source_range.end_us) == (28_000_000, 28_500_001)
    else:
        with pytest.raises(ValueError):
            parse(request, content)


def test_v3_transport_retains_metadata_and_uses_new_identity(tmp_path):
    request, paths = parts_fixture(tmp_path)
    result, transport = execute(request, paths, response(visible_parts(request)))
    assert result.status == ProviderStatus.COMPLETED and result.output is not None
    assert match_actor_details(result.output, coat_query()).status == MatchStatus.FULL
    assert transport.payloads[0]["messages"][0]["content"] == PROMPT
    assert len(transport.payloads) == 1
    assert result.metadata.prompt_version == "actor-detail-refinement-v3"
    assert result.metadata.attempt == 1 and result.metadata.request_id == "refine-request-1"
    assert (
        result.metadata.actual_model == "deepseek-flash" and result.metadata.model_revision is None
    )
    assert result.metadata.usage.cost_status == CostStatus.ESTIMATED
    assert result.metadata.usage.cached_input_tokens == 10
    details = json.loads(result.metadata.execution_details)
    assert details["requestHash"] == request_hash(request)
    assert details["promptHash"] == provider_parts_identity().prompt_hash
    assert details["inputFrames"] == 3


def test_frozen_v2_prompt_hash_and_cache_identity_are_unchanged(tmp_path):
    request, paths = prepared_fixture(tmp_path)
    old_identity = provider_refinement_identity()
    assert old_identity.prompt_version == "actor-detail-refinement-v2"
    assert (
        old_identity.prompt_hash
        == "a3675561f8ba78f6202feb4801cac3fdf9395f9c731df2721d3e472cdeb39dca"
    )
    assert old_identity.prompt_hash == hashlib.sha256(V2_PROMPT.encode()).hexdigest()
    assert provider_parts_identity().prompt_hash == hashlib.sha256(PROMPT.encode()).hexdigest()
    assert request_hash(request) != request_hash(
        replace(request, identity=provider_parts_identity())
    )
    old_payload = DeepSeekDetailRefinementProvider(Transport(None), paths)._payload(request)
    assert old_payload["messages"][0]["content"] == V2_PROMPT
    with pytest.raises(ValueError):
        parse_parts_detail(json.dumps(visible_parts(request)), request)
    result, transport = execute(request, paths, response(visible_parts(request)))
    assert result.status == ProviderStatus.FAILED and result.error.code == "provider.input"
    assert result.metadata.attempt == 0 and not transport.payloads


@pytest.mark.parametrize(
    "reply",
    [HttpResponse(429, b""), HttpResponse(503, b""), TransportError("provider.network", True)],
)
def test_retryable_failure_stays_single_send_and_cost_unknown(tmp_path, reply):
    request, paths = parts_fixture(tmp_path)
    result, transport = execute(request, paths, reply)
    assert result.status == ProviderStatus.FAILED and result.error.retryable
    assert len(transport.payloads) == 1 and result.metadata.usage.cost_cny is None


@pytest.mark.parametrize("model,usage", [("unknown-model", True), ("deepseek-flash", False)])
def test_unknown_usage_or_tariff_is_not_invented(tmp_path, model, usage):
    request, paths = parts_fixture(tmp_path)
    result, _ = execute(request, paths, response(visible_parts(request), model=model, usage=usage))
    assert result.status == ProviderStatus.COMPLETED
    assert result.metadata.usage.cost_cny is None
    assert result.metadata.usage.cost_status == CostStatus.UNVERIFIED


@pytest.mark.parametrize("cancel", [False, True])
def test_v3_timeout_and_cancel_close_transport_without_retry(tmp_path, cancel):
    request, paths = parts_fixture(tmp_path)
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
            DeepSeekDetailPartsProvider(Waiting(), paths).refine(request, context)
        )
        await entered.wait()
        if cancel:
            context.cancelled.set()
        return await task

    result = asyncio.run(run())
    assert result.status == (ProviderStatus.CANCELLED if cancel else ProviderStatus.FAILED)
    assert result.error.code == ("provider.cancelled" if cancel else "provider.timeout")
    assert closed == [True] and result.metadata.usage.cost_cny is None


@pytest.mark.parametrize(
    "content", ['{"shots":[],"shots":[],"notes":[]}', '{"shots":[],"notes":[NaN]}']
)
def test_duplicate_json_keys_and_nonfinite_values_are_rejected(tmp_path, content):
    request, _ = parts_fixture(tmp_path)
    with pytest.raises(_SchemaError):
        parse_parts_detail(content, request)


def test_parser_response_bytes_are_bounded(tmp_path):
    request, _ = parts_fixture(tmp_path)
    with pytest.raises(ValueError):
        parse_parts_detail(" " * (MAX_RESPONSE_BYTES + 1), request)


def registered_timeline(request, paths):
    stored = timeline()
    registered = {
        item.evidence_id: (item.image_sha256, paths[item.evidence_id]) for item in request.evidence
    }
    return replace(
        stored,
        evidence=tuple(
            replace(
                item,
                sha256=registered[item.evidence_id][0],
                artifact_path=registered[item.evidence_id][1],
            )
            if item.evidence_id in registered
            else item
            for item in stored.evidence
        ),
    )


def send(project, stored, provider):
    return asyncio.run(
        sidecar.send_refinement(
            project,
            stored,
            EVENT,
            provider,
            identity=provider_parts_identity(),
            budget_id="v3-fixture",
            ceiling=Decimal("10"),
            reservation=Decimal("2"),
        )
    )


def test_v3_sidecar_reuses_full_metadata_without_resending_or_rewriting(tmp_path):
    request, paths = parts_fixture(tmp_path)
    stored = registered_timeline(request, paths)
    project = tmp_path / "project"
    transport = Transport(response(visible_parts(request)))
    provider = DeepSeekDetailPartsProvider(transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004)
    result = send(project, stored, provider)
    assert not result.reused and result.detail is not None
    directory = sidecar.sidecar_directory(project, request.run_id, request_hash(request))
    before = {path: path.read_bytes() for path in project.rglob("*.json*")}
    reused = send(project, stored, provider)
    assert reused.reused and reused.detail == result.detail and len(transport.payloads) == 1
    assert {path: path.read_bytes() for path in project.rglob("*.json*")} == before
    published = json.loads((directory / "result.json").read_text())
    assert published["metadata"]["prompt_version"] == "actor-detail-refinement-v3"
    assert published["metadata"]["request_id"] == "refine-request-1"
    assert published["metadata"]["usage"]["cached_input_tokens"] == 10
    old_request = prepare_refinement(stored, EVENT, identity=provider_refinement_identity()).request
    assert old_request is not None
    assert not sidecar.sidecar_directory(
        project, request.run_id, request_hash(old_request)
    ).exists()


def test_v3_completed_attempt_recovers_after_publish_interruption_without_http(
    tmp_path, monkeypatch
):
    request, paths = parts_fixture(tmp_path)
    stored = registered_timeline(request, paths)
    project = tmp_path / "project"
    transport = Transport(response(visible_parts(request)))
    provider = DeepSeekDetailPartsProvider(transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004)
    original = sidecar._publish

    def interrupted(*args, **kwargs):
        raise OSError("fixture power loss")

    monkeypatch.setattr(sidecar, "_publish", interrupted)
    with pytest.raises(OSError):
        send(project, stored, provider)
    directory = sidecar.sidecar_directory(project, request.run_id, request_hash(request))
    attempt = (directory / "attempts/1-result.json").read_bytes()
    ledger_path = project / "detail-refinement-budgets/v3-fixture/ledger.jsonl"
    ledger = ledger_path.read_bytes()
    assert not (directory / "result.json").exists()
    monkeypatch.setattr(sidecar, "_publish", original)
    recovered = send(project, stored, provider)
    assert recovered.reused and recovered.detail is not None and len(transport.payloads) == 1
    assert match_actor_details(recovered.detail, coat_query()).status == MatchStatus.FULL
    assert (directory / "attempts/1-result.json").read_bytes() == attempt
    assert ledger_path.read_bytes() == ledger


def test_v3_unknown_cost_reservation_survives_failure_and_other_budget_directory(tmp_path):
    request, paths = parts_fixture(tmp_path)
    stored = registered_timeline(request, paths)
    project = tmp_path / "project"
    transport = Transport(TransportError("provider.network", True))
    provider = DeepSeekDetailPartsProvider(transport, paths)
    failed = send(project, stored, provider)
    assert failed.detail is None and len(transport.payloads) == 1
    other = prepare_refinement(stored, OTHER, identity=provider_parts_identity()).request
    assert other is not None
    with pytest.raises(AppError) as caught:
        sidecar.begin_attempt(
            project,
            other,
            budget_id="different-directory",
            ceiling=Decimal("3"),
            reservation=Decimal("2"),
            retry=False,
        )
    assert caught.value.code == "budget.exhausted"
    assert len(transport.payloads) == 1
    rows = [
        json.loads(line)
        for line in (project / "detail-refinement-budgets/v3-fixture/ledger.jsonl")
        .read_text()
        .splitlines()
    ]
    assert all(row["costCny"] is None and row["reservationCny"] == "2" for row in rows)
