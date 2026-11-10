"""P030 local beat grid: synthetic tempos, real FFmpeg decode, cache, and the HTTP preview."""

import asyncio
import json
import threading
import urllib.error
import urllib.request
import wave

import numpy as np
import pytest
from test_music_library import library, register  # noqa: F401

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure import music_beats
from gamingcreator.infrastructure.music_beats import RATE, analyze_track, estimate_beats


def clicks(bpm, offset, seconds=20.0, rate=RATE, seed=1):
    rng = np.random.default_rng(seed)
    samples = rng.normal(0, 0.02, int(seconds * rate))
    length = int(0.03 * rate)
    shape = np.exp(-np.arange(length) / (rate / 55)) * np.sin(np.arange(length) * 0.9)
    beat = offset
    while beat < seconds - 0.1:
        start = int(beat * rate)
        samples[start : start + length] += shape
        beat += 60 / bpm
    return samples


@pytest.mark.parametrize("bpm,offset", [(120, 0.3), (97, 0.11), (150, 0.05), (72, 0.4)])
def test_synthetic_tempo_and_phase(bpm, offset):
    grid = estimate_beats(clicks(bpm, offset))
    assert abs(grid["bpm"] - bpm) / bpm < 0.01
    truth = np.arange(offset, 19.9, 60 / bpm)
    found = np.array(grid["beatsUs"][:30]) / 1e6
    assert np.median([np.min(np.abs(truth - t)) for t in found]) < 0.02  # under 20 ms
    assert 0 < grid["confidence"] <= 1


def test_too_short_is_refused():
    with pytest.raises(ValueError):
        estimate_beats(np.zeros(1000))


def write_wav(path, samples, rate=RATE):
    pcm = (np.clip(samples, -1, 1) * 20000).astype("<i2")
    with wave.open(str(path), "wb") as writer:
        writer.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        writer.writeframes(pcm.tobytes())
    return path


def test_real_decode_caches_by_audio_hash(library, tmp_path, monkeypatch):  # noqa: F811
    track = register(library, write_wav(tmp_path / "beat.wav", clicks(100, 0.25, 12)))
    context = CancellationContext("beats", 60)
    grid = asyncio.run(analyze_track(tmp_path, track, context))
    assert abs(grid["bpm"] - 100) < 1 and grid["mediaSha256"] == track.sha256
    assert grid["status"] == "local-estimate-unreviewed"
    assert abs(grid["beatsUs"][0] - 250_000) < 25_000

    async def no_decode(*args, **kwargs):
        raise AssertionError("cached grid must not decode again")

    monkeypatch.setattr(music_beats, "run_media_process", no_decode)
    assert asyncio.run(analyze_track(tmp_path, track, context)) == grid


def test_http_preview_snaps_cuts_and_rejects_unknown_track(library, tmp_path):  # noqa: F811
    from gamingcreator.ui.server import create_server

    track = register(library, write_wav(tmp_path / "beat.wav", clicks(120, 0.0, 12)))
    server = create_server("127.0.0.1", 0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(body):
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/creation/beat-snap",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    clip = {
        "speed": {"numerator": 1, "denominator": 1},
        "transitionIn": {"type": "cut", "frames": 0},
    }
    rows = [
        {"clipId": "a", "startUs": 0, "endUs": 2_200_000, **clip},
        {"clipId": "b", "startUs": 5_000_000, "endUs": 7_300_000, **clip},
    ]
    body = {"fps": 30, "clips": rows, "trackId": track.track_id}
    try:
        preview = post({**body, "trackReceiptSha256": track.receipt_sha256})
        assert abs(preview["bpm"] - 120) < 1.5 and preview["changes"]
        assert preview["afterSeconds"] < preview["beforeSeconds"]
        with pytest.raises(urllib.error.HTTPError) as refused:
            post({**body, "trackReceiptSha256": "0" * 64})
        assert refused.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
