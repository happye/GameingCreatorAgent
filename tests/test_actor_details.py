"""Independent engineering contracts, not visual quality or human-label evidence."""

import asyncio
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.retrieval import search_timeline
from gamingcreator.application.storage import RunConfiguration, RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.actor_details import (
    DETAIL_SCHEMA_VERSION,
    DETAIL_VOCABULARY_VERSION,
    MATCHER_VERSION,
    QUERY_SCHEMA_VERSION,
    QUERY_VERSION,
    ActorDetail,
    ActorMatch,
    AttributeConstraint,
    AttributeKind,
    AttributeStatus,
    CandidateDetail,
    ConstraintSupport,
    DetailAttribute,
    DetailEvidence,
    DetailMatch,
    MatchStatus,
    QueryConstraint,
    ShotDetail,
    canonical_constraint_json,
    constraint_hash,
    normalize_attribute_value,
    source_range_for_evidence,
)
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import INT64_MAX, SourceInstant, SourceRange

DURATION = 10_000_000
EVENT_ID = "run:media:event:" + "a" * 24


def frames(count=3):
    return tuple(
        DetailEvidence(
            f"run:media:image:{index:06d}",
            hashlib.sha256(f"frame-{index}".encode()).hexdigest(),
            SourceInstant(1_000_000 + index * 100_000, DURATION),
        )
        for index in range(count)
    )


def supported_range(evidence):
    return SourceRange(
        evidence[0].source_time.time_us,
        evidence[-1].source_time.time_us + 1,
        evidence[0].source_time.duration_us,
    )


def attribute(evidence, *, part="hair", kind=AttributeKind.HAIR_COLOR, value="white"):
    return DetailAttribute(
        part,
        kind,
        value,
        AttributeStatus.OBSERVED,
        tuple(item.evidence_id for item in evidence),
        supported_range(evidence),
    )


def shot(evidence, *, shot_id="shot", actor_id="actor", attributes=None):
    actor = ActorDetail(
        shot_id,
        actor_id,
        "工程fixture中的可见主体",
        (attribute(evidence),) if attributes is None else attributes,
    )
    return ShotDetail(
        shot_id,
        supported_range(evidence),
        tuple(item.evidence_id for item in evidence),
        (),
        (actor,),
    )


def searched_candidate(evidence):
    """Produce the ID through shipped lexical retrieval, never a copied hash formula."""
    asset = MediaAsset(
        "media",
        Path("fixture-source.mp4"),
        "b" * 64,
        (MediaStream(0, "video", Fraction(1, 1_000_000), 0, DURATION),),
        Fraction(0),
        DURATION,
        "engineering-fixture",
    )
    configuration = RunConfiguration(
        AnalysisConfig("fixture", "fixture", 10, 10),
        Decimal("1"),
        "fixture-pipeline-v1",
        "c" * 64,
    )
    run = StoredRun("run", asset, configuration, "c" * 64, RunStatus.COMPLETED, None)
    references = tuple(
        EvidenceReference(
            item.evidence_id,
            "media",
            "image",
            item.source_time,
            Path(f"fixture-{index}.jpg"),
            item.image_sha256,
            "fixture-transform-v1",
        )
        for index, item in enumerate(evidence)
    )
    event = SemanticEvent(
        EVENT_ID,
        "media",
        "run",
        SourceRange(1_000_000, 2_000_000, DURATION),
        ("白发角色抬头",),
        (),
        tuple(item.evidence_id for item in evidence),
        "visual",
        "工程fixture，不代表模型识别或人工质量标签。",
    )
    timeline = StoredTimeline(run, (), references, (), (event,), ())
    result = asyncio.run(search_timeline(timeline, "白发", mode="lexical"))
    assert len(result.candidates) == 1
    assert timeline.events == (event,)
    return result.candidates[0]


def candidate(evidence=None, shots=None):
    evidence = frames() if evidence is None else evidence
    clip = searched_candidate(evidence)
    return CandidateDetail(
        "run",
        "media",
        clip.event_id,
        clip.candidate_id,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "fixture-pipeline-v1",
        "fixture-prompt-v1",
        "d" * 64,
        "e" * 64,
        clip.source_range,
        evidence,
        (shot(evidence),) if shots is None else shots,
    )


@pytest.fixture
def base():
    return candidate()


