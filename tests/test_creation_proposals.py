from copy import deepcopy

import pytest
from test_creation_render import decision

from gamingcreator.application.creation_editing import validate_revision
from gamingcreator.application.creation_proposals import (
    clip_rows,
    create_snapshot,
    revision_for_application,
    validate_proposal,
)

SHA = "b" * 64


def fixture():
    root, report, timelines = decision()
    snapshot = create_snapshot("job", "plan", "a" * 64, SHA, root)
    return snapshot, root, report, timelines


def output(snapshot):
    return {
        "schemaVersion": "creation-reasoning-v1",
        "kind": "edit_proposal",
        "message": "建议调整节奏",
        "questions": [],
        "clips": clip_rows(snapshot),
        "citations": [r["clipId"] for r in clip_rows(snapshot)],
    }


def test_executable_delete_slow_and_transition():
    snapshot, root, report, timelines = fixture()
    response = output(snapshot)
    response["clips"] = response["clips"][:2]
    response["clips"][0]["speed"] = {"numerator": 1, "denominator": 2}
    response["clips"][1]["transitionIn"] = {"type": "crossfade", "frames": 1}
    proposal = validate_proposal(snapshot, response)
    revision = revision_for_application(proposal, snapshot)
    plan = validate_revision(root, report, root, revision, timelines, SHA)
    assert proposal.after_seconds == plan.frames / plan.fps
    assert proposal.changes
    assert "尚未应用" in proposal.response["message"]
    assert snapshot.payload["parent_edl"] == root
    response["clips"].clear()
    assert proposal.response["clips"]


@pytest.mark.parametrize(
    "fault",
    [
        "unknown",
        "range",
        "bool",
        "speed_bool",
        "extra",
        "duplicate",
        "citation",
        "deleted",
        "top_extra",
    ],
)
def test_invalid_proposals(fault):
    snapshot, _, _, _ = fixture()
    response = output(snapshot)
    row = response["clips"][0]
    if fault == "unknown":
        row["clipId"] = "unknown"
    elif fault == "range":
        row["endUs"] += 1
    elif fault == "bool":
        row["startUs"] = True
    elif fault == "speed_bool":
        row["speed"]["numerator"] = True
    elif fault == "extra":
        row["sourcePath"] = "secret"
    elif fault == "duplicate":
        response["clips"][1] = deepcopy(row)
    elif fault == "citation":
        response["citations"] = ["unknown"]
    elif fault == "deleted":
        response["clips"].pop()
        response["citations"] = []
    else:
        response["paidCost"] = 0
    with pytest.raises(ValueError):
        validate_proposal(snapshot, response)


def test_snapshot_binding_and_detachment():
    snapshot, root, _, _ = fixture()
    proposal = validate_proposal(snapshot, output(snapshot))
    changed = create_snapshot("job", "plan", "c" * 64, SHA, root)
    with pytest.raises(ValueError, match="Stale"):
        revision_for_application(proposal, changed)
    root["segments"][0]["startUs"] += 1
    assert snapshot.payload["parent_edl"] != root


@pytest.mark.parametrize("kind", ["clarification", "unsupported"])
def test_non_edit_response(kind):
    snapshot, _, _, _ = fixture()
    response = output(snapshot)
    response.update(kind=kind, clips=[], questions=["请指出 logo 在哪个镜头？"])
    proposal = validate_proposal(snapshot, response)
    assert proposal.before_seconds == proposal.after_seconds
    assert not proposal.changes
    with pytest.raises(ValueError):
        revision_for_application(proposal, snapshot)
    response["clips"] = clip_rows(snapshot)
    with pytest.raises(ValueError):
        validate_proposal(snapshot, response)


def test_verified_v4_parent_keeps_real_snapshot_identity_and_applies_with_manifest():
    from gamingcreator.application.creation_editing import build_revision
    from gamingcreator.application.creation_replacements import candidate_manifest_sha

    snapshot, root, _, _ = fixture()
    parent = build_revision(root, SHA, clip_rows(snapshot))
    manifest = {
        "schemaVersion": "creation-candidates-v1",
        "rootReceiptSha256": SHA,
        "candidates": [],
    }
    parent.update(
        schemaVersion="edit-decision-revision-v4",
        candidateManifestSha256=candidate_manifest_sha(manifest),
        replacements=[],
    )
    trusted = create_snapshot("job", "plan", "c" * 64, SHA, parent)
    assert trusted.payload["parent_edl"]["schemaVersion"] == "edit-decision-revision-v4"
    assert trusted.fingerprint != snapshot.fingerprint
    response = output(trusted)
    response["clips"][0]["speed"] = {"numerator": 1, "denominator": 2}
    proposal = validate_proposal(trusted, response)
    assert proposal.after_seconds > proposal.before_seconds
    with pytest.raises(ValueError, match="manifest"):
        revision_for_application(proposal, trusted)
    revised = revision_for_application(proposal, trusted, candidate_manifest=manifest)
    assert revised["schemaVersion"] == "edit-decision-revision-v4"
    assert revised["candidateManifestSha256"] == parent["candidateManifestSha256"]
    assert revised["segments"][0]["clipId"] == parent["segments"][0]["clipId"]
    assert trusted.payload["parent_edl"] == parent
