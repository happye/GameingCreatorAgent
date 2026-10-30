from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.creation_subtitles import build_subtitles
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue, parse_srt, serialize_srt
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


def speech(start: int, end: int, text: str = "台词", media_id: str = "a") -> TranscriptSegment:
    return TranscriptSegment(media_id, SourceRange(start, end, 10_000_000), text, "ASR uncertain")


def test_cross_cut_and_half_open_boundary() -> None:
    plan = RenderPlan((clip(0, 1_000_000, 30), clip(2_000_000, 3_000_000, 30)), 30)
    original = speech(500_000, 2_500_000)
    cues = build_subtitles(plan, (original, speech(1_000_000, 2_000_000, "excluded")))
    assert [(c.start, c.end) for c in cues] == [
        (Fraction(1, 2), Fraction(1)),
        (Fraction(1), Fraction(3, 2)),
    ]
    assert all(c.uncertainty == "ASR uncertain" for c in cues)
    assert original.source_range.end_us == 2_500_000


def test_reverse_repeat_and_media_identity() -> None:
    plan = RenderPlan(
        (
            clip(2_000_000, 3_000_000, 30),
            clip(0, 1_000_000, 30, "b"),
            clip(2_000_000, 3_000_000, 30),
        ),
        30,
    )
    cues = build_subtitles(
        plan, (speech(2_000_000, 3_000_000, "A"), speech(0, 1_000_000, "B", "b"))
    )
    assert [(c.start, c.text) for c in cues] == [
        (Fraction(0), "A"),
        (Fraction(1), "B"),
        (Fraction(2), "A"),
    ]


def test_frame_clock_exact_and_clipped() -> None:
    plan = RenderPlan((clip(0, 33334, 1),) * 100, 30)
    cues = build_subtitles(plan, (speech(0, 33334),))
    assert len(cues) == 100
    assert cues[-1].start == Fraction(99, 30)
    assert cues[-1].end == Fraction(100, 30)
    assert parse_srt(serialize_srt(cues))[-1].end == Fraction(3333, 1000)


def test_outside_empty_and_unsorted_transcripts() -> None:
    plan = RenderPlan((clip(0, 1_000_000, 30),), 30)
    assert build_subtitles(plan, ()) == ()
    assert build_subtitles(plan, (speech(1_000_000, 2_000_000),)) == ()
    cues = build_subtitles(plan, (speech(800_000, 900_000, "later"), speech(0, 100_000, "first")))
    assert [c.text for c in cues] == ["first", "later"]
    assert serialize_srt(()) == ""
    assert parse_srt("") == ()


def test_multilingual_multiline_roundtrip_and_numbering() -> None:
    cue = SubtitleCue(Fraction(1, 3), Fraction(4, 3), " 中文\r\nEnglish\r\n\r\n下一句 ")
    tiny = SubtitleCue(Fraction(0), Fraction(1, 10000), "tiny")
    text = serialize_srt((tiny, cue, cue))
    assert text.startswith("1\n00:00:00,333 --> 00:00:01,333\n中文\nEnglish\n下一句")
    restored = parse_srt(text.replace("\n", "\r\n"))
    assert serialize_srt(restored) == text
    assert len(restored) == 2
    assert restored[0].uncertainty is None


@pytest.mark.parametrize(
    "timing",
    [
        "-1:00:00,000 --> 00:00:01,000",
        "00:60:00,000 --> 01:00:01,000",
        "00:00:00,000 --> 00:00:00,000",
        "00:00:02,000 --> 00:00:01,000",
        "00:00:00.000 --> 00:00:01.000",
    ],
)
def test_invalid_srt_clock(timing: str) -> None:
    with pytest.raises(ValueError):
        parse_srt(f"1\n{timing}\ntext\n")


@pytest.mark.parametrize(
    "text", ["", " \r\n ", "text\n\n2\n00:00:00,000 --> 00:00:01,000\ninjected", "null\x00"]
)
def test_unsafe_or_empty_text(text: str) -> None:
    with pytest.raises(ValueError):
        SubtitleCue(Fraction(0), Fraction(1), text)


def test_invalid_cue_and_plan_times() -> None:
    with pytest.raises(ValueError):
        SubtitleCue(Fraction(-1), Fraction(1), "text")
    with pytest.raises(ValueError):
        build_subtitles(RenderPlan((), 0), ())
    with pytest.raises(ValueError):
        build_subtitles(RenderPlan((clip(0, 1_000_000, 0),), 30), ())
    with pytest.raises(ValueError):
        parse_srt("2\n00:00:00,000 --> 00:00:01,000\ntext")
