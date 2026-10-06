"""Entity/occlusion fixtures verify contracts, not real model recognition or human quality."""

import asyncio
import hashlib
import json
from dataclasses import replace
from decimal import Decimal

import pytest
from test_detail_parts import registered_timeline
from test_detail_provider import Transport, prepared_fixture, response, visible_detail

from gamingcreator.application.actor_detail_matching import match_actor_details
from gamingcreator.application.detail_refinement import request_hash
from gamingcreator.application.detail_refinement_budget import (
    canonical_detail_json,
    detail_from_canonical,
    detail_matches_request,
    payload_hash,
)
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext, CostStatus, ProviderStatus
from gamingcreator.domain.actor_details import (
    DETAIL_SCHEMA_VERSION,
    AttributeConstraint,
    AttributeKind,
    MatchStatus,
    QueryConstraint,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar
from gamingcreator.infrastructure.deepseek_detail_parts import provider_parts_identity
from gamingcreator.infrastructure.deepseek_detail_refinement import (
    DeepSeekDetailRefinementProvider,
    parse_detail,
    provider_refinement_identity,
)
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    PROMPT,
    DeepSeekDetailTemporalProvider,
    parse_temporal_detail,
    provider_temporal_identity,
    temporal_refinement_settings,
)
from gamingcreator.infrastructure.http_transport import TransportError


def temporal_fixture(tmp_path):
    request, paths = prepared_fixture(tmp_path)
    return replace(
        request, identity=provider_temporal_identity(), settings=temporal_refinement_settings()
    ), paths


def attr(kind, value, ids, *, status="observed"):
    return {"kind": kind, "value": value, "status": status, "evidenceIds": list(ids)}


def entity(entity_id, kind, ids, *, parts=None):
    return {
        "entityId": entity_id,
        "description": "角色" if kind == "actor" else "抵近镜头的物品",
        "classification": {
            "kind": kind,
            "status": "observed",
            "basis": "character_structure" if kind == "actor" else "rigid_object",
            "evidenceIds": [ids[0]],
            "reason": "可见角色身体结构" if kind == "actor" else "可见连续物体结构",
        },
        "observations": [
            {"evidenceId": frame, "visibility": "visible", "location": "画面左侧"} for frame in ids
        ],
        "parts": parts or [],
    }


def temporal_model(request, *, color="white", all_hair_frames=False):
    ids = [item.evidence_id for item in request.evidence]
    actor = entity(
        "actor-1",
        "actor",
        ids,
        parts=[
            {
                "partId": "hair",
                "partGroup": "hair",
                "attributes": [attr("hair_color", color, ids if all_hair_frames else ids[:1])],
            }
        ],
    )
    if len(ids) >= 3:
        actor["observations"][1]["visibility"] = "partially_occluded"
        actor["observations"][2]["visibility"] = "occluded"
    item = entity(
        "object-1",
        "object",
        ids,
        parts=[
            {
                "partId": "item",
                "partGroup": "held_item",
                "attributes": [attr("held_shape", "blue_flat_object", ids)],
            }
        ],
    )
    return {
        "transitions": [
            {
                "beforeId": before,
                "afterId": after,
                "state": "continuous",
                "basis": "visual_continuity",
                "reason": "背景连续，前景物品靠近并遮挡角色",
            }
            for before, after in zip(ids, ids[1:], strict=False)
        ],
        "entities": [actor, item],
        "owners": [
            {
                "objectId": "object-1",
                "actorId": "actor-1",
                "status": "observed",
                "evidenceIds": ids[:2],
                "reason": "可见角色持握物品",
            }
        ],
        "environment": [],
        "notes": [],
    }


def parse(request, model):
    return parse_temporal_detail(json.dumps(model, ensure_ascii=False), request)


def query(*conditions):
    return QueryConstraint(
        tuple(AttributeConstraint(kind, value, group) for kind, value, group in conditions)
    )


def send(project, stored, provider):
    return asyncio.run(
        sidecar.send_refinement(
            project,
            stored,
            stored.events[0].event_id,
            provider,
            identity=provider_temporal_identity(),
            settings=temporal_refinement_settings(),
            budget_id="v4-fixture",
            ceiling=Decimal("10"),
            reservation=Decimal("2"),
        )
    )


def test_occluding_object_remains_separate_and_ownership_support_is_intersected(tmp_path):
    request, _ = temporal_fixture(tmp_path)
    detail = parse(request, temporal_model(request))
    assert detail.temporal_scene is not None and detail.schema_version == "actor-details-v2"
    assert len(detail.shots) == 1 and len(detail.shots[0].actors) == 1
    assert len(detail.temporal_scene.entities) == 2
    actor = detail.shots[0].actors[0]
    held = next(item for item in actor.attributes if item.kind == AttributeKind.HELD_SHAPE)
    assert held.evidence_ids == tuple(item.evidence_id for item in request.evidence[:2])
    assert request.evidence[2].evidence_id not in held.evidence_ids
    match = match_actor_details(
        detail,
        query(
            (AttributeKind.HAIR_COLOR, "white", "hair"),
            (AttributeKind.HELD_SHAPE, "blue_flat_object", "item"),
        ),
    )
    assert match.status == MatchStatus.FULL
    assert match.matches[0].shared_evidence_ids == (request.evidence[0].evidence_id,)


