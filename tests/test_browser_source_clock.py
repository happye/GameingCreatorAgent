"""Pure conversion semantics shared by both pages, mirrored in Chromium's JS module.

Every case here is arithmetic or decision-table behaviour; no media file is involved. The
JS module is evaluated in a real Chromium so the two implementations cannot drift while the
measured browser evidence itself lives in test_benchmark_source_clock_browser.py.
"""

import json
import math
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.browser_source_clock import (
    AXIS_TOLERANCE_US,
    DURATION_TOLERANCE_US,
    BrowserSourceClock,
    build_source_clock,
    capture_source_us,
    clock_document,
    duration_change_verdict,
    interval_replayable,
    player_seconds_to_source_us,
    source_us_to_player_seconds,
    validate_browser_observation,
)
from gamingcreator.domain.media import MediaAsset, MediaStream

ROOT = Path(__file__).resolve().parents[1]
SHARED_SCRIPT = ROOT / "src/gamingcreator/ui/static/source-clock.js"


def test_seek_timeout_can_be_extended_without_accepting_unfinished_seek():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.add_script_tag(path=str(SHARED_SCRIPT))
            result = page.evaluate(
                """async () => {
                    function player(delay) {
                        const v = new EventTarget();
                        v.seeking = false; v.readyState = 2; let time = 0;
                        Object.defineProperty(v, 'currentTime', {
                            get: () => time,
                            set(value) {
                                v.seeking = true;
                                setTimeout(() => {
                                    time = value; v.seeking = false;
                                    v.dispatchEvent(new Event('seeked'));
                                }, delay);
                            }
                        });
                        return v;
                    }
                    const values = await Promise.all([
                        SourceClock.settle(player(3300), 1),
                        SourceClock.settle(player(3300), 1, 10000),
                        SourceClock.settle(player(3300), 1, 20)
                    ]);
                    const invalid = [true, 0, -1, 1.5, 15001].map(timeout => {
                        try { SourceClock.settle(player(0), 1, timeout); return false; }
                        catch (error) { return error instanceof RangeError; }
                    });
                    return {values, invalid};
                }"""
            )
        finally:
            browser.close()
    assert result == {"values": [None, 1, None], "invalid": [True] * 5}


CLOCK = BrowserSourceClock(
    origin_us=2_478_000,
    duration_us=2_022_000,
    video_start_us=22_000,
    video_end_us=2_022_000,
    audio_start_us=0,
    audio_end_us=2_021_334,
)
DOCUMENT = clock_document(CLOCK)
ZERO_CLOCK = BrowserSourceClock(
    origin_us=0,
    duration_us=2_022_000,
    video_start_us=0,
    video_end_us=2_022_000,
    audio_start_us=0,
    audio_end_us=2_021_334,
)
ZERO_DOCUMENT = clock_document(ZERO_CLOCK)


@pytest.mark.parametrize(
    "clock, duration_seconds, seeked, reason",
    [
        # Within the tolerance window: header value and the normalised span agree.
        (CLOCK, 2.022, False, None),
        (ZERO_CLOCK, 2.022, False, None),
        # Measured Chromium growth of a non-zero-PTS MP4 after a seek, bounded by the axis end.
        (CLOCK, 2.866667, True, None),
        (CLOCK, 4.4, True, None),
        (CLOCK, 4.6, True, "duration_changed"),
        (CLOCK, 3.0, False, "duration_changed"),
        # A zero-origin media never legitimately grows.
        (ZERO_CLOCK, 3.0, True, "duration_changed"),
        (ZERO_CLOCK, 2.5, False, "duration_changed"),
        # Shrinks, non-finite and invalid values revoke regardless of seeks.
        (CLOCK, 1.5, True, "duration_mismatch"),
        (ZERO_CLOCK, 1.0, True, "duration_mismatch"),
        (ZERO_CLOCK, float("nan"), True, "duration_unavailable"),
        (ZERO_CLOCK, float("inf"), True, "duration_unavailable"),
        (CLOCK, -1.0, True, "duration_unavailable"),
        (ZERO_CLOCK, True, True, "duration_unavailable"),
        (ZERO_CLOCK, None, True, "duration_unavailable"),
    ],
)
def test_duration_change_rule(clock, duration_seconds, seeked, reason):
    assert duration_change_verdict(clock, duration_seconds, seeked=seeked) == reason


