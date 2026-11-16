"""E21：Studio 逐词高亮预览只读已核对结果，关闭回到段级，不改手写字幕。"""
# ruff: noqa: F811

from __future__ import annotations

from fractions import Fraction

import pytest
from test_asr_word_timing import clip
from test_creation_jobs import service  # noqa: F401
from test_creation_revision_jobs import revisions  # noqa: F401

from gamingcreator.application.asr_word_timing import AsrWord
from gamingcreator.application.creation_subtitles import present_subtitles
from gamingcreator.application.rendering import RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.time import SourceRange
from gamingcreator.ui.subtitle_preview import preview


def test_present_subtitles_keeps_handwritten_and_reserved_clips():
    words = (
        AsrWord("a", SourceRange(0, 400_000, 10_000_000), "你好"),
        AsrWord("a", SourceRange(400_000, 1_000_000, 10_000_000), "世界"),
    )
    plan = RenderPlan((clip(0, 1_000_000, 30), clip(0, 1_000_000, 30)), 30)
    handwritten = SubtitleCue(Fraction(0), Fraction(1), "手写台词", "user-written", 0)
    automatic = SubtitleCue(Fraction(1), Fraction(2), "自动段", "asr", 1)
    presented = present_subtitles(
        (handwritten, automatic), words=words, sidecar_available=True, plan=plan
    )
    assert presented.word_highlights is True
    assert presented.source == "words"
    assert any(
        cue.text == "手写台词" and cue.uncertainty == "user-written" and cue.clip_index == 0
        for cue in presented.cues
    )
    assert [cue.text for cue in presented.cues if cue.clip_index == 0] == ["手写台词"]
    assert [cue.text for cue in presented.cues if cue.clip_index == 1] == ["你好", "世界"]
    suppressed = present_subtitles(
        (handwritten,),
        words=words,
        sidecar_available=True,
        plan=plan,
        reserved_clip_indexes=(0, 1),
    )
    assert suppressed.source == "segment"
    assert suppressed.word_highlights is False
    assert [cue.text for cue in suppressed.cues] == ["手写台词"]


