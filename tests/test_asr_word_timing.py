"""ASR word-timing probe and conditional edit-timeline mapping (no invented timings)."""

import hashlib
import wave
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.asr_word_timing import (
    AsrWord,
    WorkerWord,
    collect_worker_words,
    map_words_to_edit_timeline,
    map_worker_words_to_source,
    probe_local_asr_word_timing,
    stitch_window_words,
    transcript_segment_has_words,
    validate_worker_words,
    words_from_provider_segment,
)
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.media import AudioEvidence, AudioFrameMapping, MediaAsset, MediaStream
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


def test_collect_worker_words_keeps_original_rows_and_returns_empty_when_missing():
    assert (
        collect_worker_words({"segments": [{"start": "0.0", "end": "1.0", "text": "一，二，三"}]})
        == ()
    )
    assert (
        collect_worker_words(
            {"segments": [{"start": "0.0", "end": "1.0", "text": "你好世界"}], "words": []}
        )
        == ()
    )
    result = {
        "segments": [{"start": "0.1", "end": "0.8", "text": "hello world"}],
        "words": [
            {"start": "0.1", "end": "0.3", "text": "hello"},
            {"start": "0.31", "end": "0.8", "text": "world"},
        ],
    }
    assert collect_worker_words(result) == (
        WorkerWord("hello", "0.1", "0.3"),
        WorkerWord("world", "0.31", "0.8"),
    )


def test_collect_worker_words_does_not_split_text_or_average_time():
    # A single model word that happens to contain punctuation or several characters
    # must stay one row; this collector has no split/average path.
    result = {
        "segments": [{"start": "0.0", "end": "1.0", "text": "你好，世界"}],
        "words": [{"start": "0.0", "end": "1.0", "text": "你好，世界"}],
    }
    assert collect_worker_words(result) == (WorkerWord("你好，世界", "0.0", "1.0"),)
    with pytest.raises(ValueError):
        collect_worker_words({"words": "你好，世界"})
    with pytest.raises(ValueError):
        collect_worker_words({"words": [{"start": 0.0, "end": 1.0, "text": "hello"}]})


def test_validate_worker_words_rejects_invalid_times_and_does_not_rewrite():
    rate, count = 16000, 16000
    original = (WorkerWord("hello", "0.1", "0.3"), WorkerWord("world", "0.31", "0.8"))
    assert validate_worker_words(original, sample_rate=rate, sample_count=count) is not None
    assert validate_worker_words(original, sample_rate=rate, sample_count=count) == original
    assert validate_worker_words((), sample_rate=rate, sample_count=count) == ()

    assert validate_worker_words(original, sample_rate=rate, sample_count=count)[0].start == "0.1"
    assert validate_worker_words(original, sample_rate=rate, sample_count=count)[0].end == "0.3"

    for words in (
        (WorkerWord("x", "NaN", "0.2"),),
        (WorkerWord("x", "Infinity", "0.2"),),
        (WorkerWord("x", "-0.1", "0.2"),),
        (WorkerWord("x", "0.5", "0.2"),),
        (WorkerWord("x", "0.2", "0.2"),),
        (WorkerWord("x", "0.0", "1.1"),),
        (WorkerWord("x", "abc", "0.2"),),
    ):
        with pytest.raises(ValueError, match="词时间无效"):
            validate_worker_words(words, sample_rate=rate, sample_count=count)


def test_worker_words_use_official_wav_rounding_and_piecewise_source_clock(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic source identity")
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(10)
        output.writeframes(b"\x00\x00" * 10)
    asset = MediaAsset(
        "media",
        source,
        hashlib.sha256(source.read_bytes()).hexdigest(),
        (
            MediaStream(0, "video", Fraction(1, 10), 0, 20),
            MediaStream(1, "audio", Fraction(1, 10), 0, 20),
        ),
        Fraction(0),
        2_000_000,
        "fake-probe",
    )
    clock = AudioEvidence(
        "audio",
        audio,
        hashlib.sha256(audio.read_bytes()).hexdigest(),
        10,
        10,
        (AudioFrameMapping(0, 3, 0, Fraction(1, 10)), AudioFrameMapping(3, 7, 5, Fraction(1, 10))),
    )
    # Same 0.1-0.8s interval as the official segment path: crosses the PTS gap after sample 3.
    words = map_worker_words_to_source((WorkerWord("测试", "0.1", "0.8"),), clock, asset)
    assert words == (AsrWord("media", SourceRange(100000, 1000000, 2_000_000), "测试"),)
    later = map_worker_words_to_source((WorkerWord("后段", "0.5", "0.7"),), clock, asset)
    assert later[0].source_range.start_us > 500_000
    assert later[0].source_range.end_us == 900_000


def test_stitch_window_words_keeps_identity_and_does_not_merge_sources():
    first = AsrWord("a", SourceRange(0, 400_000, 10_000_000), "你好")
    overlap = AsrWord("a", SourceRange(200_000, 600_000, 10_000_000), "你好")
    later = AsrWord("a", SourceRange(600_000, 900_000, 10_000_000), "世界")
    other = AsrWord("b", SourceRange(200_000, 600_000, 10_000_000), "你好")
    stitched = stitch_window_words(((first, overlap), (later,), (other,)))
    assert stitched == (first, other, later)
    assert [word.text for word in stitched] == ["你好", "你好", "世界"]
    assert "你好世界" not in {word.text for word in stitched}
    assert stitch_window_words(()) == ()
    # Adjacent, non-overlapping repeats of the same text stay two words.
    left = AsrWord("a", SourceRange(0, 200_000, 10_000_000), "好")
    right = AsrWord("a", SourceRange(200_000, 400_000, 10_000_000), "好")
    assert stitch_window_words(((left,), (right,))) == (left, right)
