"""P030 beat snapping: cuts land on beat frames, shots only get shorter, loops and speed."""

import pytest

from gamingcreator.application.beat_snap import MIN_SHOT_US, snap_to_beats
from gamingcreator.application.timeline_commands import CommandError, _frames, _starts

CUT = {"type": "cut", "frames": 0}
ONE = {"numerator": 1, "denominator": 1}


def row(clip_id, start, end, speed=ONE, transition=CUT):
    return {
        "clipId": clip_id,
        "startUs": start,
        "endUs": end,
        "speed": speed,
        "transitionIn": transition,
    }


def cuts(rows, fps=30):
    starts = _starts(rows, fps)
    return [*starts[1:], starts[-1] + _frames(rows[-1], fps)]


def test_cuts_land_on_beats_and_shots_only_shorten():
    beats = [i * 500_000 for i in range(40)]  # 120 BPM -> every 15 frames at 30 fps
    before = [
        row("a", 0, 2_200_000),
        row("b", 10_000_000, 12_350_000),
        row("c", 3_000_000, 4_100_000),
    ]
    result = snap_to_beats(before, 30, beats, 20_000_000)
    after = result["clips"]
    assert all(c % 15 == 0 for c in cuts(after))
    for old, new in zip(before, after, strict=True):
        assert new["startUs"] == old["startUs"] and new["endUs"] <= old["endUs"]
        assert new["endUs"] - new["startUs"] >= MIN_SHOT_US
    assert result["afterSeconds"] < result["beforeSeconds"] and result["changes"]


def test_double_speed_maps_output_frames_back_to_source():
    beats = [i * 500_000 for i in range(40)]
    after = snap_to_beats(
        [row("a", 0, 5_400_000, {"numerator": 2, "denominator": 1})], 30, beats, 20_000_000
    )
    clip = after["clips"][0]
    # 5.4 s source at 2x = 81 output frames; snapped back to frame 75 = 5.0 s of source.
    assert _frames(clip, 30) == 75 and clip["endUs"] == 5_000_000


def test_track_loops_on_the_output_clock():
    # A 3-second track with one beat at 1 s: output beats at 1 s, 4 s, 7 s ...
    after = snap_to_beats([row("a", 0, 4_500_000)], 30, [1_000_000], 3_000_000)
    assert cuts(after["clips"]) == [120]


def test_no_nearby_beat_or_already_aligned_is_refused():
    with pytest.raises(CommandError):
        snap_to_beats([row("a", 0, 1_500_000)], 30, [i * 500_000 for i in range(10)], 5_000_000)
    with pytest.raises(CommandError):
        snap_to_beats([row("a", 0, 5_000_000)], 30, [9_000_000], 20_000_000)
    with pytest.raises(CommandError):
        snap_to_beats([row("a", 0, 5_000_000)], 30, [], 20_000_000)


def test_never_shortens_below_minimum():
    # Beat 0.2 s before a 0.6 s shot's end would leave 0.4 s: keep the shot as it is.
    with pytest.raises(CommandError):
        snap_to_beats([row("a", 0, 600_000)], 30, [400_000], 20_000_000)
