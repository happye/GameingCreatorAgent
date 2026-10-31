"""Exact output clocks and pitch-preserving per-clip speed using pinned native tools."""

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
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer, clip_filter


def test_speed_subtitles_fraction_clock_and_override():
    clips = tuple(
        RenderClip(asset(), SourceRange(1_000_000, 2_000_000, 10_000_000), frames, speed)
        for frames, speed in ((60, Fraction(1, 2)), (15, Fraction(2)))
    )
    plan = RenderPlan(clips, 30)
    cues = build_subtitles(plan, (speech(1_250_000, 1_750_000),))
    assert [(c.start, c.end) for c in cues] == [
        (Fraction(1, 2), Fraction(3, 2)),
        (Fraction(17, 8), Fraction(19, 8)),
    ]
    cues = build_subtitles(plan, (), overrides=("slow", "fast"))
    assert [(c.start, c.end) for c in cues] == [(0, 2), (2, Fraction(5, 2))]
    capped = replace(clips[0], output_frames=40)
    assert build_subtitles(RenderPlan((capped,), 30), (speech(1_250_000, 2_000_000),))[
        0
    ].end == Fraction(4, 3)


@pytest.mark.parametrize("mode", ["pcm", "offset", "delayed", "silent"])
def test_native_speed_frames_pitch_clocks_and_bgm(tmp_path, mode):
    source, track = inputs(tmp_path, sound=False)
    source = tmp_path / "colors.mkv"
    graph = (
        "color=c=red:s=64x48:r=20:d=2[r];color=c=blue:s=64x48:r=20:d=2[b];[r][b]concat=n=2:v=1:a=0"
    )
    args = ["-f", "lavfi", "-i", graph]
    if mode != "silent":
        if mode == "delayed":
            args += ["-itsoffset", "0.5"]
        args += [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-c:a",
            "pcm_s16le",
        ]
    if mode == "offset":
        args += ["-output_ts_offset", "5"]
    tool(*args, "-c:v", "libx264", source)

    async def scenario():
        context = CancellationContext("speed-native", 90)
        media = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        clips = (
            RenderClip(media, SourceRange(0, 2_000_000, media.duration_us), 80, Fraction(1, 2)),
            RenderClip(
                media, SourceRange(2_000_000, 4_000_000, media.duration_us), 20, Fraction(2)
            ),
        )
        plan = RenderPlan(clips, 20)
        assert "atempo" not in clip_filter(replace(clips[0], speed=Fraction(1)), 20, 64, 48)
        for music in (False, True):
            kwargs = (
                {
                    "audio_mix": AudioMix(BgmSelection(track.track_id, track.receipt_sha256, 0)),
                    "music": track,
                }
                if music
                else {}
            )
            directory = tmp_path / ("mixed" if music else "source")
            result = await FfmpegCreationRenderer(TOOLS).render(
                plan, directory, (source,), context, 64, 48, **kwargs
            )
            assert result["frames"] == 100 and result["videoDuration"] == "5"
            pixels = tool(
                "-i",
                directory / "video.mp4",
                "-vf",
                "scale=1:1",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "-",
            )
            assert len(pixels) == 300
            assert all(pixels[i] > pixels[i + 2] + 100 for i in range(0, 240, 3))
            assert all(pixels[i + 2] > pixels[i] + 100 for i in range(240, 300, 3))
            samples = pcm(directory / "video.mp4")
            assert abs(len(samples) - 240000) <= 1024
            assert result["audioStartSeconds"] == "0.000000"
            for start, end in ((1.3, 2), (4.2, 4.7)):
                if mode != "silent":
                    assert amplitude(samples, 440, start, end) > 0.04
                    assert amplitude(samples, 220, start, end) < 0.002
                    assert (
                        amplitude(samples, 880, start, end) > 0.04
                        if music
                        else amplitude(samples, 880, start, end) < 0.002
                    )
            if music:
                assert amplitude(samples, 880, 0.2, 0.7) > 0.04
            if mode == "silent" and not music:
                assert max(map(abs, samples)) == 0
            if mode == "delayed":
                # 0.5 source seconds becomes one second of leading silence.
                assert amplitude(samples, 440, 0.1, 0.8) < 0.001
                edge = next(
                    i / 48000
                    for i in range(40000, 60000, 48)
                    if amplitude(samples, 440, i / 48000, (i + 480) / 48000) > 0.03
                )
                assert abs(edge - 1) <= 1024 / 48000

    asyncio.run(scenario())


