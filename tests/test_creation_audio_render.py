"""Native soundtrack signal, timing and fail-closed identity checks."""

import array
import asyncio
import hashlib
import math
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_audio import AudioMix, BgmSelection
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.infrastructure.music_library import MusicTrack

ROOT = Path(__file__).resolve().parents[1]
# Worktrees share the repository's pinned, read-only toolchain.
TOOLS = ROOT if (ROOT / ".tools/ffmpeg/bin/ffmpeg.exe").exists() else ROOT.parents[2]
FFMPEG = TOOLS / ".tools/ffmpeg/bin/ffmpeg.exe"


def tool(*args):
    return subprocess.run(
        [str(FFMPEG), "-v", "error", "-nostdin", "-n", *map(str, args)],
        check=True,
        capture_output=True,
    ).stdout


def pcm(path):
    return array.array("f", tool("-i", path, "-vn", "-ar", "48000", "-ac", "1", "-f", "f32le", "-"))


def amplitude(samples, hz, start=0.2, end=0.8):
    values = samples[round(start * 48000) : round(end * 48000)]
    real = sum(x * math.cos(2 * math.pi * hz * i / 48000) for i, x in enumerate(values))
    imag = sum(x * math.sin(2 * math.pi * hz * i / 48000) for i, x in enumerate(values))
    return 2 * math.hypot(real, imag) / len(values)


def inputs(tmp_path, sound=True, music_duration=0.25, container="mp4"):
    codec = "pcm_s16le" if container == "mkv" else "aac"
    source = tmp_path / f"source.{container}"
    args = ["-f", "lavfi", "-i", "color=c=red:s=64x48:r=10:d=4"]
    if sound:
        args += [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-af",
            "volume=enable='gte(t,1.5)':volume=0",
            "-c:a",
            codec,
        ]
    tool(*args, "-c:v", "libx264", source)
    directory = tmp_path / ("a" * 32)
    directory.mkdir()
    path = directory / "audio.wav"
    tool(
        "-f", "lavfi", "-i", f"sine=frequency=880:sample_rate=48000:duration={music_duration}", path
    )
    receipt = directory / "receipt.json"
    receipt.write_text('{"licenseStatus":"test_only"}', encoding="utf-8")
    track = MusicTrack(
        "a" * 32,
        "test tone",
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        hashlib.sha256(receipt.read_bytes()).hexdigest(),
        round(music_duration * 1e6),
        "test_only",
        "synthetic test tone",
    )
    return source, track


async def render(source, track, output, gain=0, duck="off", source_gain=0):
    context = CancellationContext("audio-native", 90)
    asset = await FfmpegMediaProcessor(TOOLS).probe(source, context)
    plan = RenderPlan((RenderClip(asset, SourceRange(0, 4_000_000, asset.duration_us), 40),), 10)
    mix = AudioMix(BgmSelection(track.track_id, track.receipt_sha256, gain), source_gain, duck)
    return await FfmpegCreationRenderer(TOOLS).render(
        plan, output, (source,), context, 64, 48, audio_mix=mix, music=track
    )


@pytest.mark.parametrize("sound,music_duration", [(True, 0.25), (False, 7)])
def test_native_mix_loop_trim_gain_and_clocks(tmp_path, sound, music_duration):
    source, track = inputs(tmp_path, sound, music_duration)
    before = (hashlib.sha256(source.read_bytes()).hexdigest(), track.path.read_bytes())
    result = asyncio.run(render(source, track, tmp_path / "full"))
    asyncio.run(render(source, track, tmp_path / "half", gain=-6))
    full, half = pcm(tmp_path / "full/video.mp4"), pcm(tmp_path / "half/video.mp4")
    assert result["frames"] == 40 and result["videoDuration"] == "4"
    assert result["audioStartSeconds"] == "0.000000"
    assert abs(len(full) - 4 * 48000) <= 1024
    assert amplitude(full, 880) > 0.04
    assert (amplitude(full, 440) > 0.04) if sound else (amplitude(full, 440) < 0.001)

    # Quiet source window measures the soundtrack gain without cross-frequency leakage.
    def rms(samples):
        return math.sqrt(sum(x * x for x in samples[96000:144000]) / 48000)

    assert 20 * math.log10(rms(half) / rms(full)) == pytest.approx(-6, abs=0.5)
    assert amplitude(full, 880, 3.1, 3.8) > 0.04
    assert result["music"]["licenseStatus"] == "test_only"
    assert result["mixPolicy"]["normalize"] is False
    assert before == (hashlib.sha256(source.read_bytes()).hexdigest(), track.path.read_bytes())


def test_native_duck_releases_and_source_gain(tmp_path):
    source, track = inputs(tmp_path)
    asyncio.run(render(source, track, tmp_path / "base"))
    asyncio.run(render(source, track, tmp_path / "duck", duck="source-v1"))
    asyncio.run(render(source, track, tmp_path / "source-half", source_gain=-6))
    base, duck, attenuated = (
        pcm(tmp_path / f"{name}/video.mp4") for name in ("base", "duck", "source-half")
    )
    assert 20 * math.log10(amplitude(duck, 880) / amplitude(base, 880)) <= -6
    assert 20 * math.log10(
        amplitude(duck, 880, 3, 3.8) / amplitude(base, 880, 3, 3.8)
    ) == pytest.approx(0, abs=1)
    assert 20 * math.log10(amplitude(attenuated, 440) / amplitude(base, 440)) == pytest.approx(
        -6, abs=0.5
    )

    # Existing source cut at 1.5 seconds survives the mixing/limiter delay compensation.
    def edge(samples):
        return next(
            i / 48000
            for i in range(60000, 85000, 480)
            if amplitude(samples, 440, i / 48000, (i + 2400) / 48000) < 0.005
        )

    assert abs(edge(duck) - edge(base)) <= 1024 / 48000