def test_registered_search_candidate_identity_and_original_facts_are_compatible(base):
    actual = searched_candidate(base.evidence)
    assert base.candidate_id == actual.candidate_id
    assert base.event_id == actual.event_id
    assert base.source_range == actual.source_range
    assert actual.observable_facts == ("白发角色抬头",)
    assert actual.evidence_ids == tuple(item.evidence_id for item in base.evidence)


def test_contracts_are_frozen_without_replacing_base_event(base):
    with pytest.raises(FrozenInstanceError):
        base.run_id = "changed"
    assert base.run_id == "run"


def test_source_range_is_exact_half_open_hull_and_handles_last_microsecond():
    evidence = frames()
    assert source_range_for_evidence(evidence) == SourceRange(1_000_000, 1_200_001, DURATION)
    last = replace(evidence[0], source_time=SourceInstant(INT64_MAX - 1, INT64_MAX))
    assert source_range_for_evidence((last,)) == SourceRange(INT64_MAX - 1, INT64_MAX, INT64_MAX)


@pytest.mark.parametrize(
    "case", ["empty", "list", "reverse", "duplicate_id", "same_clock", "duration"]
)
def test_source_clock_sequence_rejects_untraceable_ranges(case):
    evidence = frames()
    bad = {
        "empty": (),
        "list": list(evidence),
        "reverse": tuple(reversed(evidence)),
        "duplicate_id": (evidence[0], replace(evidence[1], evidence_id=evidence[0].evidence_id)),
        "same_clock": (evidence[0], replace(evidence[1], source_time=evidence[0].source_time)),
        "duration": (
            evidence[0],
            replace(evidence[1], source_time=SourceInstant(1_100_000, DURATION + 1)),
        ),
    }[case]
    with pytest.raises(ValueError):
        source_range_for_evidence(bad)


@pytest.mark.parametrize(
    "changes", [{"image_sha256": "A" * 64}, {"image_sha256": "bad"}, {"source_time": 1.0}]
)
def test_evidence_rejects_noncanonical_hash_and_untyped_clock(changes):
    with pytest.raises(ValueError):
        replace(frames()[0], **changes)


@pytest.mark.parametrize("field", ["run_id", "media_id", "event_id", "candidate_id"])
def test_candidate_does_not_borrow_base_identity(base, field):
    with pytest.raises(ValueError):
        replace(base, **{field: "foreign"})


@pytest.mark.parametrize("identity", ["other:media:image:000000", "run:other:image:000000"])
def test_candidate_rejects_foreign_run_or_media_evidence(base, identity):
    evidence = (replace(base.evidence[0], evidence_id=identity), *base.evidence[1:])
    with pytest.raises(ValueError, match="Evidence is foreign or outside"):
        replace(base, evidence=evidence, shots=(shot(evidence),))


@pytest.mark.parametrize("clock", [999_999, 2_000_000])
def test_candidate_evidence_obeys_half_open_original_interval(base, clock):
    index = 0 if clock < base.source_range.start_us else -1
    evidence = list(base.evidence)
    evidence[index] = replace(evidence[index], source_time=SourceInstant(clock, DURATION))
    updated = tuple(evidence)
    with pytest.raises(ValueError, match="Evidence is foreign or outside"):
        replace(base, evidence=updated, shots=(shot(updated),))


@pytest.mark.parametrize("scope", ["shot", "attribute"])
@pytest.mark.parametrize(
    "case", ["guessed_endpoint", "fake_duration", "unknown_id", "reverse_ids", "duplicate_ids"]
)
def test_nested_support_must_match_the_registered_clocks(base, scope, case):
    original_shot = base.shots[0]
    original = original_shot if scope == "shot" else original_shot.actors[0].attributes[0]
    ids = original.evidence_ids
    changes = {
        "guessed_endpoint": {"source_range": SourceRange(1_000_000, 1_200_002, DURATION)},
        "fake_duration": {"source_range": SourceRange(1_000_000, 1_200_001, DURATION + 1)},
        "unknown_id": {"evidence_ids": ("run:media:image:000009",)},
        "reverse_ids": {"evidence_ids": tuple(reversed(ids))},
        "duplicate_ids": {"evidence_ids": (ids[0], ids[0])},
    }[case]
    with pytest.raises(ValueError):
        nested = replace(original, **changes)
        if scope == "attribute":
            actor = replace(original_shot.actors[0], attributes=(nested,))
            nested = replace(original_shot, actors=(actor,))
        replace(base, shots=(nested,))


