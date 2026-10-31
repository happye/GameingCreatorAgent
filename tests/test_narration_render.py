"""Native narration placement, gain, ducking, fit checks and fail-closed identity."""

# ruff: noqa: F811
import asyncio
import hashlib
import json
import math
import wave

import pytest
from test_creation_audio_render import TOOLS, amplitude, inputs, pcm

from gamingcreator.application.narration import NarrationRequest
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_audio import AudioMix, BgmSelection
from gamingcreator.domain.creation_narration import NarrationSelection
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure import sapi_narration as sapi
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer

TEXT = "旁白 <speak> & 测试"


def build(tmp_path, monkeypatch, name="narr", seconds=0.5, hz=660, job="c" * 32):
    """A tiny sine narration made through the real artifact writer with a fake COM engine."""

    async def invoke(mode, request_path, context):
        if mode == "list":
            return json.dumps(
                [{"voiceId": "v", "description": "fixture", "language": "804"}]
            ).encode()
        request = json.loads(request_path.read_text(encoding="utf-8"))
        count = round(seconds * 22050)
        with wave.open(request["wavPath"], "wb") as wav:
            wav.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
            wav.writeframes(
                b"".join(
                    round(16000 * math.sin(2 * math.pi * hz * i / 22050)).to_bytes(
                        2, "little", signed=True
                    )
                    for i in range(count)
                )
            )
        return b"{}"

    monkeypatch.setattr(sapi, "_invoke", invoke)
    return asyncio.run(
        sapi.synthesize_local_narration(
            NarrationRequest("req", "project", TEXT, "v"),
            tmp_path / name,
            CancellationContext(job, 30),
        )
    )


def select(artifact, start=0, gain=0, duck="off", job="c" * 32):
    return NarrationSelection(job, artifact.receipt_sha256, start, float(gain), duck)


async def render(source, output, artifact, selection, track=None, mix=None, **kwargs):
    context = CancellationContext("narration-native", 90)
    asset = await FfmpegMediaProcessor(TOOLS).probe(source, context)
    plan = RenderPlan((RenderClip(asset, SourceRange(0, 4_000_000, asset.duration_us), 40),), 10)
    return await FfmpegCreationRenderer(TOOLS).render(
        plan,
        output,
        (source,),
        context,
        64,
        48,
        audio_mix=mix,
        music=track,
        narration=selection,
        narration_artifact=artifact,
        **kwargs,
    )