@pytest.mark.parametrize("fault", ["media", "receipt", "identity", "cancel"])
def test_music_errors_never_publish_completed(tmp_path, fault):
    source, track = inputs(tmp_path)
    if fault == "media":
        track.path.write_bytes(b"broken")
    elif fault == "receipt":
        (track.path.parent / "receipt.json").write_text("broken")
    elif fault == "identity":
        track = replace(track, track_id="b" * 32)

    async def scenario():
        context = CancellationContext("failed-audio", 60)
        asset = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        plan = RenderPlan(
            (RenderClip(asset, SourceRange(0, 1_000_000, asset.duration_us), 10),), 10
        )
        mix = AudioMix(BgmSelection("a" * 32, track.receipt_sha256, 0))
        if fault == "cancel":
            context.cancelled.set()
        with pytest.raises((ValueError, asyncio.CancelledError)):
            await FfmpegCreationRenderer(TOOLS).render(
                plan, tmp_path / "failed", (), context, 64, 48, audio_mix=mix, music=track
            )

    asyncio.run(scenario())
    assert not (tmp_path / "failed/receipt.json").exists()


def test_silent_source_does_not_duck_and_default_keeps_source(tmp_path):
    source, track = inputs(tmp_path, sound=False)
    asyncio.run(render(source, track, tmp_path / "off"))
    asyncio.run(render(source, track, tmp_path / "on", duck="source-v1"))
    off, on = pcm(tmp_path / "off/video.mp4"), pcm(tmp_path / "on/video.mp4")
    assert 20 * math.log10(amplitude(on, 880) / amplitude(off, 880)) == pytest.approx(0, abs=0.1)


def test_default_compatibility_and_invalid_constructed_mix(tmp_path):
    source, _ = inputs(tmp_path)

    async def scenario():
        context = CancellationContext("default-audio", 90)
        asset = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        plan = RenderPlan(
            (RenderClip(asset, SourceRange(0, 4_000_000, asset.duration_us), 40),), 10
        )
        renderer = FfmpegCreationRenderer(TOOLS)
        await renderer.render(plan, tmp_path / "old", (source,), context, 64, 48)
        await renderer.render(
            plan, tmp_path / "default", (source,), context, 64, 48, audio_mix=AudioMix()
        )
        assert pcm(tmp_path / "old/video.mp4") == pcm(tmp_path / "default/video.mp4")
        for index, value in enumerate((True, float("nan"), float("inf"), 1, -61)):
            invalid = AudioMix()
            object.__setattr__(invalid, "source_gain_db", value)
            with pytest.raises(ValueError):
                await renderer.render(
                    plan, tmp_path / f"invalid-{index}", (), context, 64, 48, audio_mix=invalid
                )
            assert not (tmp_path / f"invalid-{index}").exists()

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["media", "receipt", "process"])
def test_changed_music_during_render_and_processing_failure(tmp_path, monkeypatch, fault):
    from gamingcreator.infrastructure import ffmpeg_render

    source, track = inputs(tmp_path)
    original = ffmpeg_render.run_media_process

    async def changed(arguments, context, **kwargs):
        if fault == "process":
            raise ValueError("Simulated media processing failure")
        result = await original(arguments, context, **kwargs)
        if "-count_frames" in arguments:
            path = track.path if fault == "media" else track.path.parent / "receipt.json"
            path.write_bytes(b"changed during rendering")
        return result

    monkeypatch.setattr(ffmpeg_render, "run_media_process", changed)
    with pytest.raises(ValueError):
        asyncio.run(render(source, track, tmp_path / "changed"))
    assert not (tmp_path / "changed/receipt.json").exists()


def test_music_directory_cannot_be_render_destination(tmp_path):
    source, track = inputs(tmp_path)
    with pytest.raises(ValueError, match="outside all input"):
        asyncio.run(render(source, track, track.path.parent / "output"))
    assert not (track.path.parent / "output").exists()


@pytest.mark.parametrize("with_music", [False, True])
def test_matroska_pcm_source_clock_trim_and_pulse(tmp_path, with_music):
    source, track = inputs(tmp_path, container="mkv")

    async def scenario():
        context = CancellationContext("pcm-clock", 90)
        asset = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        assert next(s for s in asset.streams if s.kind == "audio").time_base.denominator == 1000
        plan = RenderPlan(
            (RenderClip(asset, SourceRange(500_000, 3_500_000, asset.duration_us), 30),), 10
        )
        kwargs = {}
        if with_music:
            kwargs = {
                "audio_mix": AudioMix(BgmSelection(track.track_id, track.receipt_sha256, 0)),
                "music": track,
            }
        return await FfmpegCreationRenderer(TOOLS).render(
            plan, tmp_path / "pcm", (source,), context, 64, 48, **kwargs
        )

    result = asyncio.run(scenario())
    original, rendered = pcm(source), pcm(tmp_path / "pcm/video.mp4")
    assert result["frames"] == 30 and result["videoDuration"] == "3"
    assert abs(len(rendered) - 144000) <= 1024
    assert amplitude(rendered, 440, 0.2, 0.7) > 0.04
    assert amplitude(rendered, 440, 1.4, 2) < 0.001

    def edge(samples, begin):
        return next(
            i / 48000
            for i in range(round(begin * 48000), round((begin + 0.3) * 48000), 48)
            if amplitude(samples, 440, i / 48000, (i + 2400) / 48000) < 0.005
        )

    assert abs(edge(original, 1.35) - 0.5 - edge(rendered, 0.85)) <= 1024 / 48000
    if with_music:
        assert amplitude(rendered, 880, 2.1, 2.8) > 0.04
