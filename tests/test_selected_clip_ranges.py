"""User framing preserves analysed evidence through persisted plans and revisions."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_creation_planner import brief, clips
from test_creation_render import ROOT, run_tool

from gamingcreator.application.creation_editing import (
    build_revision,
    editable_clips,
    validate_revision,
)
from gamingcreator.application.creative_planner import (
    candidates,
    plan_creation,
    validate_clip_ranges,
)
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import validate_render_plan
from gamingcreator.cli.creation_render import read_creation
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer


def timeline(asset, zero=False):
    events = tuple(
        replace(
            c.event,
            media_id=asset.media_id,
            source_range=SimpleNamespace(
                start_us=i * 2_000_000 + 500_000,
                end_us=i * 2_000_000 + 500_000 + (0 if zero else 1),
                duration_us=asset.duration_us,
            ),
        )
        for i, c in enumerate(clips())
    )
    return SimpleNamespace(
        run=SimpleNamespace(run_id="run", asset=asset),
        events=events,
        evidence=tuple(SimpleNamespace(evidence_id=f"evidence{i}") for i in range(3)),
    )


def ranges():
    return [
        dict(runId="run", eventId=str(i), startUs=i * 2_000_000, endUs=(i + 1) * 2_000_000)
        for i in range(3)
    ]


@pytest.mark.parametrize("zero", [False, True])
def test_selected_ranges_saved_render_edited_render(tmp_path, zero):
    source = tmp_path / "source.mp4"
    run_tool(["-f", "lavfi", "-i", "testsrc2=s=64x48:r=10:d=6", "-c:v", "libx264", str(source)])

    async def scenario():
        context = CancellationContext("selected", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        saved = timeline(asset, zero)
        material = candidates((saved,), ("0", "1", "2"), ranges())
        assert all(c.event is saved.events[i] for i, c in enumerate(material))
        report = plan_creation(brief(), material, 10)
        for plan in report["plans"]:
            assert not any("全部可用片段合计约0.0秒" in note for note in plan["advisories"])
            assert all(
                segment["score"]["parts"]["platformFit"] == 1.0 for segment in plan["segments"]
            )
        report["brief"] = {"targetDuration": 6}
        edl = select_edit_decision(report, "chronological")
        assert len(edl["segments"]) == 3
        directory = tmp_path / "plan"
        write_creation(directory, {"plans.json": report, "edit-decision.json": edl}, ())
        loaded, plans, receipt = read_creation(directory)
        plan = validate_render_plan(loaded, plans, (saved,))
        renderer = FfmpegCreationRenderer(ROOT)
        result = await renderer.render(plan, tmp_path / "render", (source,), context, 64, 48)
        assert result["frames"] == 60
        rows = editable_clips(loaded, receipt)
        edits = [dict(clipId=r["clipId"], startUs=r["startUs"], outputFrames=10) for r in rows]
        revision = build_revision(loaded, receipt, edits)
        revised = validate_revision(loaded, plans, loaded, revision, (saved,), receipt)
        result = await renderer.render(revised, tmp_path / "revised", (source,), context, 64, 48)
        assert result["frames"] == 30
        forged = deepcopy(plans)
        next(p for p in forged["plans"] if p["id"] == "chronological")["segments"][0][
            "rangeProvenance"
        ]["analysisStartUs"] += 1
        with pytest.raises(ValueError):
            validate_render_plan(loaded, forged, (saved,))

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["bool", "duplicate", "missing", "outside", "run", "disjoint"])
def test_selected_range_rejections(fault):
    saved = timeline(clips()[0].asset)
    rows = ranges()
    if fault == "bool":
        rows[0]["startUs"] = True
    elif fault == "duplicate":
        rows[1] = rows[0]
    elif fault == "missing":
        rows.pop()
    elif fault == "outside":
        rows[0]["endUs"] = 31_000_000
    elif fault == "run":
        rows[0]["runId"] = "other"
    else:
        rows[0]["startUs"] = 600_000
    with pytest.raises(ValueError):
        candidates((saved,), ("0", "1", "2"), rows)


def test_ranges_require_explicit_event_selection():
    with pytest.raises(ValueError):
        validate_clip_ranges(ranges(), ())


def test_tail_instant_and_evidence_identity():
    saved = timeline(clips()[0].asset, True)
    event = saved.events[0]
    event = replace(
        event,
        source_range=SimpleNamespace(
            start_us=30_000_000, end_us=30_000_000, duration_us=30_000_000
        ),
    )
    saved.events = (event,)
    row = dict(runId="run", eventId="0", startUs=29_000_000, endUs=30_000_000)
    assert candidates((saved,), ("0",), [row])[0].framing.end_us == 30_000_000
    saved.evidence = ()
    with pytest.raises(ValueError, match="evidence"):
        candidates((saved,), ("0",), [row])


@pytest.mark.parametrize("zero", [False, True])
def test_cropped_context_keeps_observation_and_refuses_forged_plan_or_revision(zero):
    saved = timeline(clips()[0].asset, zero)
    saved.events = tuple(
        replace(
            event,
            source_range=SimpleNamespace(
                start_us=(i + 2) * 5_000_000,
                end_us=(i + 2) * 5_000_000 + (0 if zero else 1),
                duration_us=30_000_000,
            ),
        )
        for i, event in enumerate(saved.events)
    )
    selected = [
        {**row, "startUs": 0, "endUs": (i + 3) * 5_000_000} for i, row in enumerate(ranges())
    ]
    material = candidates((saved,), ("0", "1", "2"), selected)
    report = plan_creation(brief(), material, 10)
    report["brief"] = {"targetDuration": 6}
    plan = next(p for p in report["plans"] if p["id"] == "chronological")
    assert len(plan["segments"]) == 3 and plan["ready"]
    assert all(
        s["startUs"] <= saved.events[int(s["eventId"])].source_range.start_us < s["endUs"]
        for s in plan["segments"]
    )
    edl = select_edit_decision(report, "chronological")
    validate_render_plan(edl, report, (saved,))
    rows = editable_clips(edl, "a" * 64)
    with pytest.raises(ValueError, match="原观察"):
        build_revision(
            edl,
            "a" * 64,
            [{"clipId": rows[0]["clipId"], "startUs": rows[0]["startUs"], "outputFrames": 1}],
        )
    forged = deepcopy(report)
    bad = next(p for p in forged["plans"] if p["id"] == "chronological")["segments"][0]
    length = bad["endUs"] - bad["startUs"]
    bad["startUs"], bad["endUs"] = 0, length
    with pytest.raises(ValueError, match="intersect"):
        validate_render_plan(select_edit_decision(forged, "chronological"), forged, (saved,))
