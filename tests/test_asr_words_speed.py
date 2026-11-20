"""E19：0.5/1/2 倍速按官方整数输出帧映词，贴边词不越镜头，不用浮点累计。"""

from __future__ import annotations

from fractions import Fraction

from test_asr_word_timing import asset, clip
from test_creation_subtitles import speech

from gamingcreator.application.asr_word_timing import AsrWord, map_words_to_edit_timeline
from gamingcreator.application.creation_subtitles import build_subtitles, present_subtitles
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.time import SourceRange


def test_speed_mapping_reuses_integer_frame_clock_and_matches_segments():
    clips = tuple(
        RenderClip(asset(), SourceRange(1_000_000, 2_000_000, 10_000_000), frames, speed)
        for frames, speed in ((60, Fraction(1, 2)), (15, Fraction(2)))
    )
    plan = RenderPlan(clips, 30)
    words = (AsrWord("a", SourceRange(1_250_000, 1_750_000, 10_000_000), "半段"),)
    # 与段级字幕同一套整数帧时钟，不另写第二套换算。
    segment_cues = build_subtitles(plan, (speech(1_250_000, 1_750_000),))
    word_cues = map_words_to_edit_timeline(plan, words)
    assert [(c.start, c.end) for c in word_cues] == [
        (Fraction(1, 2), Fraction(3, 2)),
        (Fraction(17, 8), Fraction(19, 8)),
    ]
    assert [(c.start, c.end) for c in word_cues] == [(c.start, c.end) for c in segment_cues]
    assert plan.start_frames == (0, 60)
    assert [int(c.start * plan.fps) for c in word_cues] == [15, 63]
    assert [int(c.end * plan.fps) for c in word_cues] == [45, 71]
    # 1 倍速保持源相对时长；贴到镜头终点的词停在镜头输出终点，不越出去。
    normal = RenderPlan((clip(1_000_000, 2_000_000, 30),), 30)
    identity = map_words_to_edit_timeline(
        normal, (AsrWord("a", SourceRange(1_000_000, 2_000_000, 10_000_000), "整段"),)
    )
    assert [(c.start, c.end) for c in identity] == [(Fraction(0), Fraction(1))]
    overflowing = map_words_to_edit_timeline(
        plan, (AsrWord("a", SourceRange(1_000_000, 2_500_000, 10_000_000), "越界"),)
    )
    assert overflowing[0].end == Fraction(60, 30)
    assert overflowing[0].end == Fraction(plan.clips[0].output_frames, plan.fps)
    assert overflowing[1].end == Fraction(60 + 15, 30)
    capped = RenderPlan(
        (RenderClip(asset(), SourceRange(1_000_000, 2_000_000, 10_000_000), 40, Fraction(1, 2)),),
        30,
    )
    capped_cues = map_words_to_edit_timeline(
        capped, (AsrWord("a", SourceRange(1_250_000, 2_000_000, 10_000_000), "封顶"),)
    )
    assert capped_cues[0].start == Fraction(1, 2)
    assert capped_cues[0].end == Fraction(4, 3)
    assert capped_cues[0].end == Fraction(40, 30)
    # 刚好落在镜头终点之后的词不进来。
    assert (
        map_words_to_edit_timeline(
            plan, (AsrWord("a", SourceRange(2_000_000, 2_100_000, 10_000_000), "镜头外"),)
        )
        == ()
    )
    presented = present_subtitles(segment_cues, words=words, sidecar_available=True, plan=plan)
    assert presented.source == "words"
    assert presented.cues == word_cues


def test_speed_offsets_use_integer_start_frames_not_float_sums():
    # 连续几段 0.5/1/2 倍速，输出起点只来自整数帧累加，避免 0.5+0.5 这类浮点漂移。
    clips = (
        RenderClip(asset(), SourceRange(0, 1_000_000, 10_000_000), 60, Fraction(1, 2)),
        RenderClip(asset(), SourceRange(1_000_000, 2_000_000, 10_000_000), 30, Fraction(1)),
        RenderClip(asset(), SourceRange(2_000_000, 3_000_000, 10_000_000), 15, Fraction(2)),
        RenderClip(asset(), SourceRange(0, 1_000_000, 10_000_000), 60, Fraction(1, 2)),
        RenderClip(asset(), SourceRange(1_000_000, 2_000_000, 10_000_000), 30, Fraction(1)),
    )
    plan = RenderPlan(clips, 30)
    assert plan.start_frames == (0, 60, 90, 105, 165)
    words = (
        AsrWord("a", SourceRange(0, 200_000, 10_000_000), "甲"),
        AsrWord("a", SourceRange(1_000_000, 1_200_000, 10_000_000), "乙"),
        AsrWord("a", SourceRange(2_000_000, 2_200_000, 10_000_000), "丙"),
    )
    cues = map_words_to_edit_timeline(plan, words)
    starts = [cue.start for cue in cues]
    # 甲出现在第 1、4 段（0.5 倍，0.2s 源 -> 0.4s），乙在第 2、5 段，丙在第 3 段。
    expected_start_frames = (0, 60, 90, 105, 165)
    assert [int(start * plan.fps) for start in starts] == list(expected_start_frames)
    assert all(type(start) is Fraction for start in starts)
    # 若用浮点逐段加时长，多次 0.5 可能对不齐整数帧；这里必须仍精确落到帧上。
    assert all((start * plan.fps).denominator == 1 for start in starts)
    assert all((cue.end * plan.fps).denominator == 1 for cue in cues)
    durations = [cue.end - cue.start for cue in cues]
    assert durations == [
        Fraction(2, 5),  # 0.2s / 0.5
        Fraction(1, 5),  # 0.2s / 1
        Fraction(1, 10),  # 0.2s / 2
        Fraction(2, 5),
        Fraction(1, 5),
    ]
