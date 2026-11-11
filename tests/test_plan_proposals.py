"""Fake text proposals verify boundaries, not real model understanding."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_creation_planner import brief, clips

from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.plan_proposals import (
    SCHEMA_VERSION,
    compile_plan_proposal,
    create_plan_snapshot,
    validate_plan_proposal,
)
from gamingcreator.application.rendering import validate_render_plan


def timelines():
    material = clips()
    return (
        SimpleNamespace(
            run=SimpleNamespace(run_id="run", asset=material[0].asset),
            events=tuple(c.event for c in material),
            evidence=tuple(SimpleNamespace(evidence_id=c.event.evidence_ids[0]) for c in material),
        ),
    )


def output(snapshot, orders=((1, 2, 3),)):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "snapshotFingerprint": snapshot.fingerprint,
        "kind": "plan_proposal",
        "questions": [],
        "plans": [
            {
                "title": "文字提案",
                "structure": "先展示再解释",
                "shots": [{"candidateId": f"candidate-{i}", "role": "展示"} for i in order],
            }
            for order in orders
        ],
    }


@pytest.mark.parametrize("orders", [((1, 2),), ((1, 2), (2, 3), (3, 1))])
def test_compile_enters_real_selection_and_render_validation(orders):
    sources = timelines()
    snapshot = create_plan_snapshot(brief(), sources, 30)
    report = compile_plan_proposal(
        snapshot, validate_plan_proposal(snapshot, output(snapshot, orders))
    )
    assert len(report["plans"]) == len(orders)
    for plan in report["plans"]:
        edl = select_edit_decision(report, plan["id"])
        rendered = validate_render_plan(edl, report, sources)
        assert rendered.frames == plan["actualFrames"]
        assert [s["eventId"] for s in plan["segments"]] == [
            str(i - 1) for i in orders[int(plan["id"][-1]) - 1]
        ]


@pytest.mark.parametrize(
    "fault", ["extra", "unknown", "repeat", "duplicate", "fingerprint", "time", "evidence"]
)
def test_reject_forged_proposals(fault):
    snapshot = create_plan_snapshot(brief(), timelines(), 30)
    value = output(snapshot)
    shot = value["plans"][0]["shots"][0]
    if fault == "extra":
        value["extra"] = True
    elif fault == "unknown":
        shot["candidateId"] = "foreign"
    elif fault == "repeat":
        value["plans"][0]["shots"].append(shot.copy())
    elif fault == "duplicate":
        value["plans"].append(value["plans"][0].copy())
    elif fault == "fingerprint":
        value["snapshotFingerprint"] = "a" * 64
    elif fault == "time":
        shot["startUs"] = 0
    else:
        shot["evidenceIds"] = ["forged"]
    with pytest.raises(ValueError):
        validate_plan_proposal(snapshot, value)


def test_frozen_identity_and_brief_driven_fake_selections():
    first = create_plan_snapshot(brief(), timelines(), 30)
    second = create_plan_snapshot(replace(brief(), objective="show final fact"), timelines(), 30)
    assert first.fingerprint != second.fingerprint
    payload = first.payload
    payload["candidates"].clear()
    assert len(first.payload["candidates"]) == 3
    proposal = validate_plan_proposal(first, output(first, ((1,),)))
    with pytest.raises(ValueError, match="fingerprint"):
        compile_plan_proposal(second, proposal)
    for snapshot, order in ((first, (1,)), (second, (3,))):
        report = compile_plan_proposal(
            snapshot, validate_plan_proposal(snapshot, output(snapshot, (order,)))
        )
        assert report["plans"][0]["segments"][0]["eventId"] == str(order[0] - 1)
    assert "sourcePath" not in first.payload_json


def test_short_material_exact_gap_and_pool_distinction():
    for seconds, status in ((6, "insufficient-selection"), (20, "insufficient-candidate-pool")):
        snapshot = create_plan_snapshot(replace(brief(), target_duration=seconds), timelines(), 30)
        report = compile_plan_proposal(
            snapshot, validate_plan_proposal(snapshot, output(snapshot, ((1,),)))
        )
        plan = report["plans"][0]
        assert plan["actualFrames"] == 90
        assert plan["frameGap"] == seconds * 30 - 90
        assert plan["durationStatus"] == status
        assert plan["ready"]


def test_selected_range_preserves_original_observation_and_pipeline():
    sources = timelines()
    ranges = [{"runId": "run", "eventId": "1", "startUs": 2_000_000, "endUs": 8_000_000}]
    snapshot = create_plan_snapshot(brief(), sources, 30, ("1",), ranges)
    ranges[0]["startUs"] = 0
    report = compile_plan_proposal(
        snapshot, validate_plan_proposal(snapshot, output(snapshot, ((1,),)))
    )
    segment = report["plans"][0]["segments"][0]
    assert segment["rangeProvenance"]["analysisStartUs"] == 3_000_000
    assert segment["rangeProvenance"]["analysisEndUs"] == 6_000_000
    assert snapshot.payload["clipRanges"][0]["startUs"] == 2_000_000
    validate_render_plan(select_edit_decision(report, "dynamic-1"), report, sources)


def test_clarification_cannot_compile():
    snapshot = create_plan_snapshot(brief(), timelines(), 30)
    value = output(snapshot)
    value.update(kind="clarification", questions=["要展示哪种玩法？"], plans=[])
    proposal = validate_plan_proposal(snapshot, value)
    with pytest.raises(ValueError, match="Clarification"):
        compile_plan_proposal(snapshot, proposal)


def test_snapshot_binds_clock_selection_and_ranges():
    sources = timelines()
    first = create_plan_snapshot(brief(), sources, 30, ("0", "1"))
    assert first.fingerprint != create_plan_snapshot(brief(), sources, 25, ("0", "1")).fingerprint
    assert first.fingerprint != create_plan_snapshot(brief(), sources, 30, ("1", "0")).fingerprint
    changed = create_plan_snapshot(
        brief(),
        sources,
        30,
        ("0", "1"),
        [
            {"runId": "run", "eventId": "0", "startUs": 0, "endUs": 4_000_000},
            {"runId": "run", "eventId": "1", "startUs": 3_000_000, "endUs": 7_000_000},
        ],
    )
    assert first.fingerprint != changed.fingerprint


@pytest.mark.parametrize("additional_material", [False, True])
def test_compiled_identical_intervals_deduplicate_before_readiness(additional_material):
    from gamingcreator.domain.time import SourceRange

    original = timelines()[0]
    overlapping = tuple(
        replace(event, source_range=SourceRange(0, end, original.run.asset.duration_us))
        for event, end in zip(original.events[:2], (5_000_000, 6_000_000), strict=True)
    )
    extra = replace(original.events[2], source_range=SourceRange(6_000_000, 10_000_000, 30_000_000))
    original.events = overlapping + ((extra,) if additional_material else ())
    snapshot = create_plan_snapshot(replace(brief(), target_duration=8), (original,), 30)
    report = compile_plan_proposal(
        snapshot, validate_plan_proposal(snapshot, output(snapshot, ((1, 2),)))
    )
    plan = report["plans"][0]
    # Since 2026-11-11 overlaps are removed before the snapshot: the 0-6 s pick keeps only its
    # uncovered 5-6 s tail, so no source second repeats.
    spans = [(row["startUs"], row["endUs"]) for row in plan["segments"]]
    assert spans == [(0, 4_000_000), (5_000_000, 6_000_000)]
    assert plan["actualFrames"] == 150
    assert plan["frameGap"] == 90
    assert plan["durationStatus"] == (
        "insufficient-selection" if additional_material else "insufficient-candidate-pool"
    )
    edl = select_edit_decision(report, plan["id"])
    assert validate_render_plan(edl, report, (original,)).frames == 150
