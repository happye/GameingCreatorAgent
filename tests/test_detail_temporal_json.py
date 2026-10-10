"""JSON-mode compatibility and frozen-version isolation, without real model calls."""

import asyncio
import json
from dataclasses import replace

import pytest
from test_detail_provider import Transport, response
from test_detail_temporal_provider import temporal_fixture, temporal_model

from gamingcreator.application.detail_refinement import canonical_request_json, request_hash
from gamingcreator.application.detail_refinement_budget import detail_matches_request
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext, CostStatus, ProviderStatus
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    DeepSeekDetailTemporalProvider,
    parse_temporal_detail,
)
from gamingcreator.infrastructure.deepseek_detail_temporal_json import (
    PROMPT,
    DeepSeekDetailTemporalJsonProvider,
    parse_temporal_json_detail,
    provider_temporal_json_identity,
)
from gamingcreator.infrastructure.http_transport import HttpResponse


def test_explicit_json_changes_only_prompt_and_request_identity_not_registered_inputs(tmp_path):
    old, paths = temporal_fixture(tmp_path)
    old_canonical = canonical_request_json(old)
    old_payload = DeepSeekDetailTemporalProvider(Transport(HttpResponse(400, b"")), paths)._payload(
        old
    )
    current = replace(old, identity=provider_temporal_json_identity())
    payload = DeepSeekDetailTemporalJsonProvider(Transport(HttpResponse(400, b"")), paths)._payload(
        current
    )
    assert (
        old.identity.prompt_hash
        == "eb37399fca06be1b7cd2fa93879965c1f83c7731b0031b2835f6ee345dad6a02"
    )
    assert current.identity.prompt_hash != old.identity.prompt_hash
    assert request_hash(current) != request_hash(old)
    assert payload["messages"][0]["content"] == PROMPT
    assert "one valid JSON object" in PROMPT
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 4096
    assert payload["messages"][1] == old_payload["messages"][1]
    assert {key: value for key, value in payload.items() if key != "messages"} == {
        key: value for key, value in old_payload.items() if key != "messages"
    }
    assert canonical_request_json(old) == old_canonical


def test_v5_single_send_keeps_strict_entity_projection_and_accounting(tmp_path):
    old, paths = temporal_fixture(tmp_path)
    request = replace(old, identity=provider_temporal_json_identity())
    transport = Transport(response(temporal_model(request)))
    result = asyncio.run(
        DeepSeekDetailTemporalJsonProvider(
            transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004
        ).refine(request, CancellationContext(request.run_id, 5))
    )
    assert result.status == ProviderStatus.COMPLETED and result.output is not None
    assert result.metadata.prompt_version == "actor-detail-refinement-v5"
    assert result.metadata.schema_version == "actor-detail-refinement-schema-v2"
    assert result.metadata.attempt == 1 and len(transport.payloads) == 1
    assert result.metadata.usage.cost_status == CostStatus.ESTIMATED
    assert detail_matches_request(result.output, request)
    assert len(result.output.shots[0].actors) == 1
    assert result.output.temporal_scene is not None
    assert len(result.output.temporal_scene.entities) == 2


@pytest.mark.parametrize("damage", ["object_as_actor", "occluded_attribute", "unknown_boundary"])
def test_json_instruction_does_not_relax_invalid_entity_evidence(tmp_path, damage):
    old, paths = temporal_fixture(tmp_path)
    request = replace(old, identity=provider_temporal_json_identity())
    model = temporal_model(request)
    if damage == "object_as_actor":
        model["entities"][1]["classification"]["kind"] = "actor"
    elif damage == "occluded_attribute":
        model["entities"][0]["parts"][0]["attributes"][0]["evidenceIds"] = [
            request.evidence[2].evidence_id
        ]
    else:
        model["transitions"][0].update(state="unknown", basis="insufficient_evidence")
    transport = Transport(response(model))
    result = asyncio.run(
        DeepSeekDetailTemporalJsonProvider(
            transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004
        ).refine(request, CancellationContext(request.run_id, 5))
    )
    assert result.status == ProviderStatus.FAILED and result.output is None
    assert result.error is not None and result.error.code == "provider.schema"
    assert len(transport.payloads) == 1 and result.metadata.usage.cost_cny is not None


@pytest.mark.parametrize("direction", ["v4_to_v5", "v5_to_v4"])
def test_parse_cannot_relabel_one_prompt_version_as_another(tmp_path, direction):
    old, _ = temporal_fixture(tmp_path)
    current = replace(old, identity=provider_temporal_json_identity())
    request, parser = (
        (old, parse_temporal_json_detail)
        if direction == "v4_to_v5"
        else (current, parse_temporal_detail)
    )
    with pytest.raises(ValueError, match="Unsupported temporal refinement identity"):
        parser(json.dumps(temporal_model(request)), request)


def test_v5_http_failure_keeps_unknown_cost_without_retry(tmp_path):
    old, paths = temporal_fixture(tmp_path)
    request = replace(old, identity=provider_temporal_json_identity())
    transport = Transport(HttpResponse(400, b""))
    result = asyncio.run(
        DeepSeekDetailTemporalJsonProvider(
            transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004
        ).refine(request, CancellationContext(request.run_id, 5))
    )
    assert result.status == ProviderStatus.FAILED and result.output is None
    assert result.error is not None and result.error.code == "provider.http"
    assert result.metadata.attempt == 1 and len(transport.payloads) == 1
    assert result.metadata.usage.cost_cny is None
