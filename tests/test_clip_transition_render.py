"""Pinned native crossfade pixels, signal, exact layout and subtitle overlap."""

import asyncio
from dataclasses import replace
from fractions import Fraction

import pytest
from test_creation_audio_render import TOOLS, amplitude, inputs, pcm, tool
from test_creation_subtitles import asset, speech

from gamingcreator.application.creation_subtitles import build_subtitles
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_audio import AudioMix, BgmSelection
from gamingcreator.domain.creation_subtitles import SubtitleCue, parse_srt, serialize_srt
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer, _burn_ass


def test_subtitle_overlap_and_lanes():
    plan = RenderPlan(
        tuple(RenderClip(asset(), SourceRange(0, 1_000_000, 10_000_000), 30) for _ in range(2)),
        30,
        (0, 6),
    )
    cues = build_subtitles(plan, (speech(0, 1_000_000),), overrides=(None, "same"))
    assert [(c.start, c.end, c.clip_index) for c in cues] == [
        (0, 1, 0),
        (Fraction(4, 5), Fraction(9, 5), 1),
    ]
    assert len(parse_srt(serialize_srt(cues))) == 2
    ass = _burn_ass(cues, 640, 480)
    assert "0:00:00.80,0:00:01.00,Default,,0,0,60" in ass
    assert "0:00:00.00,0:00:00.80,Default,,0,0,4" in ass
    identical = tuple(replace(cue, text="same\nline") for cue in cues)
    assert r"same\Nline" in _burn_ass(identical, 640, 480)
    assert ",0,0,60,," in _burn_ass(identical, 640, 480)


@pytest.mark.parametrize("silent,music", [(False, False), (True, False), (False, True)])
def test_native_red_blue_transition(tmp_path, silent, music):
    _, track = inputs(tmp_path)
    paths = []
    for color, frequency in (("red", 440), ("blue", 660)):
        path = tmp_path / f"{color}.mkv"
        args = ["-f", "lavfi", "-i", f"color=c={color}:s=64x48:r=30:d=1"]
        if not silent:
            args += [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:sample_rate=48000:duration=1",
                "-c:a",
                "pcm_s16le",
            ]
        tool(*args, "-c:v", "libx264", path)
        paths.append(path)

    async def scenario():
        context = CancellationContext("transition-native", 90)
        assets = [await FfmpegMediaProcessor(TOOLS).probe(p, context) for p in paths]
        clips = tuple(RenderClip(a, SourceRange(0, 1_000_000, a.duration_us), 30) for a in assets)
        plan = RenderPlan(clips, 30, (0, 6))
        assert plan.start_frames == (0, 24) and plan.frames == 54
        kwargs = (
            {
                "audio_mix": AudioMix(
                    BgmSelection(track.track_id, track.receipt_sha256, 0), 0, "source-v1"
                ),
                "music": track,
            }
            if music
            else {}
        )
        cues = (
            SubtitleCue(Fraction(0), Fraction(1), "same", clip_index=0),
            SubtitleCue(Fraction(4, 5), Fraction(9, 5), "same", clip_index=1),
        )
        output = tmp_path / "render"
        result = await FfmpegCreationRenderer(TOOLS).render(
            plan,
            output,
            tuple(paths),
            context,
            64,
            48,
            cues=cues,
            subtitle_mode="sidecar",
            **kwargs,
        )
        assert result["frames"] == 54 and result["videoDuration"] == "9/5"
        pixels = tool(
            "-i",
            output / "video.mp4",
            "-vf",
            "scale=1:1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        )
        assert len(pixels) == 54 * 3
        assert pixels[20 * 3] > 200 and pixels[35 * 3 + 2] > 200
        assert pixels[27 * 3] > 70 and pixels[27 * 3 + 2] > 70
        samples = pcm(output / "video.mp4")
        assert abs(len(samples) - 86400) <= 1024
        if silent:
            assert max(map(abs, samples)) == 0
        else:
            assert amplitude(samples, 440, 0.83, 0.97) > 0.02
            assert amplitude(samples, 660, 0.83, 0.97) > 0.02
            assert amplitude(samples, 660, 0.2, 0.6) < 0.003
            assert amplitude(samples, 440, 1.2, 1.6) < 0.003
        assert len(parse_srt((output / "subtitles.srt").read_text())) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("transitions", [(0, 6, 0), (0, 0, 6), (0, 6, 6)])
def test_native_three_clip_mixed_speed_burn(tmp_path, transitions):
    source, _ = inputs(tmp_path, container="mkv")

    async def scenario():
        context = CancellationContext("transition-speed", 90)
        media = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        clips = tuple(
            RenderClip(media, SourceRange(0, 1_000_000, media.duration_us), frames, speed)
            for frames, speed in ((60, Fraction(1, 2)), (15, Fraction(2)), (30, Fraction(1)))
        )
        plan = RenderPlan(clips, 30, transitions)
        cues = build_subtitles(
            plan,
            (replace(speech(0, 1_000_000), media_id=media.media_id),),
            overrides=(None, "second", "third"),
        )
        output = tmp_path / "burn"
        result = await FfmpegCreationRenderer(TOOLS).render(
            plan, output, (source,), context, 320, 180, cues=cues, subtitle_mode="burn"
        )
        assert result["frames"] == 105 - sum(transitions)
        assert abs(len(pcm(output / "video.mp4")) - round(plan.frames / 30 * 48000)) <= 1024
        assert len(parse_srt((output / "subtitles.srt").read_text())) == 3
        assert not list(output.glob("*.nut"))

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_join_failure_cleans_partial_files(tmp_path, monkeypatch, cancel):
    from gamingcreator.infrastructure import crossfade_render

    clips = tuple(RenderClip(asset(), SourceRange(0, 1_000_000, 10_000_000), 30) for _ in range(2))
    parts = [tmp_path / "first.nut", tmp_path / "second.nut"]

    async def fail(command, context, **kwargs):
        from pathlib import Path

        Path(command[-1]).write_bytes(b"partial")
        if cancel:
            raise asyncio.CancelledError()
        raise ValueError("synthetic process failure")

    monkeypatch.setattr(crossfade_render, "run_media_process", fail)
    with pytest.raises(asyncio.CancelledError if cancel else ValueError):
        asyncio.run(
            crossfade_render.compose_transitions(
                "fixed", RenderPlan(clips, 30, (0, 6)), parts, CancellationContext("fail", 30)
            )
        )
    assert not list(tmp_path.glob("join-*.nut"))
    assert not (tmp_path / "receipt.json").exists()
