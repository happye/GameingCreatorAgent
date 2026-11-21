"""Rank local music by measured rhythm against the current advertising edit."""

from bisect import bisect_left
from typing import Any

TARGET_BPM = {"cuts": None, "calm": 80, "lively": 115, "intense": 155}
TARGET_ENERGY = {"calm": 25, "lively": 55, "intense": 85}
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


def match_drop(
    grid: dict[str, Any], drop: int | None, highlight: int | None, duration_us: int
) -> int | None:
    if drop is None or highlight is None:
        return None
    analyzed_us = round(float(grid.get("analyzedSeconds", 0)) * 1_000_000)
    if not 0 <= drop < min(analyzed_us, duration_us):
        return None
    if not grid.get("complete"):
        return abs(highlight - drop) if highlight < analyzed_us else None
    if highlight < drop:
        return drop - highlight
    last_cycle = (duration_us - 1 - drop) // analyzed_us
    relative = highlight - drop
    cycle = min(relative // analyzed_us, last_cycle)
    before = relative - cycle * analyzed_us
    return min(before, analyzed_us - before) if cycle < last_cycle else before


def rank_matches(rows: list[dict[str, Any]], pace: str) -> list[dict[str, Any]]:
    target = TARGET_BPM[pace]
    target_energy = TARGET_ENERGY.get(pace)

    def key(row: dict[str, Any]) -> tuple[int, bool, int, bool, float, int, int, int]:
        bpm = row["bpm"]
        mood = row.get("moodMatch")
        mood_order = 0 if mood is True else 2 if mood is False else 1
        drop = row.get("dropGapUs")
        energy = row.get("energy")
        energy_gap = (
            abs(energy - target_energy) if energy is not None and target_energy is not None else 101
        )
        distance = abs(bpm - target) if bpm is not None and target is not None else 0.0
        return (
            mood_order,
            drop is None,
            drop or 0,
            bpm is None,
            distance,
            energy_gap,
            -row["nearCuts"],
            -row["checkedCuts"],
        )

    # Stable ties retain the candidate order from the existing duration suggestions.
    return sorted(rows, key=key)