def test_actor_ids_are_local_to_a_shot_and_evidence_cannot_cross_shots(base):
    first = shot(base.evidence[:1], shot_id="s1")
    second = shot(base.evidence[1:], shot_id="s2")
    valid = replace(base, shots=(second, first))
    assert [item.shot_id for item in valid.shots] == ["s1", "s2"]
    assert valid.shots[0].actors[0].actor_id == valid.shots[1].actors[0].actor_id
    assert valid.unassigned_evidence_ids == ()
    cross_attribute = attribute(base.evidence[1:])
    bad_actor = replace(first.actors[0], attributes=(cross_attribute,))
    with pytest.raises(ValueError):
        replace(base, shots=(replace(first, actors=(bad_actor,)), second))


def test_overlapping_shot_hulls_and_shared_frames_are_rejected(base):
    first = shot((base.evidence[0], base.evidence[2]), shot_id="s1")
    middle = shot(base.evidence[1:2], shot_id="s2")
    with pytest.raises(ValueError):
        replace(base, shots=(first, middle))
    with pytest.raises(ValueError):
        replace(base, shots=(base.shots[0], replace(base.shots[0], shot_id="s2", actors=())))


def test_unassigned_evidence_is_derived_and_cannot_be_forged(base):
    reduced = replace(base, shots=(shot(base.evidence[:1]),))
    assert reduced.unassigned_evidence_ids == tuple(item.evidence_id for item in base.evidence[1:])
    with pytest.raises(ValueError):
        replace(reduced, unassigned_evidence_ids=(base.evidence[0].evidence_id,))


def test_static_attribute_is_valid_but_single_frame_action_is_not(base):
    static = attribute(base.evidence[:1])
    replace(base, shots=(shot(base.evidence, attributes=(static,)),))
    with pytest.raises(ValueError):
        replace(static, kind=AttributeKind.ACTION, value="look_up")


def test_action_needs_distinct_source_times_and_image_content(base):
    evidence = base.evidence[:2]
    action = attribute(evidence, part="body", kind=AttributeKind.ACTION, value="look_up")
    valid = replace(base, evidence=evidence, shots=(shot(evidence, attributes=(action,)),))
    assert valid.shots[0].actors[0].attributes == (action,)
    same_image = (evidence[0], replace(evidence[1], image_sha256=evidence[0].image_sha256))
    with pytest.raises(ValueError):
        replace(base, evidence=same_image, shots=(shot(same_image, attributes=(action,)),))
    same_clock = (evidence[0], replace(evidence[1], source_time=evidence[0].source_time))
    with pytest.raises(ValueError):
        replace(base, evidence=same_clock, shots=())


@pytest.mark.parametrize("field", ["evidence", "shots", "notes", "unassigned_evidence_ids"])
def test_candidate_collections_must_be_typed_tuples(base, field):
    with pytest.raises(ValueError):
        replace(base, **{field: list(getattr(base, field))})


def test_actor_and_environment_scopes_are_separate(base):
    environment = attribute(
        base.evidence, part="scene", kind=AttributeKind.ENVIRONMENT, value="water"
    )
    with pytest.raises(ValueError):
        replace(base.shots[0].actors[0], attributes=(environment,))
    with pytest.raises(ValueError):
        replace(base.shots[0], environment=(attribute(base.evidence),))
    with pytest.raises(ValueError):
        replace(base.shots[0], actors=(replace(base.shots[0].actors[0], shot_id="other"),))
    with pytest.raises(ValueError):
        replace(base.shots[0], actors=(base.shots[0].actors[0],) * 2)


@pytest.mark.parametrize("scope", ["attributes", "actors", "environment"])
def test_nested_collections_reject_lists_and_wrong_types(base, scope):
    node = base.shots[0].actors[0] if scope == "attributes" else base.shots[0]
    for bad in (list(getattr(node, scope)), (object(),)):
        with pytest.raises(ValueError):
            replace(node, **{scope: bad})


