"""P030 local beat grid: synthetic tempos, real FFmpeg decode, cache, and the HTTP preview."""

import asyncio
import json
import subprocess
import threading
import urllib.error
import urllib.request
import wave

import numpy as np
import pytest
from test_music_library import library, register  # noqa: F401

from gamingcreator.application.ad_music_match import match_beats, match_drop, rank_matches
from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure import music_beats
from gamingcreator.infrastructure.music_annotations import save_annotation
from gamingcreator.infrastructure.music_beats import RATE, analyze_track, estimate_beats
from gamingcreator.ui.ad_music_matches import ad_music_matches


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


@pytest.mark.parametrize("frequency", [0, 20, 440, 941])
def test_sustained_tone_does_not_get_a_credible_tempo(frequency):
    samples = 0.2 * np.sin(2 * np.pi * frequency * np.arange(8 * RATE) / RATE)
    assert estimate_beats(samples) == {"bpm": None, "beatsUs": [], "confidence": 0.0}


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
        refused.value.close()  # an unread error response still holds its socket
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_ad_match_uses_loop_phase_and_refuses_unmeasured_or_unreliable_cuts():
    grid = {
        "bpm": 120,
        "confidence": 0.6,
        "beatsUs": [300_000, 800_000, 1_300_000, 1_800_000],
        "analyzedSeconds": 2,
    }
    cuts = [315_000, 1_900_000, 2_400_000, 3_320_000]
    partial = match_beats(grid, cuts)
    assert partial == {"bpm": 120, "nearCuts": 1, "checkedCuts": 2, "totalCuts": 4}
    looped = match_beats({**grid, "complete": True}, cuts)
    assert looped == {"bpm": 120, "nearCuts": 2, "checkedCuts": 4, "totalCuts": 4}
    assert match_beats({**grid, "confidence": 0.01}, cuts)["bpm"] is None


def test_annotated_drop_does_not_invent_audio_outside_a_measured_window():
    grid = {"analyzedSeconds": 4.0, "complete": False}
    assert match_drop(grid, 1_000_000, 5_050_000, 6_000_000) is None
    assert match_drop(grid, 6_000_000, 1_000_000, 2_000_000) is None
    assert match_drop(grid, 1_000_000, 950_000, 2_000_000) == 50_000
    complete = {**grid, "complete": True}
    assert match_drop(complete, 1_000_000, 5_050_000, 6_000_000) == 50_000
    assert match_drop(complete, 1_000_000, 4_900_000, 5_000_000) == 3_900_000
    assert match_drop(complete, 2_000_000, 1_000_000, 2_000_000) is None


def test_annotated_energy_can_rank_tracks_without_detected_beats():
    weak = {"energy": 25, "bpm": None, "nearCuts": 0, "checkedCuts": 0}
    strong = {**weak, "energy": 85}
    assert rank_matches([weak, strong], "intense") == [strong, weak]


def test_inflight_matching_refuses_an_updated_annotation(library, tmp_path, monkeypatch):  # noqa: F811
    from gamingcreator.ui import ad_music_matches as endpoint

    async def scenario():
        path = write_wav(tmp_path / "beat.wav", clicks(80, 0.1, 5))
        track = await library.register(
            path, "验证曲", "本机合成", "user_declared", None, CancellationContext("test", 30)
        )
        first = save_annotation(track, {"moods": ["calm"], "energy": 20, "dropUs": None}, None)

        async def analyze(*args, **kwargs):
            save_annotation(
                track,
                {"moods": ["lively"], "energy": 80, "dropUs": None},
                first["annotationSha256"],
            )
            return {"analyzedSeconds": 5, "confidence": 0, "beatsUs": []}

        monkeypatch.setattr(endpoint, "analyze_track", analyze)
        with pytest.raises(ValueError, match="请刷新"):
            await ad_music_matches(
                tmp_path,
                {
                    "durationUs": 3_000_000,
                    "cutUs": [],
                    "pace": "cuts",
                    "mood": "calm",
                    "tracks": [
                        {"trackId": track.track_id, "trackReceiptSha256": track.receipt_sha256},
                    ],
                },
            )

    asyncio.run(scenario())


