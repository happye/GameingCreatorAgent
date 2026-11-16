"""E18：同一原片用在不同输出位置时，按各自输出位置映词，不串到另一段。"""

from __future__ import annotations

from fractions import Fraction

from test_asr_word_timing import clip

from gamingcreator.application.asr_word_timing import AsrWord, map_words_to_edit_timeline
from gamingcreator.application.creation_subtitles import present_subtitles
from gamingcreator.application.rendering import RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.time import SourceRange


def _words() -> tuple[AsrWord, ...]:
    return (
        AsrWord("a", SourceRange(0, 400_000, 10_000_000), "你好"),
        AsrWord("a", SourceRange(400_000, 1_000_000, 10_000_000), "世界"),
        AsrWord("a", SourceRange(2_000_000, 2_400_000, 10_000_000), "更后"),
    )


def _snapshot(words: tuple[AsrWord, ...]) -> tuple[tuple[str, int, int, str], ...]:
    return tuple(
        (word.media_id, word.source_range.start_us, word.source_range.end_us, word.text)
        for word in words
    )


def _rows(cues: tuple[SubtitleCue, ...]) -> list[tuple[str, Fraction, Fraction, int | None]]:
    return [(cue.text, cue.start, cue.end, cue.clip_index) for cue in cues]


def test_repeated_source_keeps_separate_output_slots():
    words = _words()
    before = _snapshot(words)
    # 同一段 0–1s 原片在时间线上放两次，词要在两个输出位置各出现一次，不能并成一句。
    plan = RenderPlan((clip(0, 1_000_000, 30), clip(0, 1_000_000, 30)), 30)
    cues = map_words_to_edit_timeline(plan, words)
    assert _rows(cues) == [
        ("你好", Fraction(0), Fraction(2, 5), 0),
        ("世界", Fraction(2, 5), Fraction(1), 0),
        ("你好", Fraction(1), Fraction(7, 5), 1),
        ("世界", Fraction(7, 5), Fraction(2), 1),
    ]
    # 输出帧按官方整数起点计算，源时刻仍留在原词上。
    assert plan.start_frames == (0, 30)
    assert [int(cue.start * plan.fps) for cue in cues] == [0, 12, 30, 42]
    assert [int(cue.end * plan.fps) for cue in cues] == [12, 30, 42, 60]
    assert _snapshot(words) == before
    assert all(word.source_range.start_us in (0, 400_000, 2_000_000) for word in words)
    segment = SubtitleCue(Fraction(0), Fraction(2), "重复原片", "asr", 0)
    presented = present_subtitles((segment,), words=words, sidecar_available=True, plan=plan)
    assert presented.source == "words"
    assert presented.cues == cues
    # “更后”只在 2s 处，不应串进这两段重复镜头。
    assert "更后" not in [cue.text for cue in cues]


def test_reordered_clips_follow_new_output_positions():
    words = _words()
    before = _snapshot(words)
    original = RenderPlan((clip(0, 1_000_000, 30), clip(2_000_000, 3_000_000, 30)), 30)
    reordered = RenderPlan((clip(2_000_000, 3_000_000, 30), clip(0, 1_000_000, 30)), 30)
    first = map_words_to_edit_timeline(original, words)
    later = map_words_to_edit_timeline(reordered, words)
    assert _rows(first) == [
        ("你好", Fraction(0), Fraction(2, 5), 0),
        ("世界", Fraction(2, 5), Fraction(1), 0),
        ("更后", Fraction(1), Fraction(7, 5), 1),
    ]
    # 对调后，“更后”抢到输出起点；前面那句改到第二段，不能还按源时刻排序串回去。
    assert _rows(later) == [
        ("更后", Fraction(0), Fraction(2, 5), 0),
        ("你好", Fraction(1), Fraction(7, 5), 1),
        ("世界", Fraction(7, 5), Fraction(2), 1),
    ]
    assert reordered.start_frames == (0, 30)
    assert [int(cue.start * reordered.fps) for cue in later] == [0, 30, 42]
    assert _snapshot(words) == before
    segment = SubtitleCue(Fraction(0), Fraction(2), "对调后的台词", "asr", 0)
    presented = present_subtitles((segment,), words=words, sidecar_available=True, plan=reordered)
    assert presented.cues == later
    assert presented.cues[0].text == "更后"
    assert presented.cues[0].clip_index == 0
