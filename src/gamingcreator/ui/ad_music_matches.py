"""Bound and resolve requests for Studio's local advertising music picker."""

from itertools import pairwise
from pathlib import Path
from typing import Any

from gamingcreator.application.ad_music_match import TARGET_BPM, match_beats, rank_matches
from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.music_beats import analyze_track
from gamingcreator.infrastructure.music_library import MusicLibrary


def request_fields(value: object) -> tuple[list[int], str, list[dict[str, str]]]:
    if not isinstance(value, dict) or set(value) != {"durationUs", "cutUs", "pace", "tracks"}:
        raise ValueError("需要成片时长、剪辑切换点、节奏偏好和本机曲目。")
    duration, cuts, pace, tracks = (value[k] for k in ("durationUs", "cutUs", "pace", "tracks"))
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
    ):
        raise ValueError("节奏分析参数无效。")
    if any(
        not isinstance(row, dict)
        or set(row) != {"trackId", "trackReceiptSha256"}
        or any(not isinstance(field, str) for field in row.values())
        for row in tracks
    ) or len({row["trackId"] for row in tracks}) != len(tracks):
        raise ValueError("需要不同本机曲目的登记回执。")
    return cuts, pace, tracks


async def ad_music_matches(repository: Path, value: object) -> dict[str, Any]:
    cuts, pace, references = request_fields(value)
    library = MusicLibrary(repository)
    tracks = [library.resolve(row["trackId"], row["trackReceiptSha256"]) for row in references]
    if any(track.license_status != "user_declared" for track in tracks):
        raise ValueError("请先声明有权使用参与推荐的音乐。")
    context = CancellationContext("ad-music-matches", 90)
    rows = []
    for reference, track in zip(references, tracks, strict=True):
        try:
            grid = await analyze_track(repository, track, context, max_seconds=45)
        except ValueError:
            grid = {}
        rows.append({**reference, **match_beats(grid, cuts)})
    return {"pace": pace, "suggestions": rank_matches(rows, pace)}
