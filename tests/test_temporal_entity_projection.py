"""Ownership and classification safely control actor matching projection."""

from copy import deepcopy
from dataclasses import replace

import pytest
from test_actor_detail_matching import detail, evidence
from test_temporal_entities import model_fixture

from gamingcreator.application.actor_detail_matching import match_actor_details
from gamingcreator.application.temporal_entity_projection import project_temporal_scene
from gamingcreator.application.temporal_scene_codec import scene_from_model
from gamingcreator.domain.actor_details import (
    AttributeConstraint,
    AttributeKind,
    AttributeStatus,
    MatchStatus,
    QueryConstraint,
)


def compound_query():
    return QueryConstraint(
        (
            AttributeConstraint(AttributeKind.HAIR_COLOR, "white", "hair"),
            AttributeConstraint(AttributeKind.HELD_SHAPE, "blue_flat_object", "held"),
        )
    )


def test_object_is_not_an_actor_and_held_projection_uses_only_joint_support_frames():
    registry = evidence()
    scene = scene_from_model(model_fixture(registry), registry)
    projection = project_temporal_scene(scene)
    assert len(projection.shots) == 1 and len(projection.shots[0].actors) == 1
    actor = projection.shots[0].actors[0]
    assert actor.actor_id == "actor"
    held = next(item for item in actor.attributes if item.kind == AttributeKind.HELD_SHAPE)
    assert held.evidence_ids == tuple(item.evidence_id for item in registry[:2])
    assert held.source_range.end_us == registry[1].source_time.time_us + 1
    assert (
        len({item.part_id for item in actor.attributes}) == 2
    )  # identical local part IDs did not collide
    assert (
        match_actor_details(detail(registry, projection.shots), compound_query()).status
        == MatchStatus.FULL
    )
    assert not projection.has_unresolved_entities and projection.notes == scene.notes


def test_foreground_object_and_occluded_actor_stay_one_segment_without_new_person():
    registry = evidence()
    payload = model_fixture(registry)
    actor = payload["entities"][0]
    actor["observations"][1]["visibility"] = "occluded"
    actor["parts"][0]["attributes"][0]["evidenceIds"] = [
        registry[0].evidence_id,
        registry[2].evidence_id,
    ]
    payload["owners"][0]["evidenceIds"] = [registry[0].evidence_id]
    projection = project_temporal_scene(scene_from_model(payload, registry))
    assert len(projection.shots) == 1
    assert [item.actor_id for item in projection.shots[0].actors] == ["actor"]
    assert all(
        registry[1].evidence_id not in item.evidence_ids
        for item in projection.shots[0].actors[0].attributes
    )


@pytest.mark.parametrize("uncertain_scope", ["owner", "object", "attribute", "actor"])
def test_uncertain_ownership_or_classification_never_creates_observed_held_fact(uncertain_scope):
    registry = evidence()
    payload = model_fixture(registry)
    if uncertain_scope == "owner":
        payload["owners"][0]["status"] = "uncertain"
    elif uncertain_scope == "attribute":
        payload["entities"][1]["parts"][0]["attributes"][0]["status"] = "uncertain"
    else:
        payload["entities"][0 if uncertain_scope == "actor" else 1]["classification"]["status"] = (
            "uncertain"
        )
    projection = project_temporal_scene(scene_from_model(payload, registry))
    if uncertain_scope == "actor":
        assert not projection.shots[0].actors
    else:
        attributes = projection.shots[0].actors[0].attributes
        held = next(item for item in attributes if item.kind == AttributeKind.HELD_SHAPE)
        assert held.status == AttributeStatus.UNCERTAIN
        assert (
            match_actor_details(detail(registry, projection.shots), compound_query()).status
            != MatchStatus.FULL
        )
    assert projection.has_unresolved_entities == (uncertain_scope != "attribute")


def test_other_actor_cannot_borrow_an_unowned_or_different_owner_object():
    registry = evidence()
    payload = model_fixture(registry)
    actor = deepcopy(payload["entities"][0])
    actor["entityId"] = "other-actor"
    payload["entities"].append(actor)
    projection = project_temporal_scene(scene_from_model(payload, registry))
    assert len(projection.shots[0].actors) == 2
    assert all(
        item.kind != AttributeKind.HELD_SHAPE for item in projection.shots[0].actors[1].attributes
    )
    payload["owners"] = []
    projection = project_temporal_scene(scene_from_model(payload, registry))
    assert all(
        item.kind != AttributeKind.HELD_SHAPE
        for actor in projection.shots[0].actors
        for item in actor.attributes
    )


def test_time_hulls_of_relation_and_attribute_do_not_replace_common_frame():
    registry = evidence()
    payload = model_fixture(registry)
    payload["entities"][1]["parts"][0]["attributes"][0]["evidenceIds"] = [
        registry[0].evidence_id,
        registry[2].evidence_id,
    ]
    payload["owners"][0]["evidenceIds"] = [registry[1].evidence_id]
    projection = project_temporal_scene(scene_from_model(payload, registry))
    assert all(
        item.kind != AttributeKind.HELD_SHAPE for item in projection.shots[0].actors[0].attributes
    )