def test_clock_document_is_runtime_only_and_never_contains_fractions():
    assert DOCUMENT == {
        "schemaVersion": "browser-source-clock-v1",
        "originUs": 2_478_000,
        "durationUs": 2_022_000,
        "videoStartUs": 22_000,
        "videoEndUs": 2_022_000,
        "audioStartUs": 0,
        "audioEndUs": 2_021_334,
        "axisToleranceUs": AXIS_TOLERANCE_US,
        "durationToleranceUs": DURATION_TOLERANCE_US,
    }
    assert json.loads(json.dumps(DOCUMENT)) == DOCUMENT


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (2_478_000 / 1_000_000, 0),
        (2.5, 22_000),
        (2.778, 300_000),
        (3.0, 522_000),
        (4.5, 2_022_000),
        (4.5 + 0.001, 2_022_000),  # within tolerance of the end: clamp to the endpoint
        (2.4779, 0),  # within tolerance of the origin: clamp to zero
        (2.4759, None),  # more than 2 ms before the axis start
        (4.503, None),  # more than 2 ms past the axis end
        (0.0, None),
        (-1.0, None),
        (1e12, None),
        (9007199254.740992, None),  # beyond the safe-integer microsecond range
        (True, None),
        ("2.5", None),
        (None, None),
        (float("nan"), None),
        (float("inf"), None),
    ],
)
def test_player_seconds_quantize_to_canonical_source_microseconds(seconds, expected):
    assert player_seconds_to_source_us(CLOCK, seconds) == expected


@pytest.mark.parametrize(
    "source_us, expected",
    [
        (0, 2.478),
        (22_000, 2.5),
        (300_000, 2.778),
        (2_022_000, 4.5),
        (-1, None),
        (2_022_001, None),
        (True, None),
        (1.0, None),
        ("0", None),
        (None, None),
    ],
)
def test_source_microseconds_convert_back_to_player_seconds(source_us, expected):
    result = source_us_to_player_seconds(CLOCK, source_us)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_replay_and_capture_respect_video_coverage_and_finite_integers():
    assert interval_replayable(CLOCK, 300_000, 700_000)
    assert interval_replayable(CLOCK, 22_000, 2_022_000)
    assert not interval_replayable(CLOCK, 0, 1_000)  # audio-only head has no picture
    assert not interval_replayable(CLOCK, 0, 2_022_000)
    assert not interval_replayable(CLOCK, 700_000, 300_000)
    assert not interval_replayable(CLOCK, 300_000, 2_022_001)
    assert not interval_replayable(CLOCK, True, 700_000)
    assert capture_source_us(CLOCK, 2.478) is None
    assert capture_source_us(CLOCK, 2.47) is None
    assert capture_source_us(CLOCK, 2.5) == 22_000
    assert capture_source_us(CLOCK, 2.778) == 300_000
    assert capture_source_us(CLOCK, 4.5) == 2_022_000
    assert capture_source_us(CLOCK, 4.51) is None
    assert capture_source_us(CLOCK, float("nan")) is None


@pytest.mark.parametrize(
    "observation, reason",
    [
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, 2.478],
            },
            None,
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "middleSeconds": 2.866667,
                "axisStartsSeconds": [2.478, 2.479],
            },
            None,
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "middleSeconds": None,
                "axisStartsSeconds": [2.478, 2.478],
            },
            "seek_incomplete",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "axisStartsSeconds": [2.478, 2.478],
            },
            "seek_incomplete",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, 2.4805],
            },
            "axis_unstable",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [0, 0],
            },
            "axis_mismatch",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, None],
            },
            "axis_unavailable",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478],
            },
            "axis_unavailable",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": "x",
            },
            "axis_unavailable",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": 3.0,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, 2.478],
            },
            "duration_mismatch",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": None,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, 2.478],
            },
            "duration_unavailable",
        ),
        (
            {
                "seekable": True,
                "durationSeconds": float("inf"),
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, 2.478],
            },
            "duration_unavailable",
        ),
        (
            {
                "seekable": False,
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, 2.478],
            },
            "seek_unavailable",
        ),
        (
            {
                "seekable": "yes",
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, 2.478],
            },
            "observation_invalid",
        ),
        (
            {
                "durationSeconds": 2.022,
                "middleSeconds": 3.0,
                "axisStartsSeconds": [2.478, 2.478],
            },
            "observation_invalid",
        ),
    ],
)
def test_runtime_observation_decision_table(observation, reason):
    assert validate_browser_observation(CLOCK, observation) == reason


