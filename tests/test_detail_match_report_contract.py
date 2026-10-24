"""TD009 match-report field / inert / static-index contracts. Offline only."""

from __future__ import annotations

import copy
import hashlib

import pytest
from test_actor_detail_matching import (
    EVENT,
    RUN,
    actor,
    attribute,
    condition,
    detail,
    evidence,
    shot,
)
from test_detail_inspection import publish_fixture, refuse_sends, seed_project
from test_detail_query import constraint

from gamingcreator.application.detail_query import (
    MATCH_REPORT_VERSION,
    assert_match_report_contract,
    build_match_report_inert_contract,
    match_report,
)
from gamingcreator.domain.actor_details import (
    MATCHER_VERSION,
    AttributeKind,
    AttributeStatus,
    MatchStatus,
    QueryConstraint,
)
from gamingcreator.infrastructure.detail_query_sidecar import match_refinement


def _weapon_coexist_detail():
    registry = evidence()
    observed_shape = attribute(registry, AttributeKind.HELD_SHAPE, "蓝色扁平物体", "item")
    observed_class = attribute(
        registry, AttributeKind.HELD_CLASS, "武器", "item", status=AttributeStatus.OBSERVED
    )
    uncertain_class = attribute(
        registry, AttributeKind.HELD_CLASS, "武器", "item", status=AttributeStatus.UNCERTAIN
    )
    return detail(
        registry,
        (shot(registry, (actor((observed_shape, observed_class, uncertain_class)),)),),
    )


def test_match_report_v1_1_inert_fields_and_constraint_hash() -> None:
    query = QueryConstraint((condition(AttributeKind.HELD_CLASS, "weapon", "item"),))
    document = match_report(
        None,
        _weapon_coexist_detail(),
        query,
        run_id=RUN,
        event_id=EVENT,
        request_digest=None,
    )
    assert document["schemaVersion"] == MATCH_REPORT_VERSION == "actor-detail-match-report-v1.1"
    assert document["humanLabels"] is None
    assert document["qualityGate"] is None
    assert document["independentStaticClothingIndex"] is False
    assert document["inertContract"] == build_match_report_inert_contract()
    assert (
        document["constraintHash"]
        == hashlib.sha256(document["constraintJson"].encode("utf-8")).hexdigest()
    )
    assert document["result"]["matcherVersion"] == MATCHER_VERSION
    assert document["result"]["status"] == MatchStatus.UNVERIFIED.value
    assert_match_report_contract(document)


@pytest.mark.parametrize(
    "damage",
    [
        "humanLabels",
        "qualityGate_true",
        "qualityGate_passed",
        "static_index",
        "drop_inert",
        "bad_hash",
    ],
)
def test_assert_match_report_contract_rejects_pass_claims_and_static_index(damage: str) -> None:
    query = QueryConstraint((condition(AttributeKind.HAIR_COLOR, "white", "hair"),))
    registry = evidence()
    hair = attribute(registry, AttributeKind.HAIR_COLOR, "白发", "hair")
    document = match_report(
        None,
        detail(registry, (shot(registry, (actor((hair,)),)),)),
        query,
        run_id=RUN,
        event_id=EVENT,
        request_digest=None,
    )
    broken = copy.deepcopy(document)
    if damage == "humanLabels":
        broken["humanLabels"] = {"pass": True}
    elif damage == "qualityGate_true":
        broken["qualityGate"] = True
    elif damage == "qualityGate_passed":
        broken["qualityGate"] = "passed"
    elif damage == "static_index":
        broken["independentStaticClothingIndex"] = True
    elif damage == "drop_inert":
        broken.pop("inertContract")
    elif damage == "bad_hash":
        broken["constraintHash"] = "0" * 64
    with pytest.raises(ValueError):
        assert_match_report_contract(broken)


def test_match_refinement_readonly_keeps_inert_and_no_static_index(tmp_path, monkeypatch) -> None:
    project, _, timeline = seed_project(tmp_path)
    publish_fixture(project, timeline)
    refuse_sends(monkeypatch)
    document = match_refinement(
        project,
        timeline,
        timeline.events[0].event_id,
        constraint(("hair_color", "white", "hair")),
        profile="v1",
        save=False,
    )
    assert document["schemaVersion"] == "actor-detail-match-report-v1.1"
    assert document["humanLabels"] is document["qualityGate"] is None
    assert document["independentStaticClothingIndex"] is False
    assert (
        document["constraintHash"]
        == hashlib.sha256(document["constraintJson"].encode("utf-8")).hexdigest()
    )
    assert_match_report_contract(document)
