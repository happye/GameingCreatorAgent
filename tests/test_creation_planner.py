from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.creative_planner import CreationClip, plan_creation
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.creation_files import write_creation


def brief():
    return CreativeBrief("game", "guide", ("bilibili",), 6, "objective", "new", "calm", (), ())


def clips():
    asset = MediaAsset(
        "media",
        Path("source.mp4"),
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 1), 0, 30),),
        Fraction(0),
        30_000_000,
        "probe",
    )
    return tuple(
        CreationClip(
            asset,
            SemanticEvent(
                str(i),
                "media",
                "run",
                SourceRange(i * 3_000_000, (i + 1) * 3_000_000, 30_000_000),
                (f"fact {i}",),
                (),
                (f"evidence{i}",),
                "visual",
                None,
            ),
        )
        for i in range(3)
    )


def test_three_structures_and_source_frame_clocks():
    report = plan_creation(brief(), clips(), 30)
    decisions = [
        select_edit_decision(report, name) for name in ("chronological", "hook-first", "reverse")
    ]
    orders = [tuple(s["eventId"] for s in d["segments"]) for d in decisions]
    assert len(set(orders)) == 3
    for decision in decisions:
        segments = decision["segments"]
        assert sum(s["outputFrames"] for s in segments) <= 180
        assert all(s["sourceSha256"] == "a" * 64 for s in segments)
        assert segments[0]["outputStartFrame"] == 0
        assert all(s["endUs"] <= s["sourceDurationUs"] for s in segments)


def test_missing_material_and_topics_are_not_ready():
    for material, request in (
        (clips()[:1], brief()),
        (clips(), replace(brief(), mandatory_topics=("unseen",))),
    ):
        report = plan_creation(request, material, 30)
        with pytest.raises(ValueError, match="gaps"):
            select_edit_decision(report, "chronological")


def test_excluded_facts_are_removed():
    report = plan_creation(replace(brief(), exclude=("fact",)), clips(), 30)
    assert report["plans"][0]["segments"] == []


def test_exclusive_publish_and_re_read(tmp_path):
    output = tmp_path / "version1"
    write_creation(output, {"plans.json": {"value": 1}}, ())
    before = (output / "plans.json").read_bytes()
    with pytest.raises(FileExistsError):
        write_creation(output, {"plans.json": {"value": 2}}, ())
    assert (output / "plans.json").read_bytes() == before
    assert (output / "receipt.json").is_file()
    with pytest.raises(ValueError):
        write_creation(output / "nested", {}, (tmp_path,))


def test_brief_rejects_unknown_fields_and_bool_duration():
    with pytest.raises(ValueError):
        CreativeBrief.from_json({"extra": 1})


@pytest.mark.parametrize("fps", [0, True, 121])
def test_invalid_output_clock(fps):
    with pytest.raises(ValueError):
        plan_creation(brief(), clips(), fps)


@pytest.mark.parametrize("fault", ["run", "media", "duration", "evidence", "duplicate", "unknown"])
def test_source_identity_and_unknown_events_rejected(fault):
    from types import SimpleNamespace

    from gamingcreator.application.creative_planner import candidates

    clip = clips()[0]
    event = clip.event
    selected = ()
    if fault == "run":
        event = replace(event, run_id="foreign")
    elif fault == "media":
        event = replace(event, media_id="foreign")
    elif fault == "duration":
        event = replace(event, source_range=SourceRange(0, 31_000_000, 32_000_000))
    elif fault == "evidence":
        event = replace(event, evidence_ids=("unknown",))
    elif fault == "unknown":
        selected = ("unknown",)
    else:
        selected = (event.event_id, event.event_id)
    timeline = SimpleNamespace(
        run=SimpleNamespace(asset=clip.asset, run_id="run"),
        events=(event,),
        evidence=(SimpleNamespace(evidence_id="evidence0"),),
    )
    with pytest.raises(ValueError):
        candidates((timeline,), selected)


def test_receipt_hashes_exact_documents(tmp_path):
    import hashlib
    import json

    output = tmp_path / "version"
    write_creation(output, {"plans.json": {"text": "中文"}}, ())
    receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
    assert (
        receipt["files"]["plans.json"]
        == hashlib.sha256((output / "plans.json").read_bytes()).hexdigest()
    )


def test_same_source_interval_across_run_versions_is_one_shot():
    clip = clips()[0]
    versions = tuple(
        replace(clip, event=replace(clip.event, run_id=f"run{i}", event_id=f"event{i}"))
        for i in range(3)
    )
    report = plan_creation(brief(), versions, 30)
    for plan in report["plans"]:
        assert len(plan["segments"]) == 1
        assert plan["gaps"]
        with pytest.raises(ValueError, match="gaps"):
            select_edit_decision(report, plan["id"])


def test_chronological_sorts_source_time_despite_reverse_event_selection():
    from types import SimpleNamespace

    from gamingcreator.application.creative_planner import candidates

    material = clips()
    # First input run is source B, deliberately reverse selected event IDs.
    first = tuple(replace(clip, asset=replace(clip.asset, sha256="b" * 64)) for clip in material)
    second = tuple(
        replace(clip, event=replace(clip.event, event_id=f"second{i}", run_id="second"))
        for i, clip in enumerate(material)
    )
    timelines = tuple(
        SimpleNamespace(
            run=SimpleNamespace(asset=group[0].asset, run_id=group[0].event.run_id),
            events=tuple(clip.event for clip in group),
            evidence=tuple(SimpleNamespace(evidence_id=f"evidence{i}") for i in range(3)),
        )
        for group in (first, second)
    )
    selected = tuple(clip.event.event_id for clip in reversed(first + second))
    report = plan_creation(brief(), candidates(timelines, selected), 30)
    segments = select_edit_decision(report, "chronological")["segments"]
    assert [segment["sourceSha256"] for segment in segments] == ["b" * 64] * 3 + ["a" * 64] * 3
    assert [segment["startUs"] for segment in segments] == [0, 3_000_000, 6_000_000] * 2


def test_subframe_candidate_cannot_collapse_ready_template_orders():
    material = clips()
    tiny = replace(
        material[0],
        event=replace(
            material[0].event,
            event_id="tiny",
            source_range=SourceRange(10_000_000, 10_000_001, 30_000_000),
        ),
    )
    report = plan_creation(brief(), material + (tiny,), 30)
    decisions = [
        select_edit_decision(report, name) for name in ("chronological", "hook-first", "reverse")
    ]
    orders = [
        tuple(segment["eventId"] for segment in decision["segments"]) for decision in decisions
    ]
    assert len(set(orders)) == 3
    assert all("tiny" not in order for order in orders)
