"""Replacement source identity and independent version behavior."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_creation_editing import SHA
from test_creation_render import decision

from gamingcreator.application.creation_editing import build_revision, editable_clips
from gamingcreator.application.creation_replacements import (
    build_candidate_manifest,
    build_revision_v4,
    candidate_manifest_sha,
    timeline_fingerprint,
    validate_revision_v4,
)
from gamingcreator.domain.models import EvidenceReference, TranscriptSegment
from gamingcreator.domain.time import SourceInstant, SourceRange

PARENT = "c" * 64


@pytest.fixture
def material():
    root, _, timelines = decision()
    a = timelines[0]
    a.run.status = "completed"
    a.run.config_hash = "configuration"
    a.run.configuration = SimpleNamespace(pipeline_version="v1", pipeline_hash="pipeline")
    a.evidence = tuple(
        EvidenceReference(
            e.evidence_ids[0],
            a.run.asset.media_id,
            "image",
            SourceInstant(e.source_range.start_us, a.run.asset.duration_us),
            Path(f"{i}.png"),
            "d" * 64,
            "v1",
        )
        for i, e in enumerate(a.events)
    )
    a.transcripts = ()
    asset = replace(a.run.asset, media_id="B", sha256="e" * 64, source_path=Path("B.mp4"))
    b = SimpleNamespace(
        run=SimpleNamespace(**{**a.run.__dict__, "run_id": "B", "asset": asset}),
        events=tuple(replace(e, run_id="B", media_id="B") for e in a.events),
        evidence=tuple(replace(e, media_id="B") for e in a.evidence),
        transcripts=(),
    )
    manifest = build_candidate_manifest(SHA, "project", ["run", "B"], (a, b))
    rows = editable_clips(root, SHA)
    edits = [
        {
            "clipId": r["clipId"],
            "startUs": r["startUs"],
            "endUs": r["startUs"] + 1_000_000,
            "speed": {"numerator": 1, "denominator": 1},
            "transitionIn": {"type": "cut", "frames": 0},
        }
        for r in rows
    ]
    candidate = next(c for c in manifest["candidates"] if c["runId"] == "B")
    edits[1].update(startUs=candidate["startUs"], endUs=candidate["startUs"] + 1_000_000)
    operations = [{"targetClipId": edits[1]["clipId"], "candidateId": candidate["candidateId"]}]
    return root, (a, b), manifest, edits, operations


def build(material):
    root, timelines, manifest, edits, operations = material
    revision = build_revision_v4(root, SHA, PARENT, edits, operations, manifest)
    plan = validate_revision_v4(root, revision, SHA, PARENT, edits, operations, manifest, timelines)
    return revision, plan


def test_cross_run_replacement_new_identity_and_descendants(material):
    root, timelines, manifest, edits, operations = material
    before = deepcopy(root)
    revision, plan = build(material)
    row = revision["segments"][1]
    assert row["runId"] == "B" and plan.clips[1].asset is timelines[1].run.asset
    assert row["clipId"] != edits[1]["clipId"]
    assert row["replacesClipId"] == edits[1]["clipId"]
    assert revision["replacements"][0]["newClipId"] == row["clipId"]
    assert edits[1]["clipId"] not in {r["clipId"] for r in revision["segments"]}
    assert revision == build_revision_v4(root, SHA, PARENT, edits, operations, manifest)
    child_edits = [{k: deepcopy(r[k]) for k in edits[0]} for r in revision["segments"]]
    child_edits[1]["endUs"] -= 200_000
    child_edits[1]["speed"] = {"numerator": 1, "denominator": 2}
    child_edits[1]["transitionIn"] = {"type": "crossfade", "frames": 6}
    child = build_revision_v4(revision, SHA, "f" * 64, child_edits, [], manifest)
    child_plan = validate_revision_v4(
        revision, child, SHA, "f" * 64, child_edits, [], manifest, timelines
    )
    assert child["schemaVersion"] == "edit-decision-revision-v4"
    assert child_plan.start_frames == (0, 24, 72)
    assert child_plan.frames == 102
    assert root == before
    assert build(material)[0] == revision


def test_fingerprints_sort_ids_exclude_accounting_preserve_transcript_duplicates(material):
    _, (a, b), manifest, _, _ = material
    changed = deepcopy(a)
    changed.events = tuple(reversed(changed.events))
    changed.evidence = tuple(reversed(changed.evidence))
    changed.invocations = ("irrelevant cost",)
    assert timeline_fingerprint(changed) == timeline_fingerprint(a)
    assert build_candidate_manifest(SHA, "project", ["B", "run"], (b, a)) == manifest
    changed.events += changed.events[:1]
    with pytest.raises(ValueError):
        timeline_fingerprint(changed)


@pytest.mark.parametrize(
    "fault", ["sha", "path", "event", "evidence", "root", "fingerprint", "status"]
)
def test_manifest_and_timeline_tampering_rejected(material, fault):
    root, timelines, manifest, edits, operations = material
    revision, _ = build(material)
    if fault == "root":
        manifest["rootReceiptSha256"] = "0" * 64
    elif fault == "fingerprint":
        manifest["runFingerprints"]["B"] = "0" * 64
    elif fault == "status":
        timelines[1].run.status = "failed"
    else:
        candidate = next(c for c in manifest["candidates"] if c["runId"] == "B")
        candidate[
            {
                "sha": "sourceSha256",
                "path": "sourcePath",
                "event": "eventId",
                "evidence": "evidenceIds",
            }[fault]
        ] = "forged"
    with pytest.raises(ValueError):
        validate_revision_v4(root, revision, SHA, PARENT, edits, operations, manifest, timelines)


@pytest.mark.parametrize(
    "fault",
    [
        "parent_sha",
        "root_sha",
        "output",
        "identity",
        "source",
        "speed",
        "duplicate_target",
        "unknown_target",
        "outside",
        "bool",
    ],
)
def test_replacement_forgery_rejected(material, fault):
    root, timelines, manifest, edits, operations = material
    revision, _ = build(material)
    parent_sha, root_sha = PARENT, SHA
    if fault == "parent_sha":
        parent_sha = "1" * 64
    elif fault == "root_sha":
        root_sha = "1" * 64
    elif fault in ("output", "identity", "source"):
        revision["segments"][1][
            {"output": "outputStartFrame", "identity": "clipId", "source": "sourcePath"}[fault]
        ] = "forged"
    elif fault == "speed":
        edits[1]["speed"]["numerator"] = 2
    elif fault == "duplicate_target":
        operations *= 2
    elif fault == "unknown_target":
        operations[0]["targetClipId"] = "unknown"
    elif fault == "outside":
        edits[1]["startUs"] -= 1
    else:
        edits[1]["startUs"] = False
    with pytest.raises(ValueError):
        validate_revision_v4(
            root, revision, root_sha, parent_sha, edits, operations, manifest, timelines
        )


def test_replacement_resets_both_connections_and_rejects_duplicate_interval(material):
    root, _, manifest, edits, operations = material
    edits[1]["transitionIn"] = edits[2]["transitionIn"] = {"type": "crossfade", "frames": 6}
    revision, _ = build(material)
    assert all(r["transitionIn"] == {"type": "cut", "frames": 0} for r in revision["segments"])
    same = next(
        c
        for c in manifest["candidates"]
        if c["runId"] == "run" and c["eventId"] == root["segments"][0]["eventId"]
    )
    operations[0]["candidateId"] = same["candidateId"]
    edits[1].update(startUs=edits[0]["startUs"], endUs=edits[0]["endUs"])
    with pytest.raises(ValueError, match="Duplicate"):
        build_revision_v4(root, SHA, PARENT, edits, operations, manifest)


def test_manifest_sha_is_canonical_content(material):
    manifest = material[2]
    assert candidate_manifest_sha(manifest) == candidate_manifest_sha(
        dict(reversed(list(manifest.items())))
    )


@pytest.mark.parametrize("fault", ["event", "evidence", "asset", "config"])
def test_actual_completed_content_changes_invalidate_saved_manifest(material, fault):
    root, timelines, manifest, edits, operations = material
    revision, _ = build(material)
    b = timelines[1]
    if fault == "event":
        b.events = (replace(b.events[0], observable_facts=("changed",)), *b.events[1:])
    elif fault == "evidence":
        b.evidence = (replace(b.evidence[0], sha256="0" * 64), *b.evidence[1:])
    elif fault == "asset":
        b.run.asset = replace(b.run.asset, sha256="0" * 64)
    else:
        b.run.config_hash = "changed"
    with pytest.raises(ValueError):
        validate_revision_v4(root, revision, SHA, PARENT, edits, operations, manifest, timelines)


def test_descendants_keep_manifest_and_parent_source_limits(material):
    revision, _ = build(material)
    manifest = material[2]
    edits = [{k: deepcopy(r[k]) for k in material[3][0]} for r in revision["segments"]]
    edits[0]["endUs"] += 1
    with pytest.raises(ValueError, match="shorten"):
        build_revision_v4(revision, SHA, PARENT, edits, [], manifest)
    edits[0]["endUs"] -= 1
    changed_manifest = deepcopy(manifest)
    changed_manifest["projectId"] = "other"
    with pytest.raises(ValueError, match="retain"):
        build_revision_v4(revision, SHA, PARENT, edits, [], changed_manifest)
    with pytest.raises(ValueError):
        build_revision(revision, SHA, edits)


def test_transcript_sorting_retains_duplicate_observations(material):
    a = material[1][0]
    one = TranscriptSegment(
        a.run.asset.media_id, SourceRange(0, 100_000, a.run.asset.duration_us), "一"
    )
    two = replace(one, text="二", uncertainty="uncertain")
    a.transcripts = (one, two)
    fingerprint = timeline_fingerprint(a)
    a.transcripts = (two, one)
    assert timeline_fingerprint(a) == fingerprint
    a.transcripts = (one, two, one)
    assert timeline_fingerprint(a) != fingerprint