def test_build_source_clock_rejects_unrepresentable_assets():
    video = MediaStream(0, "video", Fraction(1, 1000), 0, 2000)

    def asset(streams, origin, duration_us):
        return MediaAsset("id", Path("media.mp4"), "a" * 64, streams, origin, duration_us, "probe")

    zero = build_source_clock(asset((video,), origin=Fraction(0), duration_us=2_000_000))
    assert zero is not None
    assert (zero.origin_us, zero.duration_us, zero.video_start_us, zero.video_end_us) == (
        0,
        2_000_000,
        0,
        2_000_000,
    )
    # Exact rational origins round to the nearest microsecond, half up.
    odd = MediaStream(0, "video", Fraction(1, 48_000), 1, 96_000)
    shifted = build_source_clock(asset((odd,), origin=odd.start_seconds, duration_us=2_000_000))
    assert shifted is not None and shifted.origin_us == 21
    negative = MediaStream(0, "video", Fraction(1, 1000), -1000, 2000)
    assert (
        build_source_clock(asset((negative,), origin=Fraction(-1), duration_us=2_000_000)) is None
    )
    second_video = MediaStream(2, "video", Fraction(1, 1000), 0, 2000)
    assert (
        build_source_clock(asset((video, second_video), origin=Fraction(0), duration_us=2_000_000))
        is None
    )


def test_build_source_clock_keeps_audio_priming_as_part_of_the_axis():
    # Real ffprobe values of the non-zero-PTS fixture: AAC priming starts 22 ms before video.
    video = MediaStream(0, "video", Fraction(1, 15_360), 38_400, 30_720)
    audio = MediaStream(1, "audio", Fraction(1, 48_000), 118_944, 97_024)
    clock = build_source_clock(
        MediaAsset(
            "id",
            Path("media.mp4"),
            "a" * 64,
            (video, audio),
            audio.start_seconds,
            2_022_000,
            "probe",
        )
    )
    assert clock is not None
    assert clock.origin_us == 2_478_000
    assert clock.video_start_us == 22_000
    assert clock.audio_start_us == 0


def js_results(browser, calls):
    page = browser.new_page()
    try:
        page.goto("data:text/html,<meta charset=utf-8>")
        page.add_script_tag(content=SHARED_SCRIPT.read_text(encoding="utf-8"))
        return page.evaluate(
            """({document, playerSeconds, sourceUs, intervals, captures, observations, durationChanges}) => {
                const media = {sourceClock: document};
                const candidates = SourceClock.clockCandidates(media);
                return {
                    candidates: candidates.length,
                    player: playerSeconds.map(value => SourceClock.playerToSourceUs(candidates[0], value)),
                    source: sourceUs.map(value => SourceClock.sourceUsToPlayerSeconds(candidates[0], value)),
                    intervals: intervals.map(pair => SourceClock.intervalReplayable(candidates[0], pair[0], pair[1])),
                    captures: captures.map(value => SourceClock.captureSourceUs(candidates[0], value)),
                    observations: observations.map(observation => SourceClock.validate(candidates[0], observation)),
                    durationChanges: durationChanges.map(change => {
                        const clock = SourceClock.clockCandidates({sourceClock: change.document})[0];
                        return SourceClock.durationChangeVerdict(clock, change.duration, change.seeked);
                    }),
                    invalidDocuments: [
                        null,
                        {schemaVersion: 'other'},
                        {...document, originUs: -1},
                        {...document, videoStartUs: document.videoEndUs},
                        {...document, durationUs: 1.5},
                        {...document, audioStartUs: 0, audioEndUs: null},
                        {...document, originUs: 1.5},
                    ].map(row => SourceClock.clockCandidates({sourceClock: row}).length),
                };
            }""",
            calls,
        )
    finally:
        page.close()