def test_uncertain_owner_does_not_supply_observed_held_attribute(tmp_path):
    request, _ = temporal_fixture(tmp_path)
    model = temporal_model(request)
    model["owners"][0]["status"] = "uncertain"
    detail = parse(request, model)
    match = match_actor_details(
        detail,
        query(
            (AttributeKind.HAIR_COLOR, "white", "hair"),
            (AttributeKind.HELD_SHAPE, "blue_flat_object", "item"),
        ),
    )
    assert match.status == MatchStatus.PARTIAL
    assert "unresolved_entity" in match.notes


def test_unknown_entity_prevents_false_global_no_match(tmp_path):
    request, _ = temporal_fixture(tmp_path)
    model = temporal_model(request, color="black", all_hair_frames=True)
    for item in model["entities"][0]["observations"]:
        item["visibility"] = "visible"
    known = parse(request, model)
    hair_query = query((AttributeKind.HAIR_COLOR, "white", "hair"))
    assert match_actor_details(known, hair_query).status == MatchStatus.NO_MATCH
    unknown = entity("unresolved", "object", [item.evidence_id for item in request.evidence])
    unknown["classification"] = {
        "kind": "unknown",
        "status": "uncertain",
        "basis": "insufficient_evidence",
        "evidenceIds": [],
        "reason": "遮挡区域实体身份不足",
    }
    model["entities"].append(unknown)
    match = match_actor_details(parse(request, model), hair_query)
    assert match.status == MatchStatus.UNVERIFIED and "unresolved_entity" in match.notes


def test_projection_cannot_be_forged_independently_of_saved_scene(tmp_path):
    request, _ = temporal_fixture(tmp_path)
    detail = parse(request, temporal_model(request))
    altered_actor = replace(detail.shots[0].actors[0], description="伪造投影，场景中没有此描述")
    altered = replace(detail, shots=(replace(detail.shots[0], actors=(altered_actor,)),))
    with pytest.raises(ValueError):
        canonical_detail_json(altered)
    with pytest.raises(ValueError):
        match_actor_details(altered, query((AttributeKind.HAIR_COLOR, "white", "hair")))
    assert not detail_matches_request(altered, request)
    saved = json.loads(canonical_detail_json(detail))
    saved["shots"][0]["actors"][0]["description"] = "改动合法字段也不能脱离scene"
    with pytest.raises(ValueError):
        detail_from_canonical(json.dumps(saved))


def test_full_temporal_evidence_round_trips_and_schema_cannot_be_downgraded(tmp_path):
    request, _ = temporal_fixture(tmp_path)
    detail = parse(request, temporal_model(request))
    saved = canonical_detail_json(detail)
    assert detail_from_canonical(saved) == detail and detail_matches_request(detail, request)
    assert payload_hash(detail) == hashlib.sha256(saved.encode()).hexdigest()
    assert "owners" in json.loads(saved)["temporalScene"]
    legacy = replace(detail, temporal_scene=None, schema_version=DETAIL_SCHEMA_VERSION)
    assert not detail_matches_request(legacy, request)
    assert not detail_matches_request(detail, replace(request, identity=provider_parts_identity()))
    wrong = json.loads(saved)
    wrong["schemaVersion"] = DETAIL_SCHEMA_VERSION
    with pytest.raises(ValueError):
        detail_from_canonical(json.dumps(wrong))


def test_historical_input_and_payload_stay_frozen(tmp_path):
    legacy_request, paths = prepared_fixture(tmp_path)
    legacy = parse_detail(json.dumps(visible_detail(legacy_request)), legacy_request)
    assert "temporalScene" not in json.loads(canonical_detail_json(legacy))
    assert legacy.schema_version == DETAIL_SCHEMA_VERSION and legacy.temporal_scene is None
    old_payload = DeepSeekDetailRefinementProvider(Transport(None), paths)._payload(legacy_request)
    assert json.loads(old_payload["messages"][1]["content"][0]["text"]) == {
        "evidenceId": legacy_request.evidence[0].evidence_id
    }
    assert (
        provider_refinement_identity().prompt_hash
        == "a3675561f8ba78f6202feb4801cac3fdf9395f9c731df2721d3e472cdeb39dca"
    )
    assert (
        provider_parts_identity().prompt_hash
        == "ce2edb889a4a9f5029c2591e06c210df030fc479d31efff20a4532b2e05f078a"
    )


