"""D01: content signatures identify final renderable segments, not names or IDs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from test_creation_planner import brief, clips

from gamingcreator.application.creative_planner import (
    plan_content_signature,
    plan_creation,
    segment_content_key,
)


def _row(run="run", sha="a" * 64, start=0, end=1_000_000, frames=30, **extra):
    row = {
        "runId": run,
        "eventId": extra.pop("eventId", "event-1"),
        "mediaId": extra.pop("mediaId", "media"),
        "sourceSha256": sha,
        "sourcePath": extra.pop("sourcePath", "A/source.mp4"),
        "startUs": start,
        "endUs": end,
        "outputFrames": frames,
        "outputStartFrame": extra.pop("outputStartFrame", 0),
        "scriptDraft": extra.pop("scriptDraft", "旁白"),
    }
    row.update(extra)
    return row


def test_signature_uses_run_source_range_frames_and_order_only():
    base = [_row(), _row(start=1_000_000, end=2_000_000, frames=15, outputStartFrame=30)]
    same = [
        _row(eventId="other", mediaId="x", sourcePath="B/renamed.mov", scriptDraft="不同说明"),
        _row(
            start=1_000_000,
            end=2_000_000,
            frames=15,
            outputStartFrame=99,
            eventId="other-2",
            sourcePath="C/also-renamed.mp4",
        ),
    ]
    assert plan_content_signature(base) == plan_content_signature(same)
    assert plan_content_signature(base) != plan_content_signature(list(reversed(base)))
    assert plan_content_signature(base) != plan_content_signature([_row(run="run-2"), base[1]])
    assert plan_content_signature(base) != plan_content_signature([_row(sha="b" * 64), base[1]])
    assert plan_content_signature(base) != plan_content_signature(
        [_row(start=10, end=1_000_000, frames=30), base[1]]
    )
    assert plan_content_signature(base) != plan_content_signature([_row(frames=29), base[1]])
    assert segment_content_key(base[0]) == ("run", "a" * 64, 0, 1_000_000, 30)
    assert "source.mp4" not in plan_content_signature(base)
    assert "event-1" not in plan_content_signature(base)
    assert "chronological" not in plan_content_signature(base)


def test_new_rule_plans_carry_content_signatures_without_using_template_ids():
    report = plan_creation(brief(), clips(), 30)
    signatures = []
    for plan in report["plans"]:
        assert plan["contentSignature"] == plan_content_signature(plan["segments"])
        signatures.append(plan["contentSignature"])
        assert plan["contentSignature"] != plan["id"]
        assert plan["structure"] not in plan["contentSignature"]
        for segment in plan["segments"]:
            assert Path(segment["sourcePath"]).name not in plan["contentSignature"]
    # Same final segments share a signature even when template ids differ.
    by_id = {plan["id"]: plan["contentSignature"] for plan in report["plans"]}
    groups = {}
    for plan in report["plans"]:
        key = tuple(segment_content_key(row) for row in plan["segments"])
        groups.setdefault(key, set()).add(plan["contentSignature"])
    assert all(len(sigs) == 1 for sigs in groups.values())
    generic = [name for name in ("chronological", "hook-first", "reverse") if name in by_id]
    assert "hook-first" in generic and "reverse" in generic
    assert len({by_id[name] for name in generic}) == len(generic)

    # Renaming the source file does not invent a new plan identity.
    renamed = tuple(
        replace(clip, asset=replace(clip.asset, source_path=Path("renamed.mov")))
        for clip in clips()
    )
    renamed_report = plan_creation(brief(), renamed, 30)
    renamed_by_id = {plan["id"]: plan["contentSignature"] for plan in renamed_report["plans"]}
    assert renamed_by_id == by_id
