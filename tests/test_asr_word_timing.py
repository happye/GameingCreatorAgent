"""ASR word-timing probe and conditional edit-timeline mapping (no invented timings)."""

from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.asr_word_timing import (
    AsrWord,
    map_words_to_edit_timeline,
    probe_local_asr_word_timing,
    transcript_segment_has_words,
    words_from_provider_segment,
)
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import TranscriptSegment
from gamingcreator.domain.time import SourceRange


def asset(media_id: str = "a") -> MediaAsset:
    return MediaAsset(
        media_id,
        Path(f"{media_id}.mp4"),
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 30), 0, 300),),
        Fraction(0),
        10_000_000,
        "test",
    )


def clip(start: int, end: int, frames: int, media_id: str = "a") -> RenderClip:
    return RenderClip(asset(media_id), SourceRange(start, end, 10_000_000), frames)


def test_probe_reports_local_asr_word_timing_gap() -> None:
    report = probe_local_asr_word_timing()
    assert report.available is False
    assert report.gap is not None
    assert "Do not invent" in report.gap or "不造假" in report.gap or "invent" in report.gap
    assert any("word_timestamps" in item for item in report.evidence)
    assert any("TranscriptSegment" in item for item in report.evidence)
    payload = report.to_json()
    assert payload["available"] is False
    assert payload["version"] == "asr-word-timing-probe-v1"


def test_transcript_segments_have_no_words_today() -> None:
    segment = TranscriptSegment("a", SourceRange(0, 1_000_000, 10_000_000), "整段台词")
    assert transcript_segment_has_words(segment) is False


def test_provider_segment_without_words_yields_empty() -> None:
    # Typical local ASR worker row: segment clock only.
    words = words_from_provider_segment(
        "a",
        10_000_000,
        {"start": "0.0", "end": "1.0", "text": "整段台词"},
    )
    assert words == ()


def test_does_not_invent_words_from_segment_text() -> None:
    plan = RenderPlan((clip(0, 1_000_000, 30),), 30)
    # No AsrWord inputs → empty cues (must not synthesize from any segment text).
    assert map_words_to_edit_timeline(plan, ()) == ()
    invented = words_from_provider_segment(
        "a",
        10_000_000,
        {"start": 0.0, "end": 1.0, "text": "一 二 三"},
    )
    assert invented == ()
    assert map_words_to_edit_timeline(plan, invented) == ()


def test_maps_real_provider_words_onto_edit_timeline() -> None:
    words = words_from_provider_segment(
        "a",
        10_000_000,
        {
            "start": 0.0,
            "end": 1.0,
            "text": "你好世界",
            "words": [
                {"text": "你好", "start": 0.0, "end": 0.4},
                {"text": "世界", "start": 0.4, "end": 1.0},
            ],
        },
    )
    assert [word.text for word in words] == ["你好", "世界"]
    plan = RenderPlan((clip(0, 1_000_000, 30), clip(2_000_000, 3_000_000, 30)), 30)
    # Second clip is outside the word source ranges → only first clip cues.
    cues = map_words_to_edit_timeline(plan, words)
    assert [(c.text, c.start, c.end, c.uncertainty) for c in cues] == [
        ("你好", Fraction(0), Fraction(2, 5), "asr-word"),
        ("世界", Fraction(2, 5), Fraction(1), "asr-word"),
    ]


def test_word_intersection_and_us_payload() -> None:
    words = (AsrWord("a", SourceRange(500_000, 1_500_000, 10_000_000), "半截"),)
    plan = RenderPlan((clip(0, 1_000_000, 30),), 30)
    cues = map_words_to_edit_timeline(plan, words)
    assert len(cues) == 1
    assert cues[0].start == Fraction(1, 2)
    assert cues[0].end == Fraction(1)
    extracted = words_from_provider_segment(
        "a",
        10_000_000,
        {"words": [{"text": "字", "startUs": 100_000, "endUs": 200_000}]},
    )
    assert extracted[0].source_range.start_us == 100_000
    assert extracted[0].source_range.end_us == 200_000


@pytest.mark.parametrize(
    "payload",
    [
        {"words": "nope"},
        {"words": [{"text": "x"}]},
        {"words": [{"text": "", "start": 0, "end": 1}]},
    ],
)
def test_invalid_word_payloads_fail_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        words_from_provider_segment("a", 10_000_000, payload)
