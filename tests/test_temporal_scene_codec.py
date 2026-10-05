"""Exact bounded temporal JSON survives persistence without accepting model clocks."""

import json
from copy import deepcopy

import pytest
from test_actor_detail_matching import evidence
from test_temporal_entities import model_fixture

from gamingcreator.application.temporal_entity_projection import project_temporal_scene
from gamingcreator.application.temporal_scene_codec import (
    MAX_SCENE_BYTES,
    scene_from_model,
    scene_from_payload,
    scene_payload,
)


def test_complete_persistence_round_trip_retains_every_classification_and_source_clock():
    registry = evidence()
    scene = scene_from_model(model_fixture(registry), registry)
    payload = scene_payload(scene)
    assert payload["schemaVersion"] == "temporal-scene-v1"
    assert payload["evidence"][0] == {
        "evidenceId": registry[0].evidence_id,
        "imageSha256": registry[0].image_sha256,
        "sourceUs": registry[0].source_time.time_us,
        "durationUs": registry[0].source_time.duration_us,
    }
    restored = scene_from_payload(json.loads(json.dumps(payload)))
    assert restored == scene
    assert project_temporal_scene(restored) == project_temporal_scene(scene)
    assert scene_payload(restored) == payload
    model = {
        key: value for key, value in payload.items() if key not in {"schemaVersion", "evidence"}
    }
    assert scene_from_model(model, registry) == scene


@pytest.mark.parametrize(
    "path",
    [
        "top",
        "transition",
        "entity",
        "classification",
        "observation",
        "part",
        "attribute",
        "owner",
        "environment",
    ],
)
def test_model_rejects_extra_fields_at_every_layer_including_clocks_and_identity(path):
    registry = evidence()
    payload = model_fixture(registry)
    entity = payload["entities"][0]
    target = {
        "top": payload,
        "transition": payload["transitions"][0],
        "entity": entity,
        "classification": entity["classification"],
        "observation": entity["observations"][0],
        "part": entity["parts"][0],
        "attribute": entity["parts"][0]["attributes"][0],
        "owner": payload["owners"][0],
    }
    if path == "environment":
        value = {
            "partId": "water",
            "kind": "environment",
            "value": "water",
            "status": "observed",
            "evidenceIds": [registry[0].evidence_id],
        }
        payload["environment"] = [value]
    else:
        value = target[path]
    value["sourceUs"] = 0
    with pytest.raises(ValueError):
        scene_from_model(payload, registry)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "evidence_extra",
        "missing_field",
        "float_time",
        "bool_time",
        "foreign_ref",
        "changed_time_order",
        "empty_evidence",
        "tuple_collection",
        "nonfinite",
        "bytes_limit",
    ],
)
def test_persistence_refuses_unknown_versions_bad_clocks_types_and_bounds(mutation):
    payload = deepcopy(scene_payload(scene_from_model(model_fixture(evidence()), evidence())))
    if mutation == "version":
        payload["schemaVersion"] = "temporal-scene-v99"
    elif mutation == "evidence_extra":
        payload["evidence"][0]["baseRunId"] = "other"
    elif mutation == "missing_field":
        del payload["owners"]
    elif mutation in {"float_time", "bool_time"}:
        payload["evidence"][0]["sourceUs"] = 0.0 if mutation == "float_time" else False
    elif mutation == "foreign_ref":
        payload["entities"][0]["classification"]["evidenceIds"] = ["missing:media:image:000000"]
    elif mutation == "changed_time_order":
        payload["evidence"][1]["sourceUs"] = payload["evidence"][0]["sourceUs"]
    elif mutation == "empty_evidence":
        payload["evidence"] = []
    elif mutation == "tuple_collection":
        payload["entities"] = tuple(payload["entities"])
    elif mutation == "nonfinite":
        payload["evidence"][0]["sourceUs"] = float("nan")
    else:
        payload["notes"] = ["x" * MAX_SCENE_BYTES]
    with pytest.raises(ValueError):
        scene_from_payload(payload)


def test_model_cannot_supply_registered_frames_even_when_they_are_valid():
    registry = evidence()
    value = scene_payload(scene_from_model(model_fixture(registry), registry))
    with pytest.raises(ValueError):
        scene_from_model(value, registry)


def test_persistence_frame_rehash_is_not_silently_hidden_by_projection():
    registry = evidence()
    scene = scene_from_model(model_fixture(registry), registry)
    payload = scene_payload(scene)
    payload["evidence"][0]["imageSha256"] = "b" * 64
    restored = scene_from_payload(payload)
    assert restored.evidence != scene.evidence
    # The enclosing CandidateDetail/request codec must compare registered evidence;
    # a pure scene decoder has no external truth and must preserve what it received.
    assert scene_payload(restored)["evidence"][0]["imageSha256"] == "b" * 64