def test_transport_supplies_actual_clocks_and_preserves_one_attempt_accounting(tmp_path):
    request, paths = temporal_fixture(tmp_path)
    transport = Transport(response(temporal_model(request)))
    provider = DeepSeekDetailTemporalProvider(
        transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    result = asyncio.run(provider.refine(request, CancellationContext(request.run_id, 5)))
    assert result.status == ProviderStatus.COMPLETED and result.output is not None
    assert result.metadata.prompt_version == "actor-detail-refinement-v4"
    assert result.metadata.schema_version == "actor-detail-refinement-schema-v2"
    assert (
        result.metadata.attempt == 1 and result.metadata.usage.cost_status == CostStatus.ESTIMATED
    )
    assert len(transport.payloads) == 1
    payload = transport.payloads[0]
    assert payload["max_tokens"] == 4096 and payload["messages"][0]["content"] == PROMPT
    blocks = payload["messages"][1]["content"]
    header = json.loads(blocks[0]["text"])
    assert header["candidateInterval"]["endUs"] == request.source_range.end_us
    texts = [json.loads(item["text"]) for item in blocks[1:] if item["type"] == "text"]
    assert [item["sourceUs"] for item in texts] == [
        item.source_time.time_us for item in request.evidence
    ]
    assert [item["frameIndex"] for item in texts] == list(range(len(request.evidence)))
    assert texts[0]["deltaFromPreviousUs"] is None
    assert (
        texts[1]["deltaFromPreviousUs"]
        == request.evidence[1].source_time.time_us - request.evidence[0].source_time.time_us
    )


@pytest.mark.parametrize(
    "bad_result", ["object_as_actor", "occluded_attribute", "unknown_boundary"]
)
def test_invalid_evidence_keeps_usage_in_schema_failure(tmp_path, bad_result):
    request, paths = temporal_fixture(tmp_path)
    model = temporal_model(request)
    if bad_result == "object_as_actor":
        model["entities"][1]["classification"]["kind"] = "actor"
    elif bad_result == "occluded_attribute":
        model["entities"][0]["parts"][0]["attributes"][0]["evidenceIds"] = [
            request.evidence[2].evidence_id
        ]
    else:
        model["transitions"][0].update(state="unknown", basis="insufficient_evidence")
    transport = Transport(response(model))
    provider = DeepSeekDetailTemporalProvider(
        transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    result = asyncio.run(provider.refine(request, CancellationContext(request.run_id, 5)))
    assert result.status == ProviderStatus.FAILED and result.output is None
    assert result.error.code == "provider.schema" and len(transport.payloads) == 1
    assert result.metadata.usage.cost_cny is not None and result.metadata.usage.input_tokens == 100


def test_missing_base_identity_rejects_before_send(tmp_path):
    request, paths = temporal_fixture(tmp_path)
    transport = Transport(response(temporal_model(request)))
    provider = DeepSeekDetailTemporalProvider(transport, paths)
    result = asyncio.run(
        provider.refine(
            replace(request, base_prompt_hash=None), CancellationContext(request.run_id, 5)
        )
    )
    assert result.status == ProviderStatus.FAILED and result.error.code == "provider.input"
    assert result.metadata.attempt == 0 and not transport.payloads


def test_temporal_sidecar_reuses_full_evidence_and_recovers_without_second_call(
    tmp_path, monkeypatch
):
    request, paths = temporal_fixture(tmp_path)
    stored = registered_timeline(request, paths)
    project = tmp_path / "project"
    transport = Transport(response(temporal_model(request)))
    provider = DeepSeekDetailTemporalProvider(
        transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    original = sidecar._publish

    def interrupted(*args, **kwargs):
        raise OSError("fixture lost publication")

    monkeypatch.setattr(sidecar, "_publish", interrupted)
    with pytest.raises(OSError):
        send(project, stored, provider)
    directory = sidecar.sidecar_directory(project, request.run_id, request_hash(request))
    attempt = (directory / "attempts/1-result.json").read_bytes()
    ledger_path = project / "detail-refinement-budgets/v4-fixture/ledger.jsonl"
    ledger = ledger_path.read_bytes()
    monkeypatch.setattr(sidecar, "_publish", original)
    recovered = send(project, stored, provider)
    assert recovered.reused and recovered.detail.temporal_scene is not None
    assert (
        detail_from_canonical(json.loads((directory / "result.json").read_text())["payloadJson"])
        == recovered.detail
    )
    assert (directory / "attempts/1-result.json").read_bytes() == attempt
    assert ledger_path.read_bytes() == ledger and len(transport.payloads) == 1


def test_temporal_network_failure_keeps_unknown_reservation_and_no_retry(tmp_path):
    request, paths = temporal_fixture(tmp_path)
    stored = registered_timeline(request, paths)
    project = tmp_path / "project"
    transport = Transport(TransportError("provider.network", True))
    provider = DeepSeekDetailTemporalProvider(transport, paths)
    failed = send(project, stored, provider)
    assert failed.detail is None and len(transport.payloads) == 1
    with pytest.raises(AppError) as caught:
        send(project, stored, provider)
    assert caught.value.code == "refinement.retry_required" and len(transport.payloads) == 1
    rows = [
        json.loads(line)
        for line in (project / "detail-refinement-budgets/v4-fixture/ledger.jsonl")
        .read_text()
        .splitlines()
    ]
    assert rows and all(row["costCny"] is None and row["reservationCny"] == "2" for row in rows)
