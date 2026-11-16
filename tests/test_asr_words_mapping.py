"""E16：复用已有逐词解析和剪辑映射，只有核对过的 sidecar 才进入词级映射。"""

from __future__ import annotations

import asyncio
from fractions import Fraction

from test_asr_audio import DURATION_US
from test_asr_models import MODEL
from test_asr_word_timing import clip
from test_asr_words_cli import FakeWords, _seed

from gamingcreator.application.asr_word_timing import AsrWord, map_words_to_edit_timeline
from gamingcreator.application.creation_subtitles import present_subtitles
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue, serialize_srt
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.asr_words import load_trusted_asr_words, transcribe_project_words


def test_untrusted_or_incomplete_inputs_stay_on_segment_clock():
    segment = SubtitleCue(Fraction(0), Fraction(1), "整段台词", "asr", 0)
    words = (AsrWord("a", SourceRange(0, 400_000, 10_000_000), "你好"),)
    plan = RenderPlan((clip(0, 1_000_000, 30),), 30)
    missing_sidecar = present_subtitles((segment,), words=words, sidecar_available=False, plan=plan)
    missing_plan = present_subtitles((segment,), words=words, sidecar_available=True)
    empty = present_subtitles((segment,), words=(), sidecar_available=True, plan=plan)
    for presentation in (missing_sidecar, missing_plan, empty):
        assert presentation.source == "segment"
        assert presentation.word_highlights is False
        assert presentation.cues == (segment,)
        assert serialize_srt(presentation.cues) == serialize_srt((segment,))


def test_trusted_words_reuse_existing_edit_timeline_mapping():
    words = (
        AsrWord("a", SourceRange(0, 400_000, 10_000_000), "你好"),
        AsrWord("a", SourceRange(400_000, 1_000_000, 10_000_000), "世界"),
    )
    plan = RenderPlan((clip(0, 1_000_000, 30), clip(2_000_000, 3_000_000, 30)), 30)
    segment = SubtitleCue(Fraction(0), Fraction(1), "你好世界", "asr", 0)
    presentation = present_subtitles((segment,), words=words, sidecar_available=True, plan=plan)
    expected = map_words_to_edit_timeline(plan, words)
    assert presentation.source == "words"
    assert presentation.word_highlights is True
    assert presentation.cues == expected
    assert [(cue.text, cue.start, cue.end, cue.uncertainty) for cue in presentation.cues] == [
        ("你好", Fraction(0), Fraction(2, 5), "asr-word"),
        ("世界", Fraction(2, 5), Fraction(1), "asr-word"),
    ]
    assert presentation.cues != (segment,)


def test_only_verified_sidecar_loads_words_for_mapping(tmp_path):
    repository, project, bundle = _seed(tmp_path)
    summary = asyncio.run(
        transcribe_project_words(project, "run-1", MODEL, repository, provider=FakeWords())
    )
    trusted = asyncio.run(load_trusted_asr_words(project, "run-1", summary.result_hash))
    missing = asyncio.run(load_trusted_asr_words(project, "run-1", "a" * 64))
    assert trusted is not None
    assert [word.text for word in trusted] == ["你好"]
    assert all(word.media_id == bundle.asset.media_id for word in trusted)
    assert missing is None
    plan = RenderPlan(
        (
            RenderClip(
                bundle.asset,
                SourceRange(0, DURATION_US, DURATION_US),
                30,
            ),
        ),
        30,
    )
    segment = SubtitleCue(Fraction(0), Fraction(1), "整段", "asr", 0)
    trusted_view = present_subtitles((segment,), words=trusted, sidecar_available=True, plan=plan)
    untrusted_view = present_subtitles(
        (segment,), words=trusted, sidecar_available=False, plan=plan
    )
    assert trusted_view.cues == map_words_to_edit_timeline(plan, trusted)
    assert trusted_view.source == "words"
    assert untrusted_view.cues == (segment,)
    assert untrusted_view.source == "segment"
