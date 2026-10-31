"""Exact transition layout, source protection and persisted revision behavior."""

import json
from copy import deepcopy
from fractions import Fraction

import pytest
from test_creation_editing import SHA, edit
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_render import decision
from test_creation_revision_jobs import payload, revisions  # noqa: F401

from gamingcreator.application.creation_editing import (
    build_revision,
    editable_clips,
    validate_revision,
)
from gamingcreator.application.rendering import output_start_frames, validate_render_plan
from gamingcreator.domain.errors import AppError
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.revision_jobs import load_chain


def transition_edit(row, overlap=0, speed=(1, 1)):
    return {
        "clipId": row["clipId"],
        "startUs": row["startUs"],
        "endUs": row["startUs"] + 1_000_000,
        "speed": {"numerator": speed[0], "denominator": speed[1]},
        "transitionIn": {"type": "crossfade" if overlap else "cut", "frames": overlap},
    }


def test_two_clips_share_exact_overlap_layout():
    root, report, timelines = decision()
    rows = editable_clips(root, SHA)
    revision = build_revision(root, SHA, [transition_edit(rows[0]), transition_edit(rows[1], 6)])
    plan = validate_revision(root, report, root, revision, timelines, SHA)
    assert revision["schemaVersion"] == "edit-decision-revision-v3"
    assert plan.frames == 54
    assert plan.start_frames == (0, 24)
    assert plan.transition_frames == (0, 6)
    assert [r["outputStartFrame"] for r in revision["segments"]] == [0, 24]
    assert [c.output_frames for c in plan.clips] == [30, 30]
    # Root validation must still reject revision schemas and overlapping root clocks.
    with pytest.raises(ValueError):
        validate_render_plan(revision, report, timelines)
    root["segments"][1]["outputStartFrame"] -= 6
    with pytest.raises(ValueError):
        validate_render_plan(root, report, timelines)


def test_three_clips_mixed_speeds_use_output_clock_for_overlap():
    root, report, timelines = decision()
    rows = editable_clips(root, SHA)
    revision = build_revision(
        root,
        SHA,
        [
            transition_edit(rows[0], speed=(1, 2)),
            transition_edit(rows[1], 6, (2, 1)),
            transition_edit(rows[2], 5),
        ],
    )
    plan = validate_revision(root, report, root, revision, timelines, SHA)
    assert [c.output_frames for c in plan.clips] == [60, 15, 30]
    assert [c.speed for c in plan.clips] == [Fraction(1, 2), Fraction(2), Fraction(1)]
    assert plan.start_frames == (0, 54, 64)
    assert plan.frames == 94


@pytest.mark.parametrize(
    "transition",
    [
        True,
        {},
        {"type": "cut", "frames": False},
        {"type": "cut", "frames": 0.0},
        {"type": "cut", "frames": 1},
        {"type": "crossfade", "frames": 0},
        {"type": "crossfade", "frames": -1},
        {"type": "crossfade", "frames": True},
        {"type": "fade", "frames": 6},
        {"type": "cut", "frames": 0, "extra": 1},
    ],
)
def test_transition_requires_exact_json(transition):
    root, _, _ = decision()
    requests = [transition_edit(r) for r in editable_clips(root, SHA)[:2]]
    requests[1]["transitionIn"] = transition
    with pytest.raises(ValueError):
        build_revision(root, SHA, requests)


@pytest.mark.parametrize("overlaps", [(1, 0, 0), (0, 30, 0), (0, 16, 14), (0, 31, 0)])
def test_first_fade_excessive_and_triple_overlap_rejected(overlaps):
    root, _, _ = decision()
    with pytest.raises(ValueError):
        build_revision(
            root,
            SHA,
            [
                transition_edit(r, t)
                for r, t in zip(editable_clips(root, SHA), overlaps, strict=True)
            ],
        )
    assert output_start_frames((30, 30, 30), (0, 16, 13)) == (0, 14, 31)


@pytest.mark.parametrize("target", ["parent", "child"])
@pytest.mark.parametrize(
    "field", ["sourcePath", "sourceSha256", "outputStartFrame", "startUs", "speed", "transitionIn"]
)
def test_v3_forged_source_clock_and_transition_rejected(target, field):
    root, report, timelines = decision()
    parent = build_revision(
        root,
        SHA,
        [transition_edit(r, 6 if i else 0) for i, r in enumerate(editable_clips(root, SHA)[:2])],
    )
    child = build_revision(
        parent, SHA, [transition_edit(r, 6 if i else 0) for i, r in enumerate(parent["segments"])]
    )
    row = (parent if target == "parent" else child)["segments"][1]
    row[field] = True if field == "outputStartFrame" else "forged"
    with pytest.raises(ValueError):
        validate_revision(root, report, parent, child, timelines, SHA)


