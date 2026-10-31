"""Speed revisions preserve source bounds independently from output frame counts."""

import json
from copy import deepcopy
from fractions import Fraction

import pytest
from test_creation_editing import SHA, edit
from test_creation_render import decision

from gamingcreator.application.creation_editing import (
    build_revision,
    editable_clips,
    validate_revision,
)
from gamingcreator.application.rendering import RenderClip


def speed_edit(row, numerator=1, denominator=2):
    return {
        "clipId": row["clipId"],
        "startUs": row["startUs"],
        "endUs": row["endUs"],
        "speed": {"numerator": numerator, "denominator": denominator},
    }


def test_v1_v2_chain_and_ancestor_restore_preserve_root_bytes():
    root, report, timelines = decision()
    before = json.dumps(root)
    old = build_revision(root, SHA, [edit(r, r["outputFrames"]) for r in editable_clips(root, SHA)])
    old_bytes = json.dumps(old)
    slow = build_revision(old, SHA, [speed_edit(r) for r in old["segments"]])
    plan = validate_revision(root, report, old, slow, timelines, SHA)
    assert plan.frames > report["brief"]["targetDuration"] * plan.fps
    assert all(c.speed == Fraction(1, 2) for c in plan.clips)
    assert [(r["startUs"], r["endUs"]) for r in slow["segments"]] == [
        (r["startUs"], r["endUs"]) for r in old["segments"]
    ]
    fast = build_revision(slow, SHA, [speed_edit(r, 2, 1) for r in slow["segments"]])
    assert validate_revision(root, report, slow, fast, timelines, SHA).frames < plan.frames
    restored = build_revision(old, SHA, [speed_edit(r) for r in old["segments"]])
    assert restored == slow
    assert json.dumps(root) == before
    assert json.dumps(old) == old_bytes
    with pytest.raises(ValueError, match="requires v2"):
        build_revision(slow, SHA, [edit(slow["segments"][0])])


@pytest.mark.parametrize(
    "speed",
    [
        True,
        1,
        0.5,
        {},
        {"numerator": True, "denominator": 2},
        {"numerator": 1.0, "denominator": 2},
        {"numerator": 2, "denominator": 4},
        {"numerator": 1, "denominator": 0},
        {"numerator": 1, "denominator": 2, "extra": 0},
    ],
)
def test_strict_speed_json(speed):
    root, _, _ = decision()
    request = speed_edit(editable_clips(root, SHA)[0])
    request["speed"] = speed
    with pytest.raises(ValueError):
        build_revision(root, SHA, [request])


@pytest.mark.parametrize("speed", [1, 1.0, True, Fraction(3), Fraction(2, 3)])
def test_render_clip_rejects_noncanonical_fraction(speed):
    _, _, timelines = decision()
    asset = timelines[0].run.asset
    with pytest.raises(ValueError, match="Fraction"):
        RenderClip(asset, timelines[0].events[0].source_range, 1, speed)


@pytest.mark.parametrize("fault", ["mixed", "extra", "bool", "float", "outside", "empty_frame"])
def test_v2_rejects_invalid_edits(fault):
    root, _, _ = decision()
    row = editable_clips(root, SHA)[0]
    request = speed_edit(row)
    requests = [request]
    if fault == "mixed":
        requests.append(edit(row))
    elif fault == "extra":
        request["outputFrames"] = 2
    elif fault == "outside":
        request["endUs"] += 1
    elif fault == "empty_frame":
        request["endUs"] = request["startUs"] + 1
    else:
        request["endUs"] = True if fault == "bool" else float(row["endUs"])
    with pytest.raises(ValueError):
        build_revision(root, SHA, requests)


@pytest.mark.parametrize("target", ["parent", "child"])
@pytest.mark.parametrize(
    "field", ["speed", "outputFrames", "outputStartFrame", "sourceSha256", "endUs", "extra"]
)
def test_v2_forgery_rejected(target, field):
    root, report, timelines = decision()
    parent = build_revision(root, SHA, [speed_edit(editable_clips(root, SHA)[0])])
    child = build_revision(parent, SHA, [speed_edit(parent["segments"][0], 2, 1)])
    row = (parent if target == "parent" else child)["segments"][0]
    row[field] = {"numerator": 2, "denominator": 4} if field == "speed" else "forged"
    with pytest.raises(ValueError):
        validate_revision(root, report, parent, child, timelines, SHA)


def test_29fps_tail_floor_and_integer_offsets():
    root, report, timelines = decision()
    root["fpsNumerator"] = report["fps"] = 29
    offset = 0
    for row in root["segments"]:
        row.update(outputFrames=29, endUs=row["startUs"] + 1_000_000, outputStartFrame=offset)
        offset += 29
    edits = [speed_edit(r, 2, 1) for r in editable_clips(root, SHA)]
    for request in edits:
        request["endUs"] -= 123
    revision = build_revision(root, SHA, edits)
    plan = validate_revision(root, report, root, revision, timelines, SHA)
    assert [r["outputStartFrame"] for r in revision["segments"]] == [
        14 * i for i in range(len(edits))
    ]
    for clip in plan.clips:
        assert clip.output_frames == 14
        duration = (
            Fraction(clip.source_range.end_us - clip.source_range.start_us, 1_000_000) / clip.speed
        )
        assert 0 <= duration - Fraction(clip.output_frames, 29) < Fraction(1, 29)
    wider = deepcopy(edits[0])
    wider["endUs"] += 124
    with pytest.raises(ValueError):
        build_revision(revision, SHA, [wider])