def test_ad_match_ranks_two_real_tempos_without_promoting_silence(library, tmp_path):  # noqa: F811
    async def scenario():
        tracks = []
        registered = []
        context = CancellationContext("test-ad-match", 50)
        for name, samples in (
            ("calm", clicks(80, 0.25, 9)),
            ("fast", clicks(150, 0.10, 9)),
            ("silent", np.zeros(9 * RATE)),
        ):
            path = write_wav(tmp_path / f"{name}.wav", samples)
            track = await library.register(
                path, name, "本机合成验证", "user_declared", None, context
            )
            registered.append(track)
            tracks.append({"trackId": track.track_id, "trackReceiptSha256": track.receipt_sha256})
        value = {"durationUs": 8_000_000, "cutUs": [500_000, 900_000, 1_300_000], "tracks": tracks}
        for pace, expected in (("cuts", 1), ("calm", 0), ("intense", 1)):
            result = await ad_music_matches(tmp_path, {**value, "pace": pace})
            suggestions = result["suggestions"]
            assert suggestions[0]["trackId"] == tracks[expected]["trackId"]
            assert suggestions[-1]["bpm"] is None
        mark = save_annotation(
            registered[0], {"moods": ["playful"], "energy": 25, "dropUs": 5_900_000}, None
        )
        save_annotation(
            registered[1], {"moods": ["dramatic"], "energy": 90, "dropUs": 4_000_000}, None
        )
        selected = await ad_music_matches(
            tmp_path, {**value, "pace": "intense", "mood": "playful", "highlightUs": 6_000_000}
        )
        first = selected["suggestions"][0]
        assert first["trackId"] == tracks[0]["trackId"] and first["dropGapUs"] == 100_000
        assert (
            first["moodMatch"]
            and first["energy"] == 25
            and first["annotationSha256"] == mark["annotationSha256"]
        )
        unavailable = await library.register(
            path, "不参与推荐", "本机合成验证", "unknown", None, context
        )
        with pytest.raises(ValueError, match="有权使用"):
            await ad_music_matches(
                tmp_path,
                {
                    **value,
                    "pace": "cuts",
                    "tracks": [
                        {
                            "trackId": unavailable.track_id,
                            "trackReceiptSha256": unavailable.receipt_sha256,
                        }
                    ],
                },
            )

    asyncio.run(scenario())


def test_preview_cache_allows_concurrent_same_track_and_preserves_full_grid(library, tmp_path):  # noqa: F811
    track = register(library, write_wav(tmp_path / "clicks.wav", clicks(120, 0.3, 8)))

    async def scenario():
        context = CancellationContext("simultaneous-music-analysis", 40)
        first, second = await asyncio.gather(
            *[analyze_track(tmp_path, track, context, max_seconds=5) for _ in range(2)]
        )
        assert first == second and first["analyzedSeconds"] == 5
        full = await analyze_track(tmp_path, track, context)
        assert full["analyzedSeconds"] == 8
        assert len(full["beatsUs"]) > len(first["beatsUs"])
        assert not list((tmp_path / ".cache/workspace/music-beats").glob("*.tmp"))

    asyncio.run(scenario())


def test_analyzer_uses_first_audio_stream_like_the_renderer(library, tmp_path):  # noqa: F811
    slow = write_wav(tmp_path / "slow.wav", clicks(80, 0.1, 8))
    fast = write_wav(tmp_path / "fast.wav", clicks(150, 0.1, 8))
    dual = tmp_path / "dual.m4a"
    subprocess.run(
        [
            str(tmp_path / ".tools/ffmpeg/bin/ffmpeg.exe"),
            "-v",
            "error",
            "-i",
            str(slow),
            "-i",
            str(fast),
            "-map",
            "0:a:0",
            "-map",
            "1:a:0",
            "-c:a",
            "aac",
            "-ac:a:1",
            "2",
            str(dual),
        ],
        check=True,
    )
    track = register(library, dual)
    grid = asyncio.run(analyze_track(tmp_path, track, CancellationContext("first-stream", 30)))
    assert abs(grid["bpm"] - 80) < 2


def test_changed_audio_is_not_published_to_its_original_hash_cache(library, tmp_path, monkeypatch):  # noqa: F811
    track = register(library, write_wav(tmp_path / "clicks.wav", clicks(120, 0.3, 8)))
    decode = music_beats.run_media_process

    async def change_track(*args, **kwargs):
        result = await decode(*args, **kwargs)
        track.path.write_bytes(b"changed")
        return result

    monkeypatch.setattr(music_beats, "run_media_process", change_track)
    with pytest.raises(ValueError, match="发生变化"):
        asyncio.run(
            analyze_track(tmp_path, track, CancellationContext("changed", 30), max_seconds=5)
        )
    assert not list((tmp_path / ".cache/workspace/music-beats").glob("*.json"))