@pytest.mark.parametrize("speed", [Fraction(1, 2), Fraction(2)])
def test_native_speed_pulse_edge(tmp_path, speed):
    source, _ = inputs(tmp_path, container="mkv")

    async def scenario():
        context = CancellationContext("speed-pulse", 60)
        media = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        frames = int(3 / speed * 20)
        plan = RenderPlan(
            (RenderClip(media, SourceRange(500_000, 3_500_000, media.duration_us), frames, speed),),
            20,
        )
        await FfmpegCreationRenderer(TOOLS).render(
            plan, tmp_path / "pulse", (source,), context, 64, 48
        )

    asyncio.run(scenario())
    samples = pcm(tmp_path / "pulse/video.mp4")
    original = pcm(source)
    source_edge = next(
        i / 48000
        for i in range(67200, 81600, 48)
        if amplitude(original, 440, i / 48000, (i + 480) / 48000) < 0.005
    )
    expected = (source_edge - 0.5) / float(speed)
    edge = next(
        i / 48000
        for i in range(round((expected - 0.15) * 48000), round((expected + 0.15) * 48000), 48)
        if amplitude(samples, 440, i / 48000, (i + 480) / 48000) < 0.005
    )
    assert abs(edge - expected) <= 1024 / 48000


@pytest.mark.parametrize("speed", [Fraction(1, 2), Fraction(2)])
def test_clip_before_audio_stream_is_exact_silence(tmp_path, speed):
    source = tmp_path / "late.mkv"
    tool(
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=64x48:r=20:d=4",
        "-itsoffset",
        "3",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=1",
        "-c:a",
        "pcm_s16le",
        "-c:v",
        "libx264",
        source,
    )

    async def scenario():
        context = CancellationContext("late-speed", 60)
        media = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        frames = int(2 / speed * 20)
        plan = RenderPlan(
            (RenderClip(media, SourceRange(0, 2_000_000, media.duration_us), frames, speed),), 20
        )
        await FfmpegCreationRenderer(TOOLS).render(
            plan, tmp_path / "late", (source,), context, 64, 48
        )

    asyncio.run(scenario())
    samples = pcm(tmp_path / "late/video.mp4")
    assert abs(len(samples) - int(2 / speed * 48000)) <= 1024
    assert max(map(abs, samples)) == 0


@pytest.mark.parametrize("speed", [Fraction(1), Fraction(1, 2)])
def test_video_shorter_than_audio_pads_full_planned_frames(tmp_path, speed):
    source = tmp_path / "tail.mkv"
    tool(
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=64x48:r=20:d=2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2.75",
        "-c:a",
        "pcm_s16le",
        "-c:v",
        "libx264",
        source,
    )

    async def scenario():
        context = CancellationContext("short-video", 60)
        media = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        frames = int(55 / speed)
        plan = RenderPlan(
            (RenderClip(media, SourceRange(0, 2_750_000, media.duration_us), frames, speed),), 20
        )
        result = await FfmpegCreationRenderer(TOOLS).render(
            plan, tmp_path / "tail", (source,), context, 64, 48
        )
        assert result["frames"] == frames
        assert Fraction(result["videoDuration"]) == Fraction(frames, 20)
        samples = pcm(tmp_path / "tail/video.mp4")
        assert abs(len(samples) - round(frames / 20 * 48000)) <= 1024

    asyncio.run(scenario())


@pytest.mark.parametrize("fps,first_frames,last_frames", [(30, 30, 10), (30, 7, 11), (29, 9, 5)])
def test_concat_uses_frame_duration_and_flushes_final_frame(
    tmp_path, fps, first_frames, last_frames
):
    source = tmp_path / "short-clips.mkv"
    tool(
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=64x48:r=60:d=1[r];color=c=blue:s=64x48:r=60:d=1[b];[r][b]concat=n=2:v=1:a=0",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2",
        "-c:a",
        "pcm_s16le",
        "-c:v",
        "libx264",
        source,
    )

    async def scenario():
        context = CancellationContext("short-concat", 60)
        media = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        clips = (
            RenderClip(
                media, SourceRange(0, 500_000, media.duration_us), first_frames, Fraction(1, 2)
            ),
            RenderClip(
                media,
                SourceRange(1_000_000, 2_000_000, media.duration_us),
                last_frames,
                Fraction(2),
            ),
        )
        total = first_frames + last_frames
        result = await FfmpegCreationRenderer(TOOLS).render(
            RenderPlan(clips, fps), tmp_path / "joined", (source,), context, 64, 48
        )
        assert result["frames"] == total
        assert Fraction(result["videoDuration"]) == Fraction(total, fps)
        pixels = tool(
            "-i",
            tmp_path / "joined/video.mp4",
            "-vf",
            "scale=1:1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        )
        assert len(pixels) == total * 3
        assert all(pixels[i] > pixels[i + 2] + 100 for i in range(0, first_frames * 3, 3))
        assert all(pixels[i + 2] > pixels[i] + 100 for i in range(first_frames * 3, total * 3, 3))
        samples = pcm(tmp_path / "joined/video.mp4")
        assert abs(len(samples) - round(total / fps * 48000)) <= 1024

    asyncio.run(scenario())
