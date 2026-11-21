"""Bound and resolve requests for Studio's local advertising music picker."""

from itertools import pairwise
from pathlib import Path
from typing import Any

from gamingcreator.application.ad_music_match import (
    TARGET_BPM,
    match_beats,
    match_drop,
    rank_matches,
)
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.music_annotation import MOODS
from gamingcreator.infrastructure.music_annotations import read_annotation
from gamingcreator.infrastructure.music_beats import analyze_track
from gamingcreator.infrastructure.music_library import MusicLibrary, MusicTrack


def request_fields(
    value: object,
) -> tuple[int, list[int], str, list[dict[str, str]], str | None, int | None]:
    if not isinstance(value, dict) or set(value) - {"mood", "highlightUs"} != {
        "durationUs",
        "cutUs",
        "pace",
        "tracks",
    }:
        raise ValueError("需要成片时长、剪辑切换点、节奏偏好和本机曲目。")
    duration, cuts, pace, tracks = (value[k] for k in ("durationUs", "cutUs", "pace", "tracks"))
    mood, highlight = value.get("mood"), value.get("highlightUs")
    if (
        type(duration) is not int
        or not 0 < duration <= 86_400_000_000
        or not isinstance(cuts, list)
        or len(cuts) > 1000
        or any(type(cut) is not int or not 0 < cut < duration for cut in cuts)
        or any(a >= b for a, b in pairwise(cuts))
        or not isinstance(pace, str)
        or pace not in TARGET_BPM
        or not isinstance(tracks, list)
        or not 1 <= len(tracks) <= 6
        or (mood is not None and mood not in MOODS)
        or (highlight is not None and (type(highlight) is not int or not 0 <= highlight < duration))
    ):
        raise ValueError("节奏分析参数无效。")
    if any(
        not isinstance(row, dict)
        or set(row) != {"trackId", "trackReceiptSha256"}
        or any(not isinstance(field, str) for field in row.values())
        for row in tracks
    ) or len({row["trackId"] for row in tracks}) != len(tracks):
        raise ValueError("需要不同本机曲目的登记回执。")
    return duration, cuts, pace, tracks, mood, highlight


def _available_annotation(track: MusicTrack) -> dict[str, Any]:
    try:
        return read_annotation(track) or {}
    except (OSError, ValueError):
        return {}


async def ad_music_matches(repository: Path, value: object) -> dict[str, Any]:
    duration, cuts, pace, references, mood, highlight = request_fields(value)
    library = MusicLibrary(repository)
    tracks = [library.resolve(row["trackId"], row["trackReceiptSha256"]) for row in references]
    if any(track.license_status != "user_declared" for track in tracks):
        raise ValueError("请先声明有权使用参与推荐的音乐。")
    context = CancellationContext("ad-music-matches", 90)
    annotations = [_available_annotation(track) for track in tracks]
    rows = []
    for reference, track, annotation in zip(references, tracks, annotations, strict=True):
        try:
            grid = await analyze_track(repository, track, context, max_seconds=45)
        except ValueError:
            grid = {}
        tags = annotation.get("moods", [])
        drop = annotation.get("dropUs")
        rows.append(
            {
                **reference,
                **match_beats(grid, cuts),
                "moods": tags,
                "energy": annotation.get("energy"),
                "dropUs": drop,
                "annotationSha256": annotation.get("annotationSha256"),
                "moodMatch": mood in tags if mood is not None and tags else None,
                "dropGapUs": match_drop(grid, drop, highlight, duration),
            }
        )
    if annotations != [_available_annotation(track) for track in tracks]:
        raise ValueError("曲库标注已更新，请刷新后重新分析。")
    return {
        "pace": pace,
        "mood": mood,
        "highlightUs": highlight,
        "suggestions": rank_matches(rows, pace),
    }
