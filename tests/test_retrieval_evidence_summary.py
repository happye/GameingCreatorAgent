"""Registered image clocks and bytes are visible without proving an action."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_retrieval_diagnostics import diagnose, row

from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.time import SourceInstant, SourceRange


def image(identifier, time, digest="a" * 64, *, media_id="media-1"):
    return EvidenceReference(
        identifier,
        media_id,
        "image",
        SourceInstant(time, 2_000_000),
        Path("not-read.jpg"),
        digest,
        "fixture",
    )


def audio(identifier="audio-1", start=0, end=1_000_000):
    return EvidenceReference(
        identifier,
        "media-1",
        "audio",
        SourceRange(start, end, 2_000_000),
        Path("not-read.wav"),
        "c" * 64,
        "fixture",
    )


def summary(references, ids=None):
    candidate = replace(
        row(1, "event-1"),
        evidence_ids=tuple(item.evidence_id for item in references) if ids is None else tuple(ids),
    )
    doc = diagnose([candidate], evidence=tuple(references))
    assert doc["schemaVersion"] == "retrieval-diagnostics-v2"
    assert doc["slots"][0]["candidate"]["evidenceIds"] == list(candidate.evidence_ids)
    assert doc["slots"][0]["candidate"]["observableFacts"] == list(candidate.facts)
    assert doc["qualityGate"] is None and doc["usefulRate"] is None
    result = doc["slots"][0]["candidate"]["evidenceSummary"]
    assert result["actionUnderstandingVerified"] is None
    return result


def test_single_registered_frame_exposes_one_instant_without_reading_file():
    result = summary([image("frame-1", 200_000)])
    assert result["status"] == "registered_single_frame"
    assert result["registeredImageCount"] == result["distinctImageSourceTimeCount"] == 1
    assert result["firstImageSourceUs"] == result["lastImageSourceUs"] == 200_000
    assert result["imageSpanUs"] == 0 and result["registeredAudioCount"] == 0


def test_multi_frame_summary_uses_registered_clocks_and_hashes_in_source_order():
    result = summary(
        [
            image("later", 600_000, "b" * 64),
            image("earlier", 200_000),
            audio(),
        ]
    )
    assert result["status"] == "registered_multi_frame"
    assert result["registeredImageCount"] == result["distinctImageSourceTimeCount"] == 2
    assert result["distinctImageContentCount"] == 2 and result["registeredAudioCount"] == 1
    assert result["imageSpanUs"] == 400_000
    assert result["imageFrames"] == [
        {"evidenceId": "earlier", "sourceUs": 200_000, "sha256": "a" * 64},
        {"evidenceId": "later", "sourceUs": 600_000, "sha256": "b" * 64},
    ]
    assert "artifactPath" not in str(result) and "not-read" not in str(result)


def test_duplicate_references_do_not_inflate_registered_frame_count():
    result = summary([image("one", 200_000)], ["one", "one"])
    assert result["registeredImageCount"] == 1
    assert result["status"] == "registered_single_frame"


def test_multiple_different_files_at_one_instant_do_not_claim_motion():
    result = summary([image("one", 200_000), image("two", 200_000, "b" * 64)])
    assert result["status"] == "registered_same_instant"
    assert result["distinctImageContentCount"] == 2 and result["imageSpanUs"] == 0


def test_repeated_bytes_at_different_instants_do_not_claim_motion():
    result = summary([image("one", 200_000), image("two", 600_000)])
    assert result["status"] == "registered_repeated_content"
    assert result["distinctImageSourceTimeCount"] == 2
    assert result["distinctImageContentCount"] == 1 and result["imageSpanUs"] == 400_000


def test_audio_only_candidate_keeps_audio_evidence_without_visual_claim():
    result = summary([audio()])
    assert result["status"] == "registered_audio_only"
    assert result["registeredAudioCount"] == 1 and result["registeredImageCount"] == 0
    assert result["imageFrames"] == [] and result["imageSpanUs"] is None


@pytest.mark.parametrize(
    "references,ids",
    [
        ([], ["missing"]),
        ([image("known", 200_000)], ["known", "missing"]),
        ([image("known", 200_000, media_id="other-media")], ["known"]),
        (
            [replace(image("known", 200_000), source_time=SourceInstant(200_000, 3_000_000))],
            ["known"],
        ),
        ([image("known", 800_000)], ["known"]),
        ([image("known", 99_999)], ["known"]),
        ([image("known", 200_000), image("known", 300_000)], ["known"]),
        ([audio(start=800_000, end=900_000)], ["audio-1"]),
        ([audio(start=0, end=100_000)], ["audio-1"]),
        ([replace(image("known", 200_000), kind="audio")], ["known"]),
        ([replace(audio(), kind="image")], ["audio-1"]),
        ([], []),
    ],
)
def test_incomplete_foreign_or_out_of_range_registry_does_not_publish_partial_counts(
    references, ids
):
    result = summary(references, ids)
    assert result["status"] == "unavailable"
    assert result["registeredImageCount"] is None
    assert result["distinctImageSourceTimeCount"] is None
    assert result["imageSpanUs"] is None and result["imageFrames"] == []


def test_missing_slots_keep_no_candidate_or_evidence_claim():
    doc = diagnose([row(1, "event-1")], evidence=(image("frame-1", 200_000),))
    assert all(slot["candidate"] is None for slot in doc["slots"][1:])
    assert doc["missingCount"] == 9


def test_multiple_frames_do_not_override_cut_or_uncertain_action_description():
    candidate = replace(
        row(1, "event-1"),
        evidence_ids=("one", "two"),
        facts=("场景切换；未见明确跳跃，主体连续性无法确认。",),
    )
    doc = diagnose([candidate], evidence=(image("one", 200_000), image("two", 600_000, "b" * 64)))
    projected = doc["slots"][0]["candidate"]
    assert projected["observableFacts"] == list(candidate.facts)
    assert projected["evidenceSummary"]["status"] == "registered_multi_frame"
    assert projected["evidenceSummary"]["actionUnderstandingVerified"] is None
    assert doc["slots"][0]["humanGrade"] is None
