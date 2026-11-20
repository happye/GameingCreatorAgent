# ruff: noqa: F811
import asyncio
import hashlib
from fractions import Fraction
from types import SimpleNamespace

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_render import ROOT, run_tool
from test_creation_subtitles import clip, speech

from gamingcreator.application.asr_word_timing import AsrWord
from gamingcreator.application.creation_subtitles import (
    build_subtitles,
    export_subtitle_tracks,
)
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.cli.creation_render import execute_render_creation
from gamingcreator.domain.creation_subtitles import SubtitleCue, serialize_srt
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.asr_words import parse_word_highlight_request
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer


def test_parse_word_highlight_request_requires_explicit_binding():
    assert parse_word_highlight_request({}) == (False, None)
    assert parse_word_highlight_request({"wordHighlights": False}) == (False, None)
    assert parse_word_highlight_request(
        {"wordHighlights": False, "asrWords": {"runId": "run-1", "resultHash": "abc"}}
    ) == (False, ("run-1", "abc"))
    assert parse_word_highlight_request({"wordHighlights": True}) == (True, None)
    assert parse_word_highlight_request(
        {"wordHighlights": True, "asrWords": {"runId": "run-1", "resultHash": "abc"}}
    ) == (True, ("run-1", "abc"))
    with pytest.raises(ValueError):
        parse_word_highlight_request({"wordHighlights": "yes"})
    with pytest.raises(ValueError):
        parse_word_highlight_request(
            {"asrWords": {"runId": "run-1", "resultHash": "abc", "newest": "x"}}
        )
    with pytest.raises(ValueError):
        parse_word_highlight_request({"asrWords": {"runId": "", "resultHash": "abc"}})


def test_export_subtitle_tracks_keeps_segment_srt_and_maps_words():
    plan = RenderPlan((clip(0, 1_000_000, 10),), 10)
    segment = build_subtitles(plan, (speech(0, 1_000_000, "整段台词"),))
    words = (
        AsrWord(plan.clips[0].asset.media_id, SourceRange(0, 400_000, 1_000_000), "你好"),
        AsrWord(plan.clips[0].asset.media_id, SourceRange(600_000, 1_000_000, 1_000_000), "世界"),
    )
    srt_cues, burn_cues = export_subtitle_tracks(
        segment, words=words, sidecar_available=True, plan=plan
    )
    assert [cue.text for cue in srt_cues] == ["整段台词"]
    assert (srt_cues[0].start, srt_cues[0].end) == (Fraction(0), Fraction(1))
    assert burn_cues is not None
    assert [(cue.text, cue.start, cue.end) for cue in burn_cues] == [
        ("你好", Fraction(0), Fraction(2, 5)),
        ("世界", Fraction(3, 5), Fraction(1)),
    ]
    text = serialize_srt(srt_cues)
    assert "整段台词" in text
    assert "你好" not in text
    none_srt, none_burn = export_subtitle_tracks(segment)
    assert none_burn is None
    assert [cue.text for cue in none_srt] == ["整段台词"]


