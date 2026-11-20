"""E15：没有词级结果或还没生成时，继续用段级字幕，不伪造逐词高亮，也不挡住导出。"""

from __future__ import annotations

from fractions import Fraction

from gamingcreator.application.asr_word_timing import AsrWord
from gamingcreator.application.creation_subtitles import present_subtitles
from gamingcreator.domain.creation_subtitles import SubtitleCue, serialize_srt
from gamingcreator.domain.time import SourceRange


def _segment() -> SubtitleCue:
    return SubtitleCue(Fraction(0), Fraction(2), "你好世界", "asr", 0)


def _even_split(cue: SubtitleCue) -> tuple[SubtitleCue, ...]:
    text = cue.text
    span = cue.end - cue.start
    step = span / len(text)
    return tuple(
        SubtitleCue(cue.start + step * index, cue.start + step * (index + 1), char, "asr-word", 0)
        for index, char in enumerate(text)
    )


def test_missing_or_empty_words_keep_segment_cues_and_disable_highlights():
    segment = _segment()
    missing = present_subtitles((segment,))
    empty = present_subtitles((segment,), words=())
    invented = (
        AsrWord("media", SourceRange(0, 500_000, 2_000_000), "你"),
        AsrWord("media", SourceRange(500_000, 1_000_000, 2_000_000), "好"),
        AsrWord("media", SourceRange(1_000_000, 1_500_000, 2_000_000), "世"),
        AsrWord("media", SourceRange(1_500_000, 2_000_000, 2_000_000), "界"),
    )
    untrusted = present_subtitles((segment,), words=invented, sidecar_available=False)
    for presentation in (missing, empty, untrusted):
        assert presentation.source == "segment"
        assert presentation.word_highlights is False
        assert presentation.cues == (segment,)
        assert presentation.cues != _even_split(segment)
        assert serialize_srt(presentation.cues) == serialize_srt((segment,))
        assert "你好世界" in serialize_srt(presentation.cues)
        assert serialize_srt(presentation.cues).count("-->") == 1


def test_unverified_words_do_not_block_ordinary_export_text():
    segment = _segment()
    presentation = present_subtitles((segment,), words=None, sidecar_available=False)
    exported = serialize_srt(presentation.cues)
    assert exported.startswith("1\n")
    assert "你好世界" in exported
    assert presentation.word_highlights is False