@pytest.mark.parametrize("boundary", ["cut", "unknown"])
def test_program_splits_segments_and_never_merges_entity_ids_across_boundaries(boundary):
    registry = evidence()
    payload = model_fixture(registry)
    payload["transitions"][1].update(
        state=boundary, basis="scene_change" if boundary == "cut" else "insufficient_evidence"
    )
    payload["owners"] = []
    early_actor = payload["entities"][0]
    late_actor = deepcopy(early_actor)
    late_actor["entityId"] = "actor-after-boundary"
    late_actor["observations"] = late_actor["observations"][2:]
    late_actor["classification"]["evidenceIds"] = [registry[2].evidence_id]
    late_actor["parts"][0]["attributes"][0]["evidenceIds"] = [registry[2].evidence_id]
    early_actor["observations"] = early_actor["observations"][:2]
    early_actor["parts"][0]["attributes"][0]["evidenceIds"] = [
        item.evidence_id for item in registry[:2]
    ]
    payload["entities"] = [early_actor, late_actor]
    payload["environment"] = [
        {
            "partId": "water",
            "kind": "environment",
            "value": "water",
            "status": "observed",
            "evidenceIds": [registry[2].evidence_id],
        }
    ]
    projection = project_temporal_scene(scene_from_model(payload, registry))
    assert [item.shot_id for item in projection.shots] == ["s1", "s2"]
    assert [item.actors[0].actor_id for item in projection.shots] == [
        "actor",
        "actor-after-boundary",
    ]
    assert not projection.shots[0].environment and len(projection.shots[1].environment) == 1
    assert projection.has_unresolved_entities == (boundary == "unknown")


def test_unknown_entity_is_retained_for_review_but_never_fabricated_as_actor():
    registry = evidence()
    payload = model_fixture(registry)
    entity = payload["entities"][1]
    entity["classification"].update(
        kind="unknown", status="uncertain", basis="insufficient_evidence", evidenceIds=[]
    )
    entity["parts"] = []
    payload["owners"] = []
    scene = scene_from_model(payload, registry)
    projection = project_temporal_scene(scene)
    assert len(scene.entities) == 2 and len(projection.shots[0].actors) == 1
    assert projection.has_unresolved_entities


def test_repeated_owner_support_merges_only_same_object_part_and_preserves_order():
    registry = evidence()
    payload = model_fixture(registry)
    relation = payload["owners"][0]
    relation["evidenceIds"] = [registry[0].evidence_id]
    payload["owners"].append(
        dict(relation, evidenceIds=[registry[2].evidence_id], reason="后帧再次明确接触。")
    )
    projection = project_temporal_scene(scene_from_model(payload, registry))
    held = [
        item
        for item in projection.shots[0].actors[0].attributes
        if item.kind == AttributeKind.HELD_SHAPE
    ]
    assert len(held) == 1 and held[0].evidence_ids == (
        registry[0].evidence_id,
        registry[2].evidence_id,
    )


def test_projection_rejects_attribute_overflow_without_silently_truncating():
    registry = evidence()
    payload = model_fixture(registry)
    actor = payload["entities"][0]
    part = actor["parts"][0]
    actor["parts"] = [dict(part, partId=f"hair-{index}") for index in range(16)]
    scene = scene_from_model(payload, registry)
    with pytest.raises(ValueError):
        project_temporal_scene(scene)


def test_projection_does_not_add_unbounded_generated_notes():
    registry = evidence()
    payload = model_fixture(registry)
    payload["notes"] = [f"待核对{index}。" for index in range(16)]
    payload["owners"][0]["status"] = "uncertain"
    scene = scene_from_model(payload, registry)
    projection = project_temporal_scene(scene)
    assert projection.notes == scene.notes and len(projection.notes) == 16
    with pytest.raises(ValueError):
        replace(projection, has_unresolved_entities=1)


@pytest.mark.parametrize("support", ["single", "same_image", "distinct"])
def test_projection_cannot_relax_action_evidence(support):
    registry = evidence()
    payload = model_fixture(registry)
    part = payload["entities"][0]["parts"][0]
    part["partGroup"] = "action"
    part["attributes"][0].update(kind="action", value="raise_item")
    if support == "single":
        part["attributes"][0]["evidenceIds"] = [registry[0].evidence_id]
    elif support == "same_image":
        registry = tuple(replace(item, image_sha256="b" * 64) for item in registry)
    if support == "distinct":
        projection = project_temporal_scene(scene_from_model(payload, registry))
        assert projection.shots[0].actors[0].attributes[0].kind == AttributeKind.ACTION
    else:
        with pytest.raises(ValueError):
            project_temporal_scene(scene_from_model(payload, registry))
