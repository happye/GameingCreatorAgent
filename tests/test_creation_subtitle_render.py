import asyncio
import hashlib
from fractions import Fraction
from types import SimpleNamespace

import pytest
from test_creation_render import ROOT, run_tool
from test_creation_subtitles import clip, speech

from gamingcreator.application.creation_subtitles import build_subtitles
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.cli.creation_render import execute_render_creation
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer, _burn_ass


def test_public_uses_exact_run_per_reordered_clip(monkeypatch, tmp_path):
    import gamingcreator.cli.creation_render as entry

    plan = RenderPlan((clip(2_000_000, 3_000_000, 10), clip(0, 1_000_000, 10)), 10)
    rows = [{"runId": "second"}, {"runId": "first"}]
    runs = {
        key: SimpleNamespace(
            run=SimpleNamespace(run_id=key), transcripts=(speech(0, 4_000_000, key),)
        )
        for key in ("first", "second")
    }

    class Store:
        async def load_completed_timeline(self, run):
            return runs[run]

        async def close(self):
            pass

    async def open_store(*args, **kwargs):
        return Store()

    class Renderer:
        async def render(self, *args):
            cues = args[-2]
            assert [(c.start, c.end, c.text) for c in cues] == [
                (Fraction(0), Fraction(1), "second"),
                (Fraction(1), Fraction(2), "first"),
            ]
            return {"ok": True}

    monkeypatch.setattr(entry, "read_creation", lambda _: ({"segments": rows}, {}, "hash"))
    monkeypatch.setattr(entry.SqliteTimelineStore, "open", open_store)
    monkeypatch.setattr(entry, "validate_render_plan", lambda *args: plan)
    assert asyncio.run(
        execute_render_creation(tmp_path, tmp_path, tmp_path, Renderer(), 320, 180, "sidecar")
    ) == {"ok": True}


def test_ass_control_text_is_literal():
    cue = SubtitleCue(Fraction(0), Fraction(1), r"{\p1}m 0 0 l 100 100\N")
    result = _burn_ass((cue,), 320, 180)
    assert r"{\p1}" not in result
    assert "｛＼p1｝" in result


@pytest.mark.parametrize("mode", ["none", "sidecar", "burn", "empty"])
def test_real_subtitle_render(tmp_path, mode):
    source = tmp_path / "source.mp4"
    run_tool(
        ["-f", "lavfi", "-i", "color=c=black:s=320x180:r=10:d=2", "-c:v", "libx264", str(source)]
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    async def scenario():
        context = CancellationContext("subtitle-test", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        plan = RenderPlan(
            (
                RenderClip(asset, SourceRange(1_000_000, 2_000_000, asset.duration_us), 10),
                RenderClip(asset, SourceRange(0, 1_000_000, asset.duration_us), 10),
            ),
            10,
        )
        transcript = speech(1_200_000, 1_700_000, "本地字幕测试", asset.media_id)
        cues = () if mode == "empty" else build_subtitles(plan, (transcript,))
        output = tmp_path / "Windows path ' quoted,semicolon; [bracket]" / mode
        result = await FfmpegCreationRenderer(ROOT).render(
            plan,
            output,
            (source,),
            context,
            320,
            180,
            "",
            cues,
            "burn" if mode == "empty" else mode,
        )
        assert result["subtitles"]["cueCount"] == (0 if mode in ("none", "empty") else 1)
        if mode != "none":
            data = (output / "subtitles.srt").read_bytes()
            assert result["files"]["subtitles.srt"] == hashlib.sha256(data).hexdigest()
            if mode != "empty":
                assert b"00:00:00,200 --> 00:00:00,700" in data
            else:
                assert data == b""
        else:
            assert not (output / "subtitles.srt").exists()
        pixels = run_tool(
            ["-i", str(output / "video.mp4"), "-pix_fmt", "gray", "-f", "rawvideo", "-"]
        )
        frame = 320 * 180
        bright = [sum(v > 100 for v in pixels[i * frame : (i + 1) * frame]) for i in range(20)]
        if mode == "burn":
            assert max(bright[:2]) == 0
            assert min(bright[3:6]) > 30
            assert max(bright[9:]) == 0
        else:
            assert max(bright) == 0

    asyncio.run(scenario())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_burn_failure_never_publishes_receipt(tmp_path, monkeypatch):
    import gamingcreator.infrastructure.ffmpeg_render as native

    async def fail(*args, **kwargs):
        raise ValueError("decoder failure")

    monkeypatch.setattr(native, "run_media_process", fail)
    output = tmp_path / "failed"
    cue = SubtitleCue(Fraction(0), Fraction(1), "saved words")
    with pytest.raises(ValueError, match="decoder failure"):
        asyncio.run(
            FfmpegCreationRenderer(ROOT).render(
                RenderPlan((clip(0, 1_000_000, 10),), 10),
                output,
                (),
                CancellationContext("failure", 60),
                320,
                180,
                "",
                (cue,),
                "burn",
            )
        )
    assert not (output / "receipt.json").exists()
