import asyncio
import json
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import (
    AudioEvidence,
    AudioFrameMapping,
    MediaAsset,
    MediaStream,
    ceil_us,
    floor_us,
)
from gamingcreator.infrastructure.ffmpeg_media import (
    hash_source,
    parse_audio_log,
    parse_probe,
    parse_visual_log,
)


def asset(origin: Fraction = Fraction(5), duration: int = 2) -> MediaAsset:
    stream = MediaStream(0, "video", Fraction(1, 90000), int(origin * 90000), duration * 90000)
    return MediaAsset(
        "media", Path("source"), "hash", (stream,), origin, duration * 1_000_000, "probe"
    )


def test_vfr_mapping_preserves_nonzero_and_negative_pts_without_fps_math() -> None:
    for origin in (Fraction(5), Fraction(-5)):
        media = asset(origin)
        base = int(origin * 90000)
        assert [
            media.instant(base + offset, Fraction(1, 90000)).time_us
            for offset in (0, 1530, 2970, 6030)
        ] == [0, 17000, 33000, 67000]


def test_rational_subtraction_precedes_microsecond_rounding() -> None:
    origin = Fraction(1, 90000)
    media = asset(origin)
    assert media.instant(2, Fraction(1, 90000)).time_us == 11
    assert floor_us(Fraction(1, 3)) == 333333
    assert ceil_us(Fraction(1, 3)) == 333334


def test_audio_gap_and_overlap_use_sample_pieces_not_one_offset() -> None:
    media = asset(Fraction(0))
    frames = (
        AudioFrameMapping(0, 100, 0, Fraction(1, 16000)),
        AudioFrameMapping(100, 100, 120, Fraction(1, 16000)),
        AudioFrameMapping(200, 100, 210, Fraction(1, 16000)),
    )
    audio = AudioEvidence("audio", Path("audio.wav"), "hash", 16000, 300, frames)
    assert audio.discontinuity_offsets == (100, 200)
    mapped = audio.map_interval(110, 120, media)
    assert (mapped.source_range.start_us, mapped.source_range.end_us, mapped.uncertain) == (
        8125,
        8750,
        False,
    )
    mapped = audio.map_interval(90, 210, media)
    assert (mapped.source_range.start_us, mapped.source_range.end_us, mapped.uncertain) == (
        5625,
        13750,
        True,
    )


def test_audio_quantization_at_origin_is_clamped_and_remains_traceable() -> None:
    origin = Fraction(406, 44100)
    stream = MediaStream(0, "video", Fraction(1, 44100), 406, 44100)
    media = MediaAsset("media", Path("source"), "hash", (stream,), origin, 1_000_000, "probe")
    audio = AudioEvidence(
        "audio",
        Path("a.wav"),
        "hash",
        16000,
        16,
        (AudioFrameMapping(0, 16, 147, Fraction(1, 16000)),),
    )
    mapped = audio.map_interval(0, 16, media)
    assert mapped.source_range.start_us == 0 and mapped.uncertain
    assert mapped.clamped_start_seconds == origin - Fraction(147, 16000)


def test_audio_mapping_rejects_missing_samples_and_out_of_range_segments() -> None:
    with pytest.raises(ValueError):
        AudioEvidence(
            "audio",
            Path("a.wav"),
            "hash",
            16000,
            10,
            (AudioFrameMapping(1, 10, 0, Fraction(1, 16000)),),
        )
    audio = AudioEvidence(
        "audio",
        Path("a.wav"),
        "hash",
        16000,
        10,
        (AudioFrameMapping(0, 10, 0, Fraction(1, 16000)),),
    )
    with pytest.raises(ValueError):
        audio.map_interval(0, 11, asset(Fraction(0)))


def test_probe_selects_actual_video_and_common_audio_origin() -> None:
    raw = {
        "streams": [
            {"index": 0, "codec_type": "video", "disposition": {"attached_pic": 1}},
            {
                "index": 1,
                "codec_type": "video",
                "time_base": "1/1000",
                "start_pts": 5000,
                "duration_ts": 2000,
            },
            {
                "index": 2,
                "codec_type": "audio",
                "time_base": "1/16000",
                "start_pts": 64000,
                "duration_ts": 40000,
            },
        ]
    }
    media = parse_probe(json.dumps(raw).encode(), Path("source"), "hash", "probe")
    assert media.origin_seconds == 4 and media.duration_us == 3_000_000
    assert media.instant(5000, Fraction(1, 1000)).time_us == 1_000_000


@pytest.mark.parametrize(
    "raw", [b"{}", b"{", b'{"streams":[]}', b'{"streams":[{"codec_type":"audio"}]}']
)
def test_probe_fails_explicitly_when_exact_timing_is_unavailable(raw: bytes) -> None:
    with pytest.raises(AppError):
        parse_probe(raw, Path("private"), "hash", "probe")


@pytest.mark.parametrize("pts", [(1, 1), (2, 1)])
def test_selected_video_pts_cannot_repeat_or_reverse(pts: tuple[int, int]) -> None:
    log = "[Parsed_showinfo_2 @ X] config in time_base: 1/90000\n"
    log += "\n".join(
        f"[Parsed_showinfo_2 @ X] n: {i} pts: {p} pts_time: 0" for i, p in enumerate(pts)
    )
    with pytest.raises(AppError):
        parse_visual_log(log)


def test_audio_log_retains_nonuniform_pts_and_sample_offsets() -> None:
    log = "\n".join(
        f"[Parsed_ashowinfo_2 @ X] n:{i} pts:{pts} rate:16000 nb_samples:{count}"
        for i, (pts, count) in enumerate([(0, 325), (320, 341), (671, 342)])
    )
    frames = parse_audio_log(log, 16000)
    assert [f.sample_offset for f in frames] == [0, 325, 666]
    assert [f.pts for f in frames] == [0, 320, 671]


def test_source_hash_checks_cancellation_after_the_last_chunk(tmp_path: Path) -> None:
    source = tmp_path / "tiny.bin"
    source.write_bytes(b"tiny")

    async def scenario() -> None:
        context = CancellationContext("run", 5)
        task = asyncio.create_task(hash_source(source, context))
        await asyncio.sleep(0)
        context.cancelled.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
