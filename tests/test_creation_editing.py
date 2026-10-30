"""Editing snapshots preserve root source identity and frame clocks."""

from copy import deepcopy

import pytest
from test_creation_render import decision

from gamingcreator.application.creation_editing import (
    build_revision,
    editable_clips,
    validate_revision,
)

SHA = "b" * 64


def edit(row, frames=1, shift=0):
    return {"clipId": row["clipId"], "startUs": row["startUs"] + shift, "outputFrames": frames}


def test_trim_reorder_delete_and_ancestor_restore_without_mutation():
    root, report, timelines = decision()
    before = deepcopy(root)
    rows = editable_clips(root, SHA)
    first = build_revision(root, SHA, [edit(rows[-1], 7, 50_000), edit(rows[0], 2)])
    plan = validate_revision(root, report, root, first, timelines, SHA)
    assert plan.frames == 9
    assert [c.source_range.start_us for c in plan.clips] == [
        rows[-1]["startUs"] + 50_000,
        rows[0]["startUs"],
    ]
    assert first["segments"][1]["outputStartFrame"] == 7
    assert plan.clips[0].asset is timelines[0].run.asset
    second = build_revision(first, SHA, [edit(first["segments"][1])])
    assert validate_revision(root, report, first, second, timelines, SHA).frames == 1
    restored = build_revision(root, SHA, [edit(r, r["outputFrames"]) for r in rows])
    assert validate_revision(root, report, root, restored, timelines, SHA).frames > 9
    assert root == before
    assert editable_clips(first, SHA)[0]["clipId"] == rows[-1]["clipId"]
    with pytest.raises(ValueError):
        build_revision(second, SHA, [edit(rows[-1])])


@pytest.mark.parametrize("fps", [3, 30])
def test_fractional_frame_duration_has_no_accumulated_rounding(fps):
    root, report, timelines = decision()
    root["fpsNumerator"] = report["fps"] = fps
    offset = 0
    for row in root["segments"]:
        row["outputFrames"] = fps
        row["endUs"] = row["startUs"] + 1_000_000
        row["outputStartFrame"] = offset
        offset += fps
    rows = editable_clips(root, SHA)
    revision = build_revision(root, SHA, [edit(r) for r in rows])
    plan = validate_revision(root, report, root, revision, timelines, SHA)
    assert plan.frames == len(rows)
    assert [r["outputStartFrame"] for r in revision["segments"]] == list(range(len(rows)))
    assert all(
        c.source_range.end_us - c.source_range.start_us == (1_000_000 + fps - 1) // fps
        for c in plan.clips
    )


@pytest.mark.parametrize(
    "fault", ["empty", "duplicate", "unknown", "bool", "float", "zero", "outside", "extra", "long"]
)
def test_reject_invalid_edit_requests(fault):
    root, _, _ = decision()
    row = editable_clips(root, SHA)[0]
    request = edit(row)
    requests = [request]
    if fault == "empty":
        requests = []
    elif fault == "duplicate":
        requests *= 2
    elif fault == "unknown":
        request["clipId"] = "unknown"
    elif fault == "bool":
        request["startUs"] = True
    elif fault == "float":
        request["outputFrames"] = 1.0
    elif fault == "zero":
        request["outputFrames"] = 0
    elif fault == "outside":
        request["startUs"] = row["startUs"] - 1
    elif fault == "long":
        request["outputFrames"] = row["outputFrames"] + 1
    else:
        request["sourcePath"] = "foreign"
    with pytest.raises(ValueError):
        build_revision(root, SHA, requests)


@pytest.mark.parametrize("target", ["parent", "revision"])
@pytest.mark.parametrize(
    "field",
    [
        "sourcePath",
        "eventId",
        "sourceSha256",
        "evidenceIds",
        "clipId",
        "startUs",
        "endUs",
        "outputStartFrame",
        "fpsNumerator",
        "scriptStatus",
    ],
)
def test_reject_forged_parent_and_revision(target, field):
    root, report, timelines = decision()
    rows = editable_clips(root, SHA)
    parent = build_revision(root, SHA, [edit(r, 2) for r in rows])
    revision = build_revision(parent, SHA, [edit(parent["segments"][0])])
    document = parent if target == "parent" else revision
    if field in ("fpsNumerator", "scriptStatus"):
        document[field] = "forged"
    else:
        row = document["segments"][0]
        row[field] = (
            float(row[field]) if field in ("startUs", "endUs", "outputStartFrame") else "forged"
        )
    with pytest.raises(ValueError):
        validate_revision(root, report, parent, revision, timelines, SHA)


def test_root_validation_and_receipt_identity_still_required():
    root, report, timelines = decision()
    revision = build_revision(root, SHA, [edit(editable_clips(root, SHA)[0])])
    with pytest.raises(ValueError):
        validate_revision(root, report, root, revision, timelines, "c" * 64)
    report["plans"][0]["ready"] = False
    report["plans"][1]["ready"] = False
    report["plans"][2]["ready"] = False
    with pytest.raises(ValueError):
        validate_revision(root, report, root, revision, timelines, SHA)