def test_execute_render_creation_passes_trusted_word_burn_cues(monkeypatch):
    plan = RenderPlan((clip(0, 1_000_000, 10),), 10)
    rows = [{"runId": "run-1"}]
    media_id = plan.clips[0].asset.media_id
    words = (
        AsrWord(media_id, SourceRange(0, 400_000, 1_000_000), "你好"),
        AsrWord(media_id, SourceRange(600_000, 1_000_000, 1_000_000), "世界"),
    )
    runs = {
        "run-1": SimpleNamespace(
            run=SimpleNamespace(run_id="run-1"),
            transcripts=(speech(0, 1_000_000, "整段台词"),),
        )
    }
    captured = {}

    class Store:
        async def load_completed_timeline(self, run):
            return runs[run]

        async def close(self):
            pass

    async def open_store(*args, **kwargs):
        return Store()

    class Renderer:
        async def render(self, *args, **kwargs):
            captured["cues"] = args[-2]
            captured["mode"] = args[-1]
            captured["burn_cues"] = kwargs.get("burn_cues")
            return {"ok": True}

    loaded = {"called": False}

    async def fake_load(project, run_id, result_hash):
        loaded["called"] = True
        loaded["binding"] = (run_id, result_hash)
        return words

    import gamingcreator.cli.creation_render as entry

    monkeypatch.setattr(entry, "read_creation", lambda _: ({"segments": rows}, {}, "hash"))
    monkeypatch.setattr(entry.SqliteTimelineStore, "open", open_store)
    monkeypatch.setattr(entry, "validate_render_plan", lambda *args: plan)
    monkeypatch.setattr("gamingcreator.infrastructure.asr_words.load_trusted_asr_words", fake_load)
    result = asyncio.run(
        execute_render_creation(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            Renderer(),
            320,
            180,
            subtitle_mode="burn",
            word_run_id="run-1",
            word_result_hash="abc",
        )
    )
    assert result == {"ok": True}
    assert loaded == {"called": True, "binding": ("run-1", "abc")}
    assert [cue.text for cue in captured["cues"]] == ["整段台词"]
    assert captured["mode"] == "burn"
    assert [(cue.text, cue.start, cue.end) for cue in captured["burn_cues"]] == [
        ("你好", Fraction(0), Fraction(2, 5)),
        ("世界", Fraction(3, 5), Fraction(1)),
    ]

    captured.clear()
    loaded["called"] = False
    asyncio.run(
        execute_render_creation(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            Renderer(),
            320,
            180,
            subtitle_mode="burn",
        )
    )
    assert loaded["called"] is False
    assert [cue.text for cue in captured["cues"]] == ["整段台词"]
    assert captured["burn_cues"] is None


def test_render_submit_rejects_invalid_word_binding(service):
    payload = {
        "requestId": "render-word-binding",
        "planJobId": "plan-missing",
        "planId": "plan-1",
        "width": 320,
        "height": 180,
        "subtitleMode": "burn",
        "wordHighlights": True,
        "asrWords": {"runId": "run-1", "resultHash": "abc", "newest": "no"},
    }
    with pytest.raises(AppError, match="请填写已核对的词级结果。") as error:
        service.submit("render", payload)
    assert error.value.code == "creation.input"


def test_renderer_burns_word_intervals_and_keeps_segment_srt(tmp_path):
    source = tmp_path / "source.mp4"
    run_tool(
        ["-f", "lavfi", "-i", "color=c=black:s=320x180:r=10:d=2", "-c:v", "libx264", str(source)]
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    async def scenario():
        context = CancellationContext("word-burn-test", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        plan = RenderPlan(
            (RenderClip(asset, SourceRange(0, 2_000_000, asset.duration_us), 20),),
            10,
        )
        segment = (
            SubtitleCue(
                Fraction(1, 5), Fraction(9, 5), "整段台词", uncertainty="asr", clip_index=0
            ),
        )
        words = (
            SubtitleCue(Fraction(3, 10), Fraction(3, 5), "你好", uncertainty="asr", clip_index=0),
            SubtitleCue(Fraction(6, 5), Fraction(3, 2), "世界", uncertainty="asr", clip_index=0),
        )
        output = tmp_path / "burned-words"
        result = await FfmpegCreationRenderer(ROOT).render(
            plan,
            output,
            (source,),
            context,
            320,
            180,
            "",
            segment,
            "burn",
            burn_cues=words,
        )
        assert result["subtitles"]["cueCount"] == 1
        data = (output / "subtitles.srt").read_bytes()
        assert result["files"]["subtitles.srt"] == hashlib.sha256(data).hexdigest()
        assert b"00:00:00,200 --> 00:00:01,800" in data
        assert "整段台词".encode() in data
        assert data.count(b"-->") == 1
        assert "你好".encode() not in data
        assert "世界".encode() not in data
        pixels = run_tool(
            ["-i", str(output / "video.mp4"), "-pix_fmt", "gray", "-f", "rawvideo", "-"]
        )
        frame = 320 * 180
        bright = [sum(v > 100 for v in pixels[i * frame : (i + 1) * frame]) for i in range(20)]
        # Follow the official burn test: skip the first frame of each word window.
        assert max(bright[:3]) == 0
        assert min(bright[4:6]) > 30
        assert max(bright[8:11]) == 0
        assert min(bright[13:15]) > 30
        assert max(bright[16:]) == 0

    asyncio.run(scenario())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
