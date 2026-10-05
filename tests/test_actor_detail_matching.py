"""Development fixtures 1–5 verify contracts; they are not human visual labels."""

import hashlib
from dataclasses import replace

import pytest

from gamingcreator.application.actor_detail_matching import match_actor_details
from gamingcreator.domain.actor_details import (
    DETAIL_SCHEMA_VERSION,
    DETAIL_VOCABULARY_VERSION,
    MATCHER_VERSION,
    QUERY_SCHEMA_VERSION,
    QUERY_VERSION,
    ActorDetail,
    AttributeConstraint,
    AttributeKind,
    AttributeStatus,
    CandidateDetail,
    DetailAttribute,
    DetailEvidence,
    MatchStatus,
    QueryConstraint,
    ShotDetail,
    canonical_constraint_json,
    constraint_hash,
    source_range_for_evidence,
)
from gamingcreator.domain.time import SourceInstant

RUN = "run-1"
MEDIA = "media-1"
EVENT = f"{RUN}:{MEDIA}:event:" + "a" * 24
DURATION = 54_743_220


def evidence(frames: int = 3) -> tuple[DetailEvidence, ...]:
    return tuple(
        DetailEvidence(
            f"{RUN}:{MEDIA}:image:{index:06d}",
            f"{index + 1:064x}",
            SourceInstant(35_000_000 + index * 500_000, DURATION),
        )
        for index in range(frames)
    )


def attribute(
    registry: tuple[DetailEvidence, ...],
    kind: AttributeKind,
    value: str,
    part: str,
    frames: tuple[int, ...] = (0, 1, 2),
    status: AttributeStatus = AttributeStatus.OBSERVED,
) -> DetailAttribute:
    support = tuple(registry[index] for index in frames)
    return DetailAttribute(
        part,
        kind,
        value,
        status,
        tuple(item.evidence_id for item in support),
        source_range_for_evidence(support),
    )


def actor(
    attributes: tuple[DetailAttribute, ...],
    actor_id: str = "left",
    shot_id: str = "shot-1",
) -> ActorDetail:
    return ActorDetail(shot_id, actor_id, "画面中的可见主体，控制身份未确认。", attributes)


def shot(
    registry: tuple[DetailEvidence, ...],
    actors: tuple[ActorDetail, ...],
    frames: tuple[int, ...] | None = None,
    shot_id: str = "shot-1",
    environment: tuple[DetailAttribute, ...] = (),
) -> ShotDetail:
    support = registry if frames is None else tuple(registry[index] for index in frames)
    return ShotDetail(
        shot_id,
        source_range_for_evidence(support),
        tuple(item.evidence_id for item in support),
        environment,
        actors,
    )


def detail(
    registry: tuple[DetailEvidence, ...],
    shots: tuple[ShotDetail, ...],
    notes: tuple[str, ...] = (),
) -> CandidateDetail:
    return CandidateDetail(
        RUN,
        MEDIA,
        EVENT,
        "clip-" + hashlib.sha256(f"{RUN}:event:{EVENT}".encode()).hexdigest()[:24],
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "phase0-analyze-detailed-v2",
        "phase0-vision-v6",
        "e" * 64,
        "f" * 64,
        source_range_for_evidence(registry),
        registry,
        shots,
        notes,
    )


def condition(kind: AttributeKind, value: str, group: str = "body") -> AttributeConstraint:
    return AttributeConstraint(kind, value, group)


def positive_fixture() -> tuple[CandidateDetail, QueryConstraint]:
    registry = evidence()
    attributes = (
        attribute(registry, AttributeKind.HAIR_COLOR, "白发", "hair"),
        attribute(registry, AttributeKind.CLOTHING_COLOR, "浅色", "shirt"),
        attribute(registry, AttributeKind.CLOTHING_SHAPE, "上装", "shirt"),
        attribute(registry, AttributeKind.ACTION, "抬头", "body"),
    )
    scene = attribute(registry, AttributeKind.ENVIRONMENT, "石块平台", "scene")
    query = QueryConstraint(
        (
            condition(AttributeKind.HAIR_COLOR, "white", "head"),
            condition(AttributeKind.CLOTHING_COLOR, "light", "shirt"),
            condition(AttributeKind.CLOTHING_SHAPE, "upper_garment", "shirt"),
            condition(AttributeKind.ACTION, "look_up", "activity"),
        ),
        (condition(AttributeKind.ENVIRONMENT, "stone_platform", "scene"),),
    )
    return detail(registry, (shot(registry, (actor(attributes),), environment=(scene,)),)), query


