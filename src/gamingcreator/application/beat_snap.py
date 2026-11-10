"""Snap shot changes to the background music's beats by shortening shots only (P030).

Pure and stateless like timeline commands: the result is a preview of new clip rows that the
editor applies and saves through the normal version path. Shots are only ever shortened, so
every source range stays inside the range the shot already had.
"""

from __future__ import annotations

from typing import Any

from gamingcreator.application.timeline_commands import (
    CommandError,
    _check,
    _frames,
    _speed,
    _starts,
    guard_transitions,
)

MIN_SHOT_US = 500_000


def _beat_frames(beats_us: list[int], track_us: int, total_frames: int, fps: int) -> list[int]:
    """Output-clock beat frames; the track starts at output 0 and loops (as rendered)."""
    frames: set[int] = set()
    loop = 0
    while beats_us and loop * track_us * fps < total_frames * 1_000_000:
        for beat in beats_us:
            frame = round((loop * track_us + beat) * fps / 1_000_000)
            if 0 < frame <= total_frames:
                frames.add(frame)
        loop += 1
    return sorted(frames)


def _source_us_for(frames: int, row: dict[str, Any], fps: int) -> int:
    """Smallest source length whose output length (as _frames floors it) is ``frames``."""
    speed = _speed(row)
    numerator = frames * 1_000_000 * speed.numerator
    denominator = fps * speed.denominator
    return -(-numerator // denominator)


def snap_to_beats(
    clips: object, fps: object, beats_us: object, track_duration_us: object, max_shift_ms: int = 700
) -> dict[str, object]:
    rows = _check(clips, fps)
    assert isinstance(fps, int)
    if (
        not isinstance(beats_us, list)
        or not beats_us
        or any(type(b) is not int or b < 0 for b in beats_us)
        or type(track_duration_us) is not int
        or track_duration_us <= 0
    ):
        raise CommandError("配乐没有可用的节拍。")
    before = max(s + _frames(r, fps) for s, r in zip(_starts(rows, fps), rows, strict=True))
    beats = _beat_frames(sorted(beats_us), track_duration_us, before, fps)
    max_shift = max_shift_ms * fps // 1000
    changes: list[str] = []
    for index in range(len(rows)):
        starts = _starts(rows, fps)
        # The visible cut is where the next shot starts; the last shot's cut is the video end.
        cut = (
            starts[index + 1]
            if index + 1 < len(rows)
            else starts[index] + _frames(rows[index], fps)
        )
        earlier = [b for b in beats if cut - max_shift <= b <= cut]
        if not earlier or earlier[-1] == cut:
            continue
        shorten = cut - earlier[-1]
        row = rows[index]
        target = _frames(row, fps) - shorten
        length = _source_us_for(target, row, fps)
        if length < MIN_SHOT_US or length >= row["endUs"] - row["startUs"]:
            continue
        row["endUs"] = row["startUs"] + length
        changes.append(f"第{index + 1}个镜头缩短 {shorten / fps:.2f} 秒，切换落在拍点")
    if not changes:
        raise CommandError("切换点已经对齐节拍，或附近没有可用的拍点。")
    changes += guard_transitions(rows, fps)
    starts = _starts(rows, fps)
    after = max(s + _frames(r, fps) for s, r in zip(starts, rows, strict=True))
    return {
        "schemaVersion": "beat-snap-v1",
        "clips": rows,
        "changes": changes,
        "beforeSeconds": before / fps,
        "afterSeconds": after / fps,
        "beatFrames": [b for b in beats if b <= after],
    }