def _payload(jobs, root, **extra):
    editor = jobs.edit(root, "hook-first")
    payload = {k: editor[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")}
    payload.update(
        projectId=jobs.read(jobs.directory(root) / "status.json")["projectId"],
        subtitleMode="sidecar",
        clips=[{k: c[k] for k in ("clipId", "startUs", "outputFrames")} for c in editor["clips"]],
        subtitleOverrides=[{"clipId": editor["clips"][0]["clipId"], "text": "手写台词"}],
    )
    payload.update(extra)
    return payload, editor


def test_preview_toggle_off_stays_on_segments_and_skips_loader(revisions, monkeypatch):
    jobs, root, _ = revisions
    payload, _ = _payload(
        jobs, root, wordHighlights=False, asrWords={"runId": "run-1", "resultHash": "a" * 64}
    )
    calls = []

    async def forbidden(project, run_id, result_hash):
        calls.append((run_id, result_hash))
        raise AssertionError("关闭开关时不得去读词级结果")

    monkeypatch.setattr("gamingcreator.infrastructure.asr_words.load_trusted_asr_words", forbidden)
    before = {str(path): path.read_bytes() for path in jobs.repository.rglob("*") if path.is_file()}
    result = preview(jobs, payload)
    assert result["subtitleSource"] == "segment"
    assert result["wordHighlights"] is False
    assert "手写台词" in [cue["text"] for cue in result["cues"]]
    assert calls == []
    after = {str(path): path.read_bytes() for path in jobs.repository.rglob("*") if path.is_file()}
    assert after == before


def test_preview_toggle_on_maps_trusted_words_and_keeps_handwritten(revisions, monkeypatch):
    from gamingcreator.application.creation_editing import validate_revision
    from gamingcreator.application.edit_decision import select_edit_decision
    from gamingcreator.ui.revision_jobs import load_chain, prepare_revision

    jobs, root, _ = revisions
    payload, editor = _payload(jobs, root)
    payload["wordHighlights"] = True
    payload["asrWords"] = {"runId": "run-used", "resultHash": "b" * 64}
    chain = load_chain(jobs, payload["parentJobId"], payload["planId"], read_only=True)
    revised, _ = prepare_revision(jobs, payload, chain)
    plan = validate_revision(
        select_edit_decision(chain.report, chain.plan_id),
        chain.report,
        chain.edl,
        revised,
        chain.timelines,
        chain.root_sha,
    )
    second = plan.clips[1]
    start, end = second.source_range.start_us, second.source_range.end_us
    mid = start + (end - start) // 2
    trusted = (
        AsrWord(second.asset.media_id, SourceRange(start, mid, second.asset.duration_us), "词一"),
        AsrWord(second.asset.media_id, SourceRange(mid, end, second.asset.duration_us), "词二"),
    )
    seen = []

    async def load(project, run_id, result_hash):
        seen.append((run_id, result_hash, project))
        return trusted

    monkeypatch.setattr("gamingcreator.infrastructure.asr_words.load_trusted_asr_words", load)
    before = {str(path): path.read_bytes() for path in jobs.repository.rglob("*") if path.is_file()}
    result = preview(jobs, payload)
    assert seen == [("run-used", "b" * 64, jobs.project(payload["projectId"]))]
    assert result["subtitleSource"] == "words"
    assert result["wordHighlights"] is True
    texts = [cue["text"] for cue in result["cues"]]
    assert "手写台词" in texts
    assert "词一" in texts and "词二" in texts
    first_id = editor["clips"][0]["clipId"]
    assert all(cue["text"] != "词一" or cue.get("clipId") != first_id for cue in result["cues"])
    word_cues = [cue for cue in result["cues"] if cue["text"] in {"词一", "词二"}]
    # sidecar 模式按毫秒量化到微秒，时间必须落在第二段输出时钟上，而不是源微秒原值。
    second_start = word_cues[0]["startUs"]
    assert word_cues[0]["endUs"] > word_cues[0]["startUs"]
    assert word_cues[1]["startUs"] == word_cues[0]["endUs"]
    assert second_start >= 0
    # 关闭后即使仍带着同一份绑定，也回到段级。
    closed = preview(jobs, {**payload, "wordHighlights": False})
    assert closed["subtitleSource"] == "segment"
    assert closed["wordHighlights"] is False
    assert "手写台词" in [cue["text"] for cue in closed["cues"]]
    assert "词一" not in [cue["text"] for cue in closed["cues"]]
    after = {str(path): path.read_bytes() for path in jobs.repository.rglob("*") if path.is_file()}
    assert after == before


def test_preview_missing_or_invalid_binding_stays_on_segments(revisions, monkeypatch):
    jobs, root, _ = revisions
    payload, _ = _payload(
        jobs, root, wordHighlights=True, asrWords={"runId": "run-1", "resultHash": "c" * 64}
    )

    async def missing(project, run_id, result_hash):
        return None

    monkeypatch.setattr("gamingcreator.infrastructure.asr_words.load_trusted_asr_words", missing)
    result = preview(jobs, payload)
    assert result["subtitleSource"] == "segment"
    assert result["wordHighlights"] is False
    assert "手写台词" in [cue["text"] for cue in result["cues"]]
    with pytest.raises(ValueError, match="Expected draft subtitle preview fields"):
        preview(
            jobs,
            {**payload, "asrWords": {"runId": "run-1", "resultHash": "c" * 64, "newest": True}},
        )
    with pytest.raises(ValueError, match="Expected draft subtitle preview fields"):
        preview(jobs, {**payload, "wordHighlights": "yes"})
    # 打开开关但没有绑定，不猜目录里最新的一份。
    unbound = preview(jobs, {k: v for k, v in payload.items() if k != "asrWords"})
    assert unbound["subtitleSource"] == "segment"
    assert unbound["wordHighlights"] is False