def test_fixture_1_full_requires_same_actor_part_and_shared_real_support() -> None:
    observed, query = positive_fixture()
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.FULL
    assert result.constraint_hash == constraint_hash(query)
    assert result.schema_version == DETAIL_SCHEMA_VERSION
    assert result.vocabulary_version == DETAIL_VOCABULARY_VERSION
    assert result.query_schema_version == QUERY_SCHEMA_VERSION
    assert result.query_version == QUERY_VERSION
    assert result.matcher_version == MATCHER_VERSION
    matched = result.matches[0]
    assert matched.shot_id == "shot-1" and matched.actor_id == "left"
    assert len(matched.satisfied) == 5 and not matched.missing and not matched.uncertain
    assert matched.shared_evidence_ids == tuple(item.evidence_id for item in observed.evidence)
    assert matched.source_range == observed.source_range
    assert {(item.condition.value, item.part_id) for item in matched.satisfied} >= {
        ("light", "shirt"),
        ("upper_garment", "shirt"),
    }


def test_fixture_1_query_actor_attribute_and_environment_order_are_stable() -> None:
    observed, query = positive_fixture()
    unknown = actor((), "right")
    original_shot = observed.shots[0]
    observed = replace(
        observed, shots=(replace(original_shot, actors=(*original_shot.actors, unknown)),)
    )
    shuffled_shot = replace(
        observed.shots[0],
        actors=tuple(
            replace(item, attributes=tuple(reversed(item.attributes)))
            for item in reversed(observed.shots[0].actors)
        ),
        environment=tuple(reversed(observed.shots[0].environment)),
    )
    shuffled = replace(observed, shots=(shuffled_shot,))
    reverse_query = replace(query, actor_all=tuple(reversed(query.actor_all)))
    assert canonical_constraint_json(reverse_query) == canonical_constraint_json(query)
    assert match_actor_details(shuffled, reverse_query) == match_actor_details(observed, query)


def test_fixture_2_cannot_pool_white_hair_and_another_actors_red_coat() -> None:
    registry = evidence()
    white = attribute(registry, AttributeKind.HAIR_COLOR, "white", "hair")
    red = attribute(registry, AttributeKind.CLOTHING_COLOR, "red", "coat")
    coat = attribute(registry, AttributeKind.CLOTHING_SHAPE, "coat", "coat")
    observed = detail(registry, (shot(registry, (actor((white,)), actor((red, coat), "middle"))),))
    query = QueryConstraint(
        (
            condition(AttributeKind.HAIR_COLOR, "white", "head"),
            condition(AttributeKind.CLOTHING_COLOR, "red", "garment"),
            condition(AttributeKind.CLOTHING_SHAPE, "coat", "garment"),
        )
    )
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.PARTIAL
    assert all(len(item.satisfied) < 3 for item in result.matches)
    assert (
        match_actor_details(observed, QueryConstraint((query.actor_all[0],))).status
        == MatchStatus.FULL
    )


def test_fixture_2_red_scarf_and_blue_coat_cannot_become_red_coat() -> None:
    registry = evidence()
    attributes = (
        attribute(registry, AttributeKind.CLOTHING_COLOR, "red", "scarf"),
        attribute(registry, AttributeKind.CLOTHING_SHAPE, "scarf", "scarf"),
        attribute(registry, AttributeKind.CLOTHING_COLOR, "blue", "coat"),
        attribute(registry, AttributeKind.CLOTHING_SHAPE, "coat", "coat"),
    )
    query = QueryConstraint(
        (
            condition(AttributeKind.CLOTHING_COLOR, "red", "garment"),
            condition(AttributeKind.CLOTHING_SHAPE, "coat", "garment"),
        )
    )
    result = match_actor_details(detail(registry, (shot(registry, (actor(attributes),)),)), query)
    assert result.status != MatchStatus.FULL
    assert all(len(item.satisfied) <= 1 for item in result.matches)
    assert result.status == MatchStatus.NO_MATCH
    assert {item.part_id for item in result.matches[0].counter_evidence} == {"coat"}


def test_fixture_3_uncertain_weapon_class_cannot_override_observed_shape() -> None:
    registry = evidence()
    observed_shape = attribute(registry, AttributeKind.HELD_SHAPE, "蓝色扁平物体", "item")
    uncertain_class = attribute(
        registry, AttributeKind.HELD_CLASS, "武器", "item", status=AttributeStatus.UNCERTAIN
    )
    observed = detail(registry, (shot(registry, (actor((observed_shape, uncertain_class)),)),))
    shape_query = QueryConstraint(
        (condition(AttributeKind.HELD_SHAPE, "blue_flat_object", "item"),)
    )
    class_query = QueryConstraint((condition(AttributeKind.HELD_CLASS, "weapon", "item"),))
    assert match_actor_details(observed, shape_query).status == MatchStatus.FULL
    result = match_actor_details(observed, class_query)
    assert result.status == MatchStatus.UNVERIFIED
    assert not result.matches[0].satisfied and len(result.matches[0].uncertain) == 1
    combined = match_actor_details(
        observed, QueryConstraint((*shape_query.actor_all, *class_query.actor_all))
    )
    assert combined.status == MatchStatus.PARTIAL


