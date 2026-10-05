"""Temporal contracts reject unsupported identities; fixtures are not visual quality labels."""

from dataclasses import FrozenInstanceError, replace

import pytest
from test_actor_detail_matching import evidence

from gamingcreator.application.temporal_scene_codec import scene_from_model
from gamingcreator.domain.temporal_entities import (
    EntityClassification,
    EntityKind,
    EntityObservation,
    TemporalScene,
    Visibility,
)


def model_fixture(registry):
    ids = [item.evidence_id for item in registry]

    def attribute(kind, value):
        return {"kind": kind, "value": value, "status": "observed", "evidenceIds": ids}

    def entity(entity_id, kind, basis, part_group, attributes):
        return {
            "entityId": entity_id,
            "description": "画面中的角色。" if kind == "actor" else "被角色拿着的前景物品。",
            "classification": {
                "kind": kind,
                "status": "observed",
                "basis": basis,
                "evidenceIds": ids[:1],
                "reason": "引用帧中可见相应结构。",
            },
            "observations": [
                {"evidenceId": frame, "visibility": "visible", "location": "画面中央。"}
                for frame in ids
            ],
            "parts": [{"partId": "part", "partGroup": part_group, "attributes": attributes}],
        }

    return {
        "transitions": [
            {
                "beforeId": before,
                "afterId": after,
                "state": "continuous",
                "basis": "visual_continuity",
                "reason": "背景与主体位置连续，前景物体靠近镜头。",
            }
            for before, after in zip(ids, ids[1:], strict=False)
        ],
        "entities": [
            entity(
                "actor", "actor", "character_structure", "hair", [attribute("hair_color", "white")]
            ),
            entity(
                "object",
                "object",
                "carried_object",
                "held_item",
                [attribute("held_shape", "blue_flat_object")],
            ),
        ],
        "owners": [
            {
                "objectId": "object",
                "actorId": "actor",
                "status": "observed",
                "evidenceIds": ids[:2],
                "reason": "角色的手与物体保持接触。",
            }
        ],
        "environment": [],
        "notes": ["这是开发fixture，不代表真实模型观察正确。"],
    }


def test_contracts_are_immutable_and_partial_occlusion_still_supports_visibility():
    registry = evidence()
    payload = model_fixture(registry)
    payload["entities"][0]["observations"][1]["visibility"] = "partially_occluded"
    scene = scene_from_model(payload, registry)
    assert scene.evidence == registry
    assert scene.entities[0].observations[1].visibility == Visibility.PARTIALLY_OCCLUDED
    with pytest.raises(FrozenInstanceError):
        scene.entities = ()
    with pytest.raises(ValueError):
        replace(scene, entities=list(scene.entities))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_transition",
        "reverse_transition",
        "cut_wrong_basis",
        "static_cut",
        "skipped_observation",
        "reverse_observation",
        "repeated_observation",
        "foreign_observation",
        "cross_cut_entity",
        "cross_unknown_entity",
        "bad_actor_basis",
        "single_agency",
        "same_image_agency",
        "hidden_classification",
        "hidden_attribute",
        "unknown_visibility_attribute",
        "object_hair",
        "actor_held",
        "unknown_parts",
        "observed_unknown",
        "owner_hidden",
        "owner_foreign_frame",
        "owner_unknown_entity",
        "owner_wrong_kind",
        "duplicate_entity",
        "duplicate_part",
        "too_many_actors",
        "too_many_entities",
        "too_many_attributes",
        "too_many_owners",
        "too_many_notes",
        "cross_environment",
        "foreign_namespace",
        "wrong_environment_kind",
    ],
)
def test_invalid_identity_visibility_basis_or_bounds_are_rejected(mutation):
    registry = evidence()
    payload = model_fixture(registry)
    entity = payload["entities"][0]
    other = payload["entities"][1]
    refs = [item.evidence_id for item in registry]
    if mutation == "missing_transition":
        payload["transitions"].pop()
    elif mutation == "reverse_transition":
        payload["transitions"].reverse()
    elif mutation == "cut_wrong_basis":
        payload["transitions"][0]["state"] = "cut"
    elif mutation == "static_cut":
        registry = tuple(replace(item, image_sha256="a" * 64) for item in registry)
        payload["transitions"][0].update(state="cut", basis="scene_change")
    elif mutation == "skipped_observation":
        entity["observations"].pop(1)
    elif mutation == "reverse_observation":
        entity["observations"].reverse()
    elif mutation == "repeated_observation":
        entity["observations"].append(entity["observations"][0])
    elif mutation == "foreign_observation":
        entity["observations"][0]["evidenceId"] = "other:media:image:000000"
    elif mutation in {"cross_cut_entity", "cross_unknown_entity"}:
        payload["transitions"][0].update(
            state="cut" if mutation == "cross_cut_entity" else "unknown",
            basis="scene_change" if mutation == "cross_cut_entity" else "insufficient_evidence",
        )
    elif mutation == "bad_actor_basis":
        entity["classification"]["basis"] = "carried_object"
    elif mutation in {"single_agency", "same_image_agency"}:
        entity["classification"]["basis"] = "independent_agency"
        if mutation == "same_image_agency":
            entity["classification"]["evidenceIds"] = refs[:2]
            registry = tuple(replace(item, image_sha256="a" * 64) for item in registry)
    elif mutation == "hidden_classification":
        entity["observations"][0]["visibility"] = "occluded"
    elif mutation in {"hidden_attribute", "unknown_visibility_attribute"}:
        entity["observations"][1]["visibility"] = (
            "occluded" if mutation == "hidden_attribute" else "unknown"
        )
    elif mutation == "object_hair":
        other["parts"] = entity["parts"]
    elif mutation == "actor_held":
        entity["parts"] = other["parts"]
    elif mutation == "unknown_parts":
        entity["classification"].update(
            kind="unknown", status="uncertain", basis="insufficient_evidence"
        )
    elif mutation == "observed_unknown":
        entity["classification"].update(kind="unknown", basis="insufficient_evidence")
        entity["parts"] = []
    elif mutation == "owner_hidden":
        other["observations"][1]["visibility"] = "occluded"
        other["parts"][0]["attributes"][0]["evidenceIds"] = [refs[0], refs[2]]
    elif mutation == "owner_foreign_frame":
        payload["owners"][0]["evidenceIds"] = ["other:media:image:000000"]
    elif mutation == "owner_unknown_entity":
        payload["owners"][0]["actorId"] = "missing"
    elif mutation == "owner_wrong_kind":
        payload["owners"][0].update(actorId="object", objectId="actor")
    elif mutation == "duplicate_entity":
        payload["entities"].append(entity)
    elif mutation == "duplicate_part":
        entity["parts"].append(entity["parts"][0])
    elif mutation in {"too_many_actors", "too_many_entities"}:
        payload["entities"] = [
            dict(entity, entityId=f"actor-{index}")
            for index in range(9 if mutation == "too_many_actors" else 73)
        ]
    elif mutation == "too_many_attributes":
        entity["parts"][0]["attributes"] *= 17
    elif mutation == "too_many_owners":
        payload["owners"] *= 73
    elif mutation == "too_many_notes":
        payload["notes"] *= 17
    elif mutation == "cross_environment":
        payload["entities"] = []
        payload["owners"] = []
        payload["transitions"][0].update(state="unknown", basis="insufficient_evidence")
        payload["environment"] = [
            {
                "partId": "ground",
                "kind": "environment",
                "value": "water",
                "status": "observed",
                "evidenceIds": refs,
            }
        ]
    elif mutation == "foreign_namespace":
        registry = (
            registry[0],
            replace(registry[1], evidence_id="other:media:image:000001"),
            registry[2],
        )
    else:
        payload["environment"] = [
            {
                "partId": "hair",
                "kind": "hair_color",
                "value": "white",
                "status": "observed",
                "evidenceIds": refs,
            }
        ]
    with pytest.raises(ValueError):
        scene_from_model(payload, registry)


