"""Attach a read-only screen-text group to a project search, when explicitly requested."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gamingcreator.application.screen_text_reports import (
    ScreenTextSource,
    collect_screen_text_group,
)
from gamingcreator.cli.local_reports import load_saved_timeline
from gamingcreator.cli.shot_boundaries import saved_frames
from gamingcreator.domain.errors import AppError
from gamingcreator.ui.frame_text import frame_text_cache_path


async def screen_text_group_for_search(
    project: Path,
    run_ids: Sequence[str],
    query: str,
    repository: Path,
) -> dict[str, object]:
    """Read existing workbench OCR caches only. Never starts a new recognition job."""
    sources: list[ScreenTextSource] = []
    reports: list[Path | None] = []
    saved_by_run: dict[str, tuple[tuple[str, int], ...]] = {}
    for run_id in run_ids:
        try:
            timeline = await load_saved_timeline(project, run_id)
        except AppError:
            continue
        asset = timeline.run.asset
        sources.append(ScreenTextSource(run_id, asset.sha256, asset.duration_us))
        reports.append(frame_text_cache_path(repository, project, run_id))
        saved_by_run[run_id] = saved_frames(timeline)
    return collect_screen_text_group(
        query=query,
        query_run_ids=tuple(run_ids),
        sources=tuple(sources),
        reports=tuple(reports),
        saved_by_run=saved_by_run,
    )