def test_maximum_frames_shots_actors_and_attributes_are_bounded():
    nine = frames(9)
    maximum = candidate(nine, tuple(shot((item,), shot_id=f"s{i}") for i, item in enumerate(nine)))
    assert len(maximum.evidence) == len(maximum.shots) == 9
    with pytest.raises(ValueError):
        candidate(frames(10), ())
    attrs = tuple(attribute(nine[:1], part=f"part{i}") for i in range(16))
    actor = ActorDetail("shot", "actor", "engineering fixture", attrs)
    with pytest.raises(ValueError):
        replace(actor, attributes=attrs + (attribute(nine[:1], part="overflow"),))
    actors = tuple(replace(actor, actor_id=f"a{i}") for i in range(8))
    largest_shot = ShotDetail(
        "shot", supported_range(nine), tuple(item.evidence_id for item in nine), (), actors
    )
    assert len(largest_shot.actors) == 8
    with pytest.raises(ValueError):
        replace(largest_shot, actors=actors + (replace(actor, actor_id="overflow"),))
    environment = tuple(
        attribute(nine, part=f"scene{i}", kind=AttributeKind.ENVIRONMENT, value="water")
        for i in range(16)
    )
    assert len(replace(largest_shot, environment=environment).environment) == 16
    with pytest.raises(ValueError):
        replace(
            largest_shot, environment=environment + (replace(environment[0], part_id="overflow"),)
        )


@pytest.mark.parametrize(
    "changes",
    [{"kind": "hair_color"}, {"status": "observed"}, {"value": "invented"}, {"evidence_ids": []}],
)
def test_attribute_kind_status_value_and_references_are_explicit(base, changes):
    with pytest.raises(ValueError):
        replace(base.shots[0].actors[0].attributes[0], **changes)


@pytest.mark.parametrize("field", ["schema_version", "vocabulary_version"])
def test_candidate_rejects_unknown_contract_versions(base, field):
    with pytest.raises(ValueError):
        replace(base, **{field: "future-version"})


@pytest.mark.parametrize(
    "field",
    [
        "event_fingerprint",
        "media_sha256",
        "configuration_hash",
        "base_prompt_hash",
        "detail_identity_hash",
    ],
)
def test_candidate_hashes_are_complete_lowercase_sha256(base, field):
    with pytest.raises(ValueError):
        replace(base, **{field: "A" * 64})


def test_visible_blue_shape_remains_distinct_from_uncertain_equipment_class(base):
    visible = attribute(
        base.evidence[:1], part="held", kind=AttributeKind.HELD_SHAPE, value="蓝色扁平物体"
    )
    uncertain = replace(
        visible, kind=AttributeKind.HELD_CLASS, value="权杖", status=AttributeStatus.UNCERTAIN
    )
    assert visible.value == "blue_flat_object"
    assert visible.status == AttributeStatus.OBSERVED
    assert uncertain.value == "staff" and uncertain.status == AttributeStatus.UNCERTAIN
    assert visible.kind != uncertain.kind


def test_query_hash_is_canonical_for_order_and_explicit_chinese_english_aliases():
    first = QueryConstraint(
        (
            AttributeConstraint(AttributeKind.HAIR_COLOR, " 白发 ", "hair"),
            AttributeConstraint(AttributeKind.CLOTHING_SHAPE, "外套", "coat"),
        ),
        (AttributeConstraint(AttributeKind.ENVIRONMENT, "水面", "scene"),),
    )
    second = QueryConstraint(
        (
            AttributeConstraint(AttributeKind.CLOTHING_SHAPE, "jacket", "coat"),
            AttributeConstraint(AttributeKind.HAIR_COLOR, "WHITE HAIR", "hair"),
        ),
        (AttributeConstraint(AttributeKind.ENVIRONMENT, "water", "scene"),),
    )
    assert first == second
    assert canonical_constraint_json(first) == canonical_constraint_json(second)
    assert constraint_hash(first) == constraint_hash(second)
    assert (
        json.loads(canonical_constraint_json(first))["vocabularyVersion"]
        == DETAIL_VOCABULARY_VERSION
    )