def test_fixture_3_overlapping_observed_conflict_is_neither_full_nor_reliable_negative() -> None:
    registry = evidence()
    white = attribute(registry, AttributeKind.HAIR_COLOR, "white", "hair")
    black = attribute(registry, AttributeKind.HAIR_COLOR, "black", "hair")
    observed = detail(registry, (shot(registry, (actor((white, black)),)),))
    result = match_actor_details(
        observed, QueryConstraint((condition(AttributeKind.HAIR_COLOR, "white"),))
    )
    assert result.status == MatchStatus.UNVERIFIED
    assert result.notes == ("observed_attribute_conflict",)
    assert result.matches[0].uncertain[0].evidence_ids == white.evidence_ids
    assert result.matches[0].conflicts[0].values == ("black", "white")
    assert not result.matches[0].counter_evidence


def test_fixture_4_cannot_bridge_identical_actor_ids_across_shots() -> None:
    registry = evidence(4)
    clothing = attribute(registry, AttributeKind.CLOTHING_COLOR, "light", "shirt", (0, 1))
    action = attribute(registry, AttributeKind.ACTION, "look_up", "body", (2, 3))
    observed = detail(
        registry,
        (
            shot(registry, (actor((clothing,)),), (0, 1)),
            shot(registry, (actor((action,), shot_id="shot-2"),), (2, 3), "shot-2"),
        ),
    )
    query = QueryConstraint(
        (
            condition(AttributeKind.CLOTHING_COLOR, "light", "shirt"),
            condition(AttributeKind.ACTION, "look_up", "body"),
        )
    )
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.PARTIAL
    assert {(item.shot_id, item.actor_id) for item in result.matches} == {
        ("shot-1", "left"),
        ("shot-2", "left"),
    }
    assert all(len(item.satisfied) == 1 for item in result.matches)


@pytest.mark.parametrize("uncertain_value", [False, True])
def test_fixture_4_black_actor_plus_unknown_actor_is_not_no_match(uncertain_value: bool) -> None:
    registry = evidence()
    black = attribute(registry, AttributeKind.HAIR_COLOR, "black", "hair")
    unknown = (
        (
            attribute(
                registry,
                AttributeKind.HAIR_COLOR,
                "white",
                "hair",
                status=AttributeStatus.UNCERTAIN,
            ),
        )
        if uncertain_value
        else ()
    )
    observed = detail(registry, (shot(registry, (actor((black,)), actor(unknown, "other"))),))
    result = match_actor_details(
        observed, QueryConstraint((condition(AttributeKind.HAIR_COLOR, "white"),))
    )
    assert result.status == MatchStatus.UNVERIFIED
    assert len(result.matches) == 2


def test_fixture_4_unassigned_or_unknown_shot_prevents_no_match() -> None:
    registry = evidence()
    black = attribute(registry, AttributeKind.HAIR_COLOR, "black", "hair", (0, 1))
    observed = detail(registry, (shot(registry, (actor((black,)),), (0, 1)),))
    query = QueryConstraint((condition(AttributeKind.HAIR_COLOR, "white"),))
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.UNVERIFIED and result.notes == ("unassigned_evidence",)
    assert observed.unassigned_evidence_ids == (registry[2].evidence_id,)
    unknown_shot = shot(registry, (), (2,), "unknown-shot")
    assert (
        match_actor_details(
            replace(observed, shots=(*observed.shots, unknown_shot), unassigned_evidence_ids=()),
            query,
        ).status
        == MatchStatus.UNVERIFIED
    )


def test_fixture_4_no_match_requires_observed_opposition_at_every_source_frame() -> None:
    registry = evidence()
    query = QueryConstraint((condition(AttributeKind.HAIR_COLOR, "white"),))
    partial_black = attribute(registry, AttributeKind.HAIR_COLOR, "black", "hair", (0,))
    coat = attribute(registry, AttributeKind.CLOTHING_SHAPE, "coat", "coat", (1, 2))
    observed = detail(registry, (shot(registry, (actor((partial_black, coat)),)),))
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.UNVERIFIED
    all_black = attribute(registry, AttributeKind.HAIR_COLOR, "black", "hair")
    negative = detail(registry, (shot(registry, (actor((all_black,)),)),))
    result = match_actor_details(negative, query)
    assert result.status == MatchStatus.NO_MATCH
    assert result.matches[0].counter_evidence[0].evidence_ids == all_black.evidence_ids