def test_legacy_bytes_unchanged_subset_reorder_and_ancestor_restore(tmp_path):
    root, report, timelines = decision()
    old = build_revision(root, SHA, [edit(r, 30) for r in editable_clips(root, SHA)])
    v2 = build_revision(
        old,
        SHA,
        [
            {k: v for k, v in transition_edit(r).items() if k != "transitionIn"}
            for r in old["segments"]
        ],
    )
    paths = []
    for i, document in enumerate((root, old, v2)):
        path = tmp_path / f"legacy-{i}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append((path, path.read_bytes()))
    parent = build_revision(
        v2, SHA, [transition_edit(r, 6 if i else 0) for i, r in enumerate(v2["segments"])]
    )
    validate_revision(root, report, v2, parent, timelines, SHA)
    child = build_revision(
        parent,
        SHA,
        [transition_edit(parent["segments"][2]), transition_edit(parent["segments"][0], 4)],
    )
    plan = validate_revision(root, report, parent, child, timelines, SHA)
    assert plan.start_frames == (0, 26)
    assert plan.frames == 56
    with pytest.raises(ValueError):
        build_revision(child, SHA, [transition_edit(parent["segments"][1])])
    restored = build_revision(
        v2, SHA, [transition_edit(r, 6 if i else 0) for i, r in enumerate(v2["segments"])]
    )
    assert restored == parent
    assert all(path.read_bytes() == before for path, before in paths)
    assert all("transitionIn" not in r for r in v2["segments"])
    assert validate_revision(root, report, old, v2, timelines, SHA).start_frames == (0, 30, 60)


def v3_payload(jobs, parent, token):
    request = payload(jobs, parent, token)
    rows = jobs.edit(parent, "hook-first")["clips"]
    request["clips"] = [transition_edit(r, 6 if i else 0) for i, r in enumerate(rows[:2])]
    return request


def test_persistent_v3_chain_inherits_subtitles_audio_and_restores_ancestor(revisions):  # noqa: F811
    jobs, root, _ = revisions
    original = {p: p.read_bytes() for p in jobs.directory(root).rglob("*") if p.is_file()}
    request = v3_payload(jobs, root, "b")
    request["subtitleOverrides"] = [
        {"clipId": r["clipId"], "text": f"caption {i}"} for i, r in enumerate(request["clips"])
    ]
    request["audioMix"] = {"sourceGainDb": -6.0, "bgm": None, "ducking": "source-v1"}
    parent = jobs.submit("revision", request)["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    child_request = v3_payload(jobs, parent, "c")
    child_request["clips"] = [transition_edit(jobs.edit(parent, "hook-first")["clips"][1])]
    child = jobs.submit("revision", child_request)["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    restarted = CreationJobs(jobs.repository)
    chain = load_chain(restarted, child, "hook-first")
    assert chain.plan.frames == 30
    assert chain.subtitle_overrides == request["subtitleOverrides"][1:]
    assert chain.audio_mix.to_json() == request["audioMix"]
    assert len(chain.ancestry) == 2
    assert not restarted.threads
    restore = restarted.submit("revision", v3_payload(restarted, root, "d"))["jobId"]
    assert finish(restarted, restore)["status"] == "completed"
    assert load_chain(restarted, restore, "hook-first").plan.frames == 54
    assert all(path.read_bytes() == data for path, data in original.items())


@pytest.mark.parametrize("target", ["request", "edl", "ancestor"])
def test_persistent_v3_tampered_chain_rejected(revisions, target):  # noqa: F811
    jobs, root, _ = revisions
    parent = jobs.submit("revision", v3_payload(jobs, root, "b"))["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    child = jobs.submit("revision", v3_payload(jobs, parent, "c"))["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    path = jobs.directory(parent if target == "ancestor" else child) / (
        "request.json" if target == "request" else "result/edit-decision.json"
    )
    if target == "request":
        stored = deepcopy(jobs.read(path))
        stored["request"]["clips"][1]["transitionIn"]["frames"] = 5
        jobs.save(path, stored)
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((ValueError, AppError)):
        load_chain(jobs, child, "hook-first")
