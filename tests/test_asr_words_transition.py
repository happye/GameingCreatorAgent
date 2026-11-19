"""E20：转场重叠区按既有策略叠放词级字幕，不串句、不错归镜头。"""

from __future__ import annotations

from fractions import Fraction

from test_creation_subtitles import asset, speech

from gamingcreator.application.asr_word_timing import AsrWord, map_words_to_edit_timeline
from gamingcreator.application.creation_subtitles import build_subtitles, present_subtitles
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue, parse_srt, serialize_srt
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_render import _burn_ass, burn_events


def test_transition_words_overlap_without_merging_or_misattributing():
    plan = RenderPlan(
        (
            RenderClip(asset("a"), SourceRange(0, 1_000_000, 10_000_000), 30),
            RenderClip(asset("b"), SourceRange(0, 1_000_000, 10_000_000), 30),
        ),
        30,
        (0, 6),
    )
    assert plan.start_frames == (0, 24)
    words = (
        AsrWord("a", SourceRange(0, 500_000, 10_000_000), "你好"),
        AsrWord("a", SourceRange(500_000, 1_000_000, 10_000_000), "世界"),
        AsrWord("b", SourceRange(0, 500_000, 10_000_000), "再见"),
        AsrWord("b", SourceRange(500_000, 1_000_000, 10_000_000), "朋友"),
    )
    cues = map_words_to_edit_timeline(plan, words)
    assert [(c.text, c.start, c.end, c.clip_index) for c in cues] == [
        ("你好", Fraction(0), Fraction(1, 2), 0),
        ("世界", Fraction(1, 2), Fraction(1), 0),
        ("再见", Fraction(4, 5), Fraction(13, 10), 1),
        ("朋友", Fraction(13, 10), Fraction(9, 5), 1),
    ]
    # 重叠区 0.8–1.0 秒同时有第一段的“世界”和第二段的“再见”，必须是两条，不能并成一句。
    overlap = [c for c in cues if c.start < Fraction(1) and Fraction(4, 5) < c.end]
    assert [(c.text, c.clip_index) for c in overlap] == [("世界", 0), ("再见", 1)]
    assert all(cue.text in {"你好", "世界", "再见", "朋友"} for cue in cues)
    events = list(burn_events(cues))
    texts = {event[2] for event in events}
    assert texts == {"你好", "世界", "再见", "朋友"}
    lifted_overlap = [
        event
        for event in events
        if event[0] == Fraction(4, 5) and event[1] == Fraction(1) and event[3]
    ]
    assert lifted_overlap == [(Fraction(4, 5), Fraction(1), "世界", True)]
    bottom_overlap = [
        event
        for event in events
        if event[0] == Fraction(4, 5) and event[1] == Fraction(1) and not event[3]
    ]
    assert bottom_overlap == [(Fraction(4, 5), Fraction(1), "再见", False)]
    ass = _burn_ass(cues, 640, 480)
    assert "0:00:00.80,0:00:01.00,Default,,0,0,60" in ass
    assert ",0,0,60,,世界" in ass.replace("\n", "")
    assert "世界再见" not in ass
    segment = SubtitleCue(Fraction(0), Fraction(2), "整段", "asr", 0)
    presented = present_subtitles((segment,), words=words, sidecar_available=True, plan=plan)
    assert presented.source == "words"
    assert presented.cues == cues


def test_same_source_transition_keeps_two_cues_on_existing_clock():
    plan = RenderPlan(
        tuple(RenderClip(asset("a"), SourceRange(0, 1_000_000, 10_000_000), 30) for _ in range(2)),
        30,
        (0, 6),
    )
    words = (AsrWord("a", SourceRange(0, 1_000_000, 10_000_000), "同一句"),)
    cues = map_words_to_edit_timeline(plan, words)
    segments = build_subtitles(plan, (speech(0, 1_000_000, "同一句"),))
    assert [(c.start, c.end, c.clip_index, c.text) for c in cues] == [
        (Fraction(0), Fraction(1), 0, "同一句"),
        (Fraction(4, 5), Fraction(9, 5), 1, "同一句"),
    ]
    assert [(c.start, c.end, c.clip_index, c.text) for c in cues] == [
        (c.start, c.end, c.clip_index, c.text) for c in segments
    ]
    assert len(parse_srt(serialize_srt(cues))) == 2
    # 即使两段词文字相同，重叠时仍按镜头分开抬高，而不是合成一句。
    ass = _burn_ass(cues, 640, 480)
    assert "0:00:00.80,0:00:01.00,Default,,0,0,60" in ass
    assert "0:00:00.00,0:00:00.80,Default,,0,0,4" in ass
    events = list(burn_events(cues))
    assert [(start, end, text, lifted) for start, end, text, lifted in events] == [
        (Fraction(0), Fraction(4, 5), "同一句", False),
        (Fraction(4, 5), Fraction(1), "同一句", True),
        (Fraction(4, 5), Fraction(1), "同一句", False),
        (Fraction(1), Fraction(9, 5), "同一句", False),
    ]


def test_narration_and_two_crossfaded_sources_have_distinct_lanes():
    cues = (
        SubtitleCue(Fraction(0), Fraction(2), "原声一", clip_index=0),
        SubtitleCue(Fraction(1), Fraction(3), "原声二", clip_index=1),
        SubtitleCue(Fraction(1), Fraction(2), "旁白"),
    )
    overlapping = {
        text: lane for start, end, text, lane in burn_events(cues) if (start, end) == (1, 2)
    }
    assert overlapping == {"原声一": 2, "原声二": 1, "旁白": 0}
    output = _burn_ass(cues, 640, 480)
    assert all(
        f",0,0,{margin},,{text}" in output
        for text, margin in (("原声一", 120), ("原声二", 60), ("旁白", 4))
    )