def test_fixture_4_scarf_color_cannot_exclude_an_unknown_coat() -> None:
    registry = evidence()
    scarf_blue = attribute(registry, AttributeKind.CLOTHING_COLOR, "blue", "scarf")
    scarf_shape = attribute(registry, AttributeKind.CLOTHING_SHAPE, "scarf", "scarf")
    coat_shape = attribute(registry, AttributeKind.CLOTHING_SHAPE, "coat", "coat")
    observed = detail(registry, (shot(registry, (actor((scarf_blue, scarf_shape, coat_shape)),)),))
    query = QueryConstraint(
        (
            condition(AttributeKind.CLOTHING_COLOR, "red", "garment"),
            condition(AttributeKind.CLOTHING_SHAPE, "coat", "garment"),
        )
    )
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.PARTIAL
    assert not result.matches[0].opposed and not result.matches[0].counter_evidence
    assert result.matches[0].satisfied[0].part_id == "coat"


def test_fixture_5_convex_hulls_overlap_without_a_shared_supporting_frame() -> None:
    registry = evidence()
    hair = attribute(registry, AttributeKind.HAIR_COLOR, "white", "hair", (0, 2))
    clothing = attribute(registry, AttributeKind.CLOTHING_COLOR, "light", "shirt", (1,))
    assert hair.source_range.start_us < clothing.source_range.start_us < hair.source_range.end_us
    observed = detail(registry, (shot(registry, (actor((hair, clothing)),)),))
    query = QueryConstraint(
        (
            condition(AttributeKind.HAIR_COLOR, "white", "head"),
            condition(AttributeKind.CLOTHING_COLOR, "light", "shirt"),
        )
    )
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.PARTIAL
    assert len(result.matches[0].satisfied) == 1


def test_fixture_5_no_attribute_persistence_past_its_observed_half_open_range() -> None:
    registry = evidence()
    hair = attribute(registry, AttributeKind.HAIR_COLOR, "white", "hair", (0,))
    clothing = attribute(registry, AttributeKind.CLOTHING_COLOR, "light", "shirt", (2,))
    observed = detail(registry, (shot(registry, (actor((hair, clothing)),)),))
    query = QueryConstraint(
        (
            condition(AttributeKind.HAIR_COLOR, "white", "head"),
            condition(AttributeKind.CLOTHING_COLOR, "light", "shirt"),
        )
    )
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.PARTIAL
    assert result.matches[0].source_range in (hair.source_range, clothing.source_range)


def test_environment_cannot_borrow_actor_attributes_or_other_frames() -> None:
    registry = evidence()
    hair = attribute(registry, AttributeKind.HAIR_COLOR, "white", "hair", (0, 2))
    environment = attribute(registry, AttributeKind.ENVIRONMENT, "water", "scene", (1,))
    observed = detail(registry, (shot(registry, (actor((hair,)),), environment=(environment,)),))
    query = QueryConstraint(
        (condition(AttributeKind.HAIR_COLOR, "white", "head"),),
        (condition(AttributeKind.ENVIRONMENT, "water", "scene"),),
    )
    assert match_actor_details(observed, query).status == MatchStatus.PARTIAL


def test_missing_sidecar_empty_actors_or_only_uncertainty_are_unverified() -> None:
    query = QueryConstraint((condition(AttributeKind.HAIR_COLOR, "white"),))
    result = match_actor_details(None, query)
    assert result.status == MatchStatus.UNVERIFIED and result.notes == ("detail_missing",)
    assert result.constraint_hash == constraint_hash(query)
    registry = evidence()
    assert (
        match_actor_details(detail(registry, (shot(registry, ()),)), query).status
        == MatchStatus.UNVERIFIED
    )


def test_nonexclusive_mechanics_and_shapes_are_missing_not_negative() -> None:
    registry = evidence()
    action = attribute(registry, AttributeKind.ACTION, "move", "body")
    item = attribute(registry, AttributeKind.HELD_SHAPE, "long_rod", "item")
    observed = detail(registry, (shot(registry, (actor((action, item)),)),))
    query = QueryConstraint(
        (
            condition(AttributeKind.ACTION, "jump", "body"),
            condition(AttributeKind.HELD_SHAPE, "flat_object", "item"),
        )
    )
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.UNVERIFIED
    assert not result.matches[0].opposed and len(result.matches[0].missing) == 2


def test_partial_preserves_same_actor_support_without_mutating_the_candidate() -> None:
    observed, query = positive_fixture()
    before = repr(observed)
    query = replace(
        query, actor_all=(*query.actor_all, condition(AttributeKind.HELD_CLASS, "weapon", "item"))
    )
    result = match_actor_details(observed, query)
    assert result.status == MatchStatus.PARTIAL
    assert result.matches[0].missing == (condition(AttributeKind.HELD_CLASS, "weapon", "item"),)
    assert repr(observed) == before