def span(samples, hz, window=0.01, floor=0.1):
    hits = [
        i
        for i in range(len(samples) // 480)
        if amplitude(samples, hz, i * window, (i + 1) * window) > floor
    ]
    return hits[0] * window, (hits[-1] + 1) * window


def db(a, b):
    return 20 * math.log10(a / b)


@pytest.mark.parametrize("start", [0, 12])
def test_start_frame_places_tone_without_changing_video_clock(tmp_path, monkeypatch, start):
    source, _ = inputs(tmp_path, sound=False)
    artifact = build(tmp_path, monkeypatch)
    before = (source.read_bytes(), artifact.wav_path.read_bytes())
    result = asyncio.run(render(source, tmp_path / "out", artifact, select(artifact, start)))
    samples = pcm(tmp_path / "out/video.mp4")
    assert result["frames"] == 40 and result["videoDuration"] == "4"
    assert abs(len(samples) - 4 * 48000) <= 1024
    begin, end = span(samples, 660)
    assert abs(begin - start / 10) <= 0.03 and abs(end - (start / 10 + 0.5)) <= 0.03
    assert amplitude(samples, 660, begin + 0.05, end - 0.05) == pytest.approx(0.49, abs=0.06)
    assert result["narration"]["startSample"] == start * 4800
    assert before == (source.read_bytes(), artifact.wav_path.read_bytes())


def test_narration_that_exactly_fits_the_end_is_accepted(tmp_path, monkeypatch):
    source, _ = inputs(tmp_path, sound=False)
    artifact = build(tmp_path, monkeypatch)
    asyncio.run(render(source, tmp_path / "out", artifact, select(artifact, 35)))
    samples = pcm(tmp_path / "out/video.mp4")
    begin, end = span(samples, 660)
    assert abs(begin - 3.5) <= 0.03 and abs(end - 4) <= 0.03
    assert abs(len(samples) - 4 * 48000) <= 1024


def test_gain_changes_narration_amplitude_per_db(tmp_path, monkeypatch):
    source, _ = inputs(tmp_path)
    artifact = build(tmp_path, monkeypatch)
    levels = {}
    for gain in (0, -6, -20):
        asyncio.run(render(source, tmp_path / f"g{-gain}", artifact, select(artifact, 20, gain)))
        levels[gain] = amplitude(pcm(tmp_path / f"g{-gain}/video.mp4"), 660, 2.1, 2.4)
    assert db(levels[-6], levels[0]) == pytest.approx(-6, abs=0.5)
    assert db(levels[-20], levels[0]) == pytest.approx(-20, abs=1)


def test_ducking_lowers_source_only_while_narration_plays(tmp_path, monkeypatch):
    source, _ = inputs(tmp_path)
    artifact = build(tmp_path, monkeypatch)
    for name, duck in (("off", "off"), ("on", "narration-v1")):
        asyncio.run(render(source, tmp_path / name, artifact, select(artifact, 5, 0, duck)))
    off, on = pcm(tmp_path / "off/video.mp4"), pcm(tmp_path / "on/video.mp4")
    # Source sine plays until 1.5 s; narration covers 0.5..1.0 s.
    assert db(amplitude(on, 440, 0.7, 0.95), amplitude(off, 440, 0.7, 0.95)) <= -10
    assert db(amplitude(on, 440, 1.25, 1.45), amplitude(off, 440, 1.25, 1.45)) == pytest.approx(
        0, abs=2
    )
    assert db(amplitude(on, 440, 0.1, 0.4), amplitude(off, 440, 0.1, 0.4)) == pytest.approx(
        0, abs=1
    )
    assert db(amplitude(on, 660, 0.6, 0.95), amplitude(off, 660, 0.6, 0.95)) == pytest.approx(
        0, abs=1
    )


def test_source_bgm_and_narration_mix_together(tmp_path, monkeypatch):
    source, track = inputs(tmp_path, music_duration=0.25)
    artifact = build(tmp_path, monkeypatch)
    mix = AudioMix(BgmSelection(track.track_id, track.receipt_sha256, 0))
    for name, duck in (("off", "off"), ("on", "narration-v1")):
        asyncio.run(
            render(source, tmp_path / name, artifact, select(artifact, 5, 0, duck), track, mix)
        )
    off, on = pcm(tmp_path / "off/video.mp4"), pcm(tmp_path / "on/video.mp4")
    assert abs(len(off) - 4 * 48000) <= 1024
    for samples in (off, on):
        assert amplitude(samples, 660, 0.6, 0.95) > 0.2
        assert amplitude(samples, 880, 2.1, 2.8) > 0.04  # BGM after narration and source
    assert amplitude(off, 440, 0.2, 0.4) > 0.04 and amplitude(off, 880, 0.2, 0.4) > 0.04
    assert db(amplitude(on, 440, 0.7, 0.95), amplitude(off, 440, 0.7, 0.95)) <= -10
    assert db(amplitude(on, 880, 0.7, 0.95), amplitude(off, 880, 0.7, 0.95)) <= -10
    assert db(amplitude(on, 880, 3.1, 3.8), amplitude(off, 880, 3.1, 3.8)) == pytest.approx(
        0, abs=1
    )


def test_silent_source_without_bgm_renders_narration(tmp_path, monkeypatch):
    source, _ = inputs(tmp_path, sound=False)
    artifact = build(tmp_path, monkeypatch)
    asyncio.run(
        render(source, tmp_path / "out", artifact, select(artifact, 10, -3, "narration-v1"))
    )
    samples = pcm(tmp_path / "out/video.mp4")
    assert amplitude(samples, 660, 1.1, 1.4) > 0.2
    assert amplitude(samples, 440, 0.2, 0.8) < 0.001


@pytest.mark.parametrize("start", [38, 40, 400])
def test_overlong_narration_is_rejected_before_any_output(tmp_path, monkeypatch, start):
    source, _ = inputs(tmp_path, sound=False)
    artifact = build(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Narration lasts|nonnegative|available"):
        asyncio.run(render(source, tmp_path / "out", artifact, select(artifact, start)))
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("when", ["before", "during"])
@pytest.mark.parametrize("target", ["narration.wav", "narration.txt"])
def test_tampered_asset_is_rejected(tmp_path, monkeypatch, when, target):
    from gamingcreator.infrastructure import ffmpeg_render

    source, _ = inputs(tmp_path, sound=False)
    artifact = build(tmp_path, monkeypatch)
    selection = select(artifact, 0)
    path = artifact.directory / target
    original = ffmpeg_render.run_media_process

    def tamper():
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)

    if when == "before":
        tamper()
    else:

        async def changed(arguments, context, **kwargs):
            result = await original(arguments, context, **kwargs)
            if "-count_frames" in arguments:
                tamper()
            return result

        monkeypatch.setattr(ffmpeg_render, "run_media_process", changed)
    with pytest.raises(ValueError):
        asyncio.run(render(source, tmp_path / "out", artifact, selection))
    assert not (tmp_path / "out/receipt.json").exists()
    assert not (tmp_path / "out/video.mp4").exists()


def test_selection_identity_and_pairing_fail_closed(tmp_path, monkeypatch):
    source, _ = inputs(tmp_path, sound=False)
    artifact = build(tmp_path, monkeypatch)
    wrong_job = select(artifact, job="d" * 32)
    wrong_digest = NarrationSelection("c" * 32, "0" * 64, 0, 0.0, "off")
    for selection in (wrong_job, wrong_digest):
        with pytest.raises(ValueError):
            asyncio.run(render(source, tmp_path / "out", artifact, selection))
    with pytest.raises(ValueError, match="together"):
        asyncio.run(render(source, tmp_path / "out", None, select(artifact)))
    with pytest.raises(ValueError, match="together"):
        asyncio.run(render(source, tmp_path / "out", artifact, None))
    with pytest.raises(ValueError, match="outside all input"):
        asyncio.run(render(source, artifact.directory / "out", artifact, select(artifact)))
    assert not (artifact.directory / "out").exists() and not (tmp_path / "out").exists()


def test_receipt_records_narration_text_hash_and_unknown_license(tmp_path, monkeypatch):
    source, _ = inputs(tmp_path, sound=False)
    artifact = build(tmp_path, monkeypatch)
    selection = select(artifact, 7, -3, "narration-v1")
    result = asyncio.run(render(source, tmp_path / "out", artifact, selection))
    receipt = json.loads((tmp_path / "out/receipt.json").read_text(encoding="utf-8"))
    text = (tmp_path / "out/narration.txt").read_bytes()
    assert text == TEXT.encode() == artifact.text_path.read_bytes()
    assert set(receipt["files"]) == {"video.mp4", "narration.txt"}
    assert receipt["files"]["narration.txt"] == hashlib.sha256(text).hexdigest()
    block = receipt["narration"]
    assert block == result["narration"]
    assert block["selection"] == selection.to_json()
    assert block["licenseStatus"] == "unknown"
    assert block["startSample"] == 7 * 4800 and block["rounding"] == "nearest-ties-to-even-48000"
    assert block["sampleCount"] == artifact.sample_count and block["sampleRate"] == 22050
    assert block["wavSha256"] == artifact.wav_sha256 and block["textSha256"] == artifact.text_sha256
    assert block["assetReceiptSha256"] == artifact.receipt_sha256
    assert block["voice"]["voiceId"] == "v" and block["voice"]["engine"] == "windows-sapi"


def test_render_without_narration_is_unchanged(tmp_path):
    source, _ = inputs(tmp_path)

    async def scenario():
        context = CancellationContext("plain", 90)
        asset = await FfmpegMediaProcessor(TOOLS).probe(source, context)
        plan = RenderPlan(
            (RenderClip(asset, SourceRange(0, 4_000_000, asset.duration_us), 40),), 10
        )
        return await FfmpegCreationRenderer(TOOLS).render(
            plan, tmp_path / "plain", (source,), context, 64, 48
        )

    result = asyncio.run(scenario())
    assert "narration" not in result and set(result["files"]) == {"video.mp4"}
    assert not (tmp_path / "plain/narration.txt").exists()
