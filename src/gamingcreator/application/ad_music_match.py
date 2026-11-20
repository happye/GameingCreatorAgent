"""Rank local music by measured rhythm against the current advertising edit."""

from bisect import bisect_left
from typing import Any

TARGET_BPM = {"cuts": None, "calm": 80, "lively": 115, "intense": 155}
NEAR_BEAT_US = 75_000


def match_beats(grid: dict[str, Any], cuts: list[int]) -> dict[str, Any]:
    result: dict[str, Any] = {"bpm": None, "nearCuts": 0, "checkedCuts": 0, "totalCuts": len(cuts)}
    analyzed_us = round(grid.get("analyzedSeconds", 0) * 1_000_000)
    beats = [beat for beat in grid.get("beatsUs", []) if 0 <= beat < analyzed_us]
    if len(beats) < 4 or grid.get("confidence", 0) < 0.18:
        return result
    complete = grid.get("complete") is True
    result["bpm"] = grid["bpm"]
    for cut in cuts:
        if not complete and cut >= analyzed_us:
            continue
        cycle, phase = divmod(cut, analyzed_us) if complete else (0, cut)
        i = bisect_left(beats, phase)
        adjacent = beats[max(0, i - 1) : i + 1]
        if complete:
            if cycle:
                adjacent.append(beats[-1] - analyzed_us)
            adjacent.append(analyzed_us + beats[0])
        result["checkedCuts"] += 1
        if min(abs(phase - beat) for beat in adjacent) <= NEAR_BEAT_US:
            result["nearCuts"] += 1
    return result


def rank_matches(rows: list[dict[str, Any]], pace: str) -> list[dict[str, Any]]:
    target = TARGET_BPM[pace]

    def key(row: dict[str, Any]) -> tuple[bool, float, int, int]:
        bpm = row["bpm"]
        distance = abs(bpm - target) if bpm is not None and target is not None else 0.0
        return bpm is None, distance, -row["nearCuts"], -row["checkedCuts"]

    # Stable ties retain the candidate order from the existing duration suggestions.
    return sorted(rows, key=key)