def test_independent_agency_requires_continuous_distinct_images_and_accepts_nonhuman_actor():
    registry = evidence()
    payload = model_fixture(registry)
    entity = payload["entities"][0]
    entity["description"] = "独立行动的小机器人。"
    entity["classification"].update(
        basis="independent_agency", evidenceIds=[item.evidence_id for item in registry[:2]]
    )
    scene = scene_from_model(payload, registry)
    assert scene.entities[0].classification.kind == EntityKind.ACTOR


def test_forged_attribute_clock_and_untagged_enum_are_rejected():
    scene = scene_from_model(model_fixture(evidence()), evidence())
    entity = scene.entities[0]
    part = entity.parts[0]
    attribute = part.attributes[0]
    bad_attribute = replace(
        attribute,
        source_range=replace(attribute.source_range, end_us=attribute.source_range.end_us + 1),
    )
    bad_entity = replace(entity, parts=(replace(part, attributes=(bad_attribute,)),))
    with pytest.raises(ValueError):
        replace(scene, entities=(bad_entity, *scene.entities[1:]))
    with pytest.raises(ValueError):
        replace(entity.classification, kind="actor")
    with pytest.raises(ValueError):
        EntityObservation(evidence()[0].evidence_id, "visible", "中央。")


def test_unknown_entity_can_retain_full_occlusion_without_invented_classification_evidence():
    registry = evidence()
    payload = model_fixture(registry)
    entity = payload["entities"][0]
    entity["classification"].update(
        kind="unknown", status="uncertain", basis="insufficient_evidence", evidenceIds=[]
    )
    entity["parts"] = []
    for observation in entity["observations"]:
        observation["visibility"] = "occluded"
    payload["entities"] = [entity]
    payload["owners"] = []
    scene = scene_from_model(payload, registry)
    assert scene.entities[0].classification.evidence_ids == ()
    assert all(item.visibility == Visibility.OCCLUDED for item in scene.entities[0].observations)


def test_top_level_scene_requires_frozen_tuples_and_supported_version():
    scene = scene_from_model(model_fixture(evidence()), evidence())
    with pytest.raises(ValueError):
        replace(scene, schema_version="temporal-scene-v2")
    with pytest.raises(ValueError):
        TemporalScene(
            list(scene.evidence),
            scene.transitions,
            scene.entities,
            scene.owners,
            scene.environment,
            scene.notes,
        )
    with pytest.raises(ValueError):
        EntityClassification(
            "actor",
            scene.entities[0].classification.status,
            scene.entities[0].classification.basis,
            (),
            "理由。",
        )


def test_identical_images_cannot_establish_cut_without_any_entity_validation():
    registry = tuple(replace(item, image_sha256="a" * 64) for item in evidence())
    payload = model_fixture(registry)
    payload["entities"] = []
    payload["owners"] = []
    payload["transitions"][0].update(state="cut", basis="scene_change")
    with pytest.raises(ValueError, match="Identical images"):
        scene_from_model(payload, registry)
    payload["transitions"][0].update(state="unknown", basis="insufficient_evidence")
    assert scene_from_model(payload, registry).transitions[0].state.value == "unknown"


def test_single_frame_character_structure_is_allowed_but_no_transition_is_invented():
    registry = evidence(frames=1)
    payload = model_fixture(registry)
    scene = scene_from_model(payload, registry)
    assert scene.transitions == ()
    assert len(scene.entities[0].classification.evidence_ids) == 1