def test_javascript_and_python_share_one_conversion_semantics():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    player_seconds = [
        2.478,
        2.4780005,
        2.4779999,
        2.4775,
        2.477,
        2.5,
        2.778,
        3.0,
        3.123456,
        4.499999,
        4.5,
        4.5005,
        4.501,
        4.51,
        0.0,
        0.000001,
        -1.0,
        1e12,
        9007199254.740992,
        1 / 3,
    ]
    source_us = [
        0,
        1,
        21_999,
        22_000,
        300_000,
        2_021_999,
        2_022_000,
        2_022_001,
        -1,
        9_007_199_254_740_991,
    ]
    intervals = [
        [0, 1_000],
        [22_000, 2_022_000],
        [300_000, 700_000],
        [2_022_000, 22_000],
        [0, 2_022_000],
    ]
    captures = [2.478, 2.5, 2.778, 4.5, 4.51]
    observations = [
        {
            "seekable": True,
            "durationSeconds": 2.022,
            "middleSeconds": 3.0,
            "axisStartsSeconds": [2.478, 2.478],
        },
        {
            "seekable": True,
            "durationSeconds": 2.022,
            "middleSeconds": None,
            "axisStartsSeconds": [2.478, 2.478],
        },
        {
            "seekable": True,
            "durationSeconds": 2.022,
            "middleSeconds": 3.0,
            "axisStartsSeconds": [2.478, 2.4805],
        },
        {
            "seekable": True,
            "durationSeconds": 2.022,
            "middleSeconds": 3.0,
            "axisStartsSeconds": [0, 0],
        },
        {
            "seekable": True,
            "durationSeconds": 2.022,
            "middleSeconds": 3.0,
            "axisStartsSeconds": [2.478, None],
        },
        {
            "seekable": True,
            "durationSeconds": 3.0,
            "middleSeconds": 3.0,
            "axisStartsSeconds": [2.478, 2.478],
        },
        {
            "seekable": True,
            "durationSeconds": None,
            "middleSeconds": 3.0,
            "axisStartsSeconds": [2.478, 2.478],
        },
        {
            "seekable": False,
            "durationSeconds": 2.022,
            "middleSeconds": 3.0,
            "axisStartsSeconds": [2.478, 2.478],
        },
        {
            "seekable": "yes",
            "durationSeconds": 2.022,
            "middleSeconds": 3.0,
            "axisStartsSeconds": [2.478, 2.478],
        },
        {
            "seekable": True,
            "durationSeconds": 2.022,
            "axisStartsSeconds": [2.478, 2.478],
        },
    ]
    duration_changes = [
        (DOCUMENT, CLOCK, 2.022, False),
        (ZERO_DOCUMENT, ZERO_CLOCK, 2.022, False),
        (DOCUMENT, CLOCK, 2.866667, True),
        (DOCUMENT, CLOCK, 4.4, True),
        (DOCUMENT, CLOCK, 4.6, True),
        (DOCUMENT, CLOCK, 3.0, False),
        (ZERO_DOCUMENT, ZERO_CLOCK, 3.0, True),
        (ZERO_DOCUMENT, ZERO_CLOCK, 1.0, True),
        (ZERO_DOCUMENT, ZERO_CLOCK, float("inf"), True),
    ]
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            result = js_results(
                browser,
                {
                    "document": DOCUMENT,
                    "playerSeconds": player_seconds,
                    "sourceUs": source_us,
                    "intervals": intervals,
                    "captures": captures,
                    "observations": observations,
                    "durationChanges": [
                        {
                            "document": document,
                            "duration": None if math.isinf(duration) else duration,
                            "seeked": seeked,
                        }
                        for document, _, duration, seeked in duration_changes
                    ],
                },
            )
        finally:
            browser.close()
    assert result["candidates"] == 1
    assert result["player"] == [
        player_seconds_to_source_us(CLOCK, value) for value in player_seconds
    ]
    python_source = [source_us_to_player_seconds(CLOCK, value) for value in source_us]
    for left, right in zip(result["source"], python_source, strict=True):
        assert (left is None) == (right is None)
        if right is not None:
            assert math.isclose(left, right, rel_tol=0, abs_tol=1e-12)
    assert result["intervals"] == [interval_replayable(CLOCK, *pair) for pair in intervals]
    assert result["captures"] == [capture_source_us(CLOCK, value) for value in captures]
    assert result["durationChanges"] == [
        duration_change_verdict(clock, duration, seeked=seeked)
        for _, clock, duration, seeked in duration_changes
    ]
    assert [row["reason"] for row in result["observations"]] == [
        validate_browser_observation(CLOCK, row) for row in observations
    ]
    # Invalid runtime documents are rejected, never coerced into a mapping.
    assert result["invalidDocuments"] == [0, 0, 0, 0, 0, 0, 0]
