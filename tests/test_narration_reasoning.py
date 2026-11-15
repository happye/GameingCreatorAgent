"""Narration provenance, immutable inputs and final spoken clock contracts."""

import json
from copy import deepcopy
from fractions import Fraction

import pytest

from gamingcreator.application.narration_reasoning import (
    SCHEMA_VERSION,
    narration_request,
    narration_snapshot,
    validate_narration,
)
from gamingcreator.application.narration_script import CHARS_PER_SECOND, FILL_RATIO

BRIEF = {
    "game": "Atom",
    "contentType": "feature_showcase",
    "platforms": ["bilibili"],
    "targetDuration": 12,
    "objective": "介绍玩法",
    "audience": "新玩家",
    "tone": "简洁",
    "mandatoryTopics": ["角色"],
    "exclude": [],
}
CLIPS = [
    {
        "clipId": "a",
        "outputStartFrame": 0,
        "outputFrames": 180,
        "scriptDraft": "角色奔跑经过城堡",
        "path": "secret.mp4",
        "startUs": 999,
    },
    {
        "clipId": "b",
        "outputStartFrame": 180,
        "outputFrames": 180,
        "scriptDraft": "蓝色球体碰到红球",
        "sourcePath": "private.mp4",
    },
]
KNOWLEDGE = [
    {"entryId": "k", "text": "能量需要等待恢复", "citation": "本地手册", "path": "private"}
]


def snapshot(**kwargs):
    args = dict(
        job_id="job",
        plan_id="plan",
        parent_receipt_sha256="a" * 64,
        root_receipt_sha256="b" * 64,
        brief=deepcopy(BRIEF),
        clips=deepcopy(CLIPS),
        output_frames=360,
        fps=30,
        knowledge=deepcopy(KNOWLEDGE),
    )
    args.update(kwargs)
    return narration_snapshot(**args)


def output(snap):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "snapshotFingerprint": snap.fingerprint,
        "lines": [
            {
                "clipId": "a",
                "text": "一路跑向城堡",
                "observationQuote": "角色奔跑",
                "knowledgeUses": [{"entryId": "k", "quote": "等待恢复"}],
            }
        ],
    }


def test_whitelist_frozen_payload_and_complete_fingerprint():
    clips = deepcopy(CLIPS)
    knowledge = deepcopy(KNOWLEDGE)
    snap = snapshot(clips=clips, knowledge=knowledge)
    before = snap.fingerprint
    clips[0]["scriptDraft"] = "changed"
    knowledge[0]["citation"] = "changed"
    snap.payload["brief"]["game"] = "changed"
    assert snap.fingerprint == before
    request = narration_request(snap)
    assert "private" not in request.user and "secret.mp4" not in request.user
    assert "startUs" not in request.user
    assert set(snap.payload["clips"][0]) == {
        "clipId",
        "outputStartFrame",
        "outputFrames",
        "scriptDraft",
    }
    assert set(snap.payload["knowledge"][0]) == {"entryId", "text", "citation"}
    assert json.loads(request.user)["snapshotFingerprint"] == before
    assert snapshot(knowledge=knowledge).fingerprint != before
    assert snapshot(root_receipt_sha256="c" * 64).fingerprint != before
    assert snapshot(parent_receipt_sha256="c" * 64).fingerprint != before
    brief = deepcopy(BRIEF)
    brief["tone"] = "活泼"
    assert snapshot(brief=brief).fingerprint != before


def test_compatible_shape_punctuation_clock_and_echo():
    snap = snapshot()
    result = validate_narration(snap, output(snap))
    assert result["schemaVersion"] == "creation-narration-script-v1"
    assert result["status"] == "ai-draft-human-review-required"
    assert result["generator"] == "ai-deepseek-v1"
    assert result["text"] == "一路跑向城堡。"
    assert result["lines"][0]["outputStartFrame"] == 0
    assert result["omittedClips"] == 1
    assert result["citations"] == [{k: KNOWLEDGE[0][k] for k in ("entryId", "text", "citation")}]
    assert result["budgetCharacters"] == int(Fraction(360, 30) * CHARS_PER_SECOND * FILL_RATIO)
    assert result["estimatedSeconds"] <= result["outputSeconds"] == 12
    assert result["fingerprintEcho"] == "exact"
    changed = output(snap)
    changed["snapshotFingerprint"] = "invented"
    assert validate_narration(snap, changed)["fingerprintEcho"] == "mismatch"


@pytest.mark.parametrize(
    "field,value",
    [
        ("clipId", "unknown"),
        ("observationQuote", "蓝色球体"),
        ("observationQuote", ""),
        ("observationQuote", "角色" * 251),
        ("text", " "),
        ("outputStartFrame", 0),
        ("path", "file.mp4"),
        ("receiptSha256", "fake"),
        ("knowledgeUses", [{"entryId": "missing", "quote": "等待"}]),
        ("knowledgeUses", [{"entryId": "k", "quote": "无限能量"}]),
        ("knowledgeUses", [{"entryId": "k", "quote": "等待"}] * 2),
        ("knowledgeUses", [{"entryId": "k", "quote": "等待", "citation": "fake"}]),
    ],
)
def test_rejects_invalid_line_and_model_identity(field, value):
    snap = snapshot()
    response = output(snap)
    response["lines"][0][field] = value
    with pytest.raises(ValueError):
        validate_narration(snap, response)


@pytest.mark.parametrize("ids", [["a", "a"], ["b", "a"]])
def test_rejects_duplicate_or_reordered_clips(ids):
    snap = snapshot()
    response = output(snap)
    response["lines"] = [
        dict(
            clipId=clip_id,
            text="继续前进",
            observationQuote=CLIPS[0 if clip_id == "a" else 1]["scriptDraft"],
            knowledgeUses=[],
        )
        for clip_id in ids
    ]
    with pytest.raises(ValueError):
        validate_narration(snap, response)


def test_final_punctuation_counts_toward_budget_and_no_truncation():
    snap = snapshot()
    response = output(snap)
    response["lines"][0]["text"] = "字" * snap.payload["budgetCharacters"]
    with pytest.raises(ValueError, match="budget"):
        validate_narration(snap, response)
    response["lines"][0]["text"] = "字" * (snap.payload["budgetCharacters"] - 1)
    assert len(validate_narration(snap, response)["text"]) == snap.payload["budgetCharacters"]


@pytest.mark.parametrize("frames,fps", [(0, 30), (360, 0), (True, 30), (360, 29.97)])
def test_rejects_invalid_output_clock(frames, fps):
    with pytest.raises(ValueError):
        snapshot(output_frames=frames, fps=fps)


def test_no_descriptions_fails_before_request_and_knowledge_is_bounded():
    clips = deepcopy(CLIPS)
    for clip in clips:
        clip["scriptDraft"] = " "
    with pytest.raises(ValueError, match="descriptions"):
        snapshot(clips=clips)
    entries = [dict(entryId=str(i), text="资料", citation="手册") for i in range(4)]
    assert len(snapshot(knowledge=entries).payload["knowledge"]) == 3