def test_query_versions_and_normalized_value_are_part_of_the_frozen_hash():
    query = QueryConstraint((AttributeConstraint(AttributeKind.HAIR_COLOR, "white", "hair"),))
    golden = (
        '{"actorAll":[{"kind":"hair_color","partGroup":"hair","value":"white"}],'
        '"environmentAll":[],"schemaVersion":"actor-detail-query-schema-v1",'
        '"version":"actor-detail-query-v1","vocabularyVersion":"actor-detail-vocabulary-v1"}'
    )
    assert canonical_constraint_json(query) == golden
    assert (
        constraint_hash(query) == "1342b945da41cb36d95f3d6d825d99aba126caf753db55347210ebf8cf736ad8"
    )
    assert query.schema_version == QUERY_SCHEMA_VERSION
    assert query.version == QUERY_VERSION
    assert constraint_hash(query) != constraint_hash(
        replace(query, actor_all=(AttributeConstraint(AttributeKind.HAIR_COLOR, "black", "hair"),))
    )


@pytest.mark.parametrize("field", ["schema_version", "version", "vocabulary_version"])
def test_query_rejects_unknown_versions(field):
    query = QueryConstraint((AttributeConstraint(AttributeKind.HAIR_COLOR, "white", "hair"),))
    with pytest.raises(ValueError):
        replace(query, **{field: "future"})


def test_query_rejects_unknown_values_duplicates_wrong_scopes_and_collections():
    white = AttributeConstraint(AttributeKind.HAIR_COLOR, "white", "hair")
    with pytest.raises(ValueError):
        normalize_attribute_value(AttributeKind.HELD_CLASS, "恶魔领主官方权杖")
    with pytest.raises(ValueError):
        QueryConstraint((white, AttributeConstraint(AttributeKind.HAIR_COLOR, "白发", "hair")))
    with pytest.raises(ValueError):
        QueryConstraint((AttributeConstraint(AttributeKind.ENVIRONMENT, "water", "scene"),))
    with pytest.raises(ValueError):
        QueryConstraint((white,), (white,))
    with pytest.raises(ValueError):
        QueryConstraint([white])
    with pytest.raises(ValueError):
        QueryConstraint((white,), [])
    with pytest.raises(ValueError):
        QueryConstraint(())
    maximum = QueryConstraint(tuple(replace(white, part_group=f"g{i}") for i in range(16)))
    with pytest.raises(ValueError):
        replace(maximum, actor_all=maximum.actor_all + (replace(white, part_group="overflow"),))


def report_support(base):
    condition = AttributeConstraint(AttributeKind.HAIR_COLOR, "white", "hair")
    support = ConstraintSupport(
        condition,
        "hair",
        tuple(item.evidence_id for item in base.evidence),
        supported_range(base.evidence),
    )
    match = ActorMatch(
        "shot", "actor", (support,), (), (), (), support.evidence_ids, support.source_range, ()
    )
    return condition, support, match


def test_full_report_requires_supported_observed_conditions(base):
    condition, _, match = report_support(base)
    report = DetailMatch(MatchStatus.FULL, constraint_hash(QueryConstraint((condition,))), (match,))
    assert report.status == MatchStatus.FULL
    assert (
        report.schema_version == DETAIL_SCHEMA_VERSION and report.matcher_version == MATCHER_VERSION
    )
    with pytest.raises(ValueError):
        replace(report, matches=())
    with pytest.raises(ValueError):
        replace(
            report,
            matches=(
                replace(
                    match,
                    missing=(condition,),
                    satisfied=(),
                    shared_evidence_ids=(),
                    source_range=None,
                ),
            ),
        )


@pytest.mark.parametrize(
    "changes", [{"part_id": None}, {"evidence_ids": ()}, {"source_range": None}]
)
def test_report_evidence_support_never_accepts_missing_part_refs_or_range(base, changes):
    _, support, _ = report_support(base)
    with pytest.raises(ValueError):
        replace(support, **changes)


@pytest.mark.parametrize(
    "interval",
    [SourceRange(9_000_000, 9_000_001, DURATION), SourceRange(1_000_000, 1_200_001, DURATION + 1)],
)
def test_report_common_range_cannot_escape_or_change_support_duration(base, interval):
    _, _, match = report_support(base)
    with pytest.raises(ValueError):
        replace(match, source_range=interval)


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "query_schema_version",
        "query_version",
        "vocabulary_version",
        "matcher_version",
    ],
)
def test_match_report_rejects_unknown_versions(base, field):
    condition, _, match = report_support(base)
    report = DetailMatch(MatchStatus.FULL, constraint_hash(QueryConstraint((condition,))), (match,))
    with pytest.raises(ValueError):
        replace(report, **{field: "future"})
