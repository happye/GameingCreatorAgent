"""Workbench shot-boundary reports: an explicit local scan, cached outside the project."""

import hashlib
import json
import threading
from pathlib import Path
from uuid import uuid4

from gamingcreator.application.shot_boundaries import (
    SHOT_REPORT_VERSION,
    ShotDetector,
    shot_timeline_digest,
)
from gamingcreator.cli.shot_boundaries import build_run_shot_report, saved_frames
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

MAX_CACHED_REPORT_BYTES = 16 * 1024 * 1024
_busy: set[Path] = set()
_busy_guard = threading.Lock()


def shot_cache_path(repository: Path, project: Path, run_id: str) -> Path:
    """One cache file per project and run, under the workbench cache, never in the project."""
    key = hashlib.sha256(f"{project.resolve()}\n{run_id}".encode()).hexdigest()[:32]
    return repository.resolve() / ".cache" / "workspace" / "shots" / f"{key}.json"


def _with_reference(report: dict[str, object], reference: str) -> dict[str, object]:
    return {**report, "available": True, "project": reference}


async def detect_shots_payload(
    project: Path,
    run_id: str,
    repository: Path,
    detector: ShotDetector,
    *,
    project_reference: str,
) -> dict[str, object]:
    """Scan the run's original footage now (local, read-only) and replace its cached report."""
    target = shot_cache_path(repository, project, run_id)
    with _busy_guard:
        if target in _busy:
            raise AppError("shots.busy", "这个任务正在检测镜头，请稍候。", ExitCode.STORAGE)
        _busy.add(target)
    try:
        report = await build_run_shot_report(project, run_id, detector)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + "." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(report, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return _with_reference(report, project_reference)
    finally:
        with _busy_guard:
            _busy.discard(target)


async def cached_shots_payload(
    project: Path,
    run_id: str,
    repository: Path,
    detector: ShotDetector,
    *,
    project_reference: str,
) -> dict[str, object]:
    """The saved report when it still describes this run's footage, analysis and detector.

    No scan: a report made before the analysis gained events or stages is not shown.
    """
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timeline = await store.load_timeline(run_id, require_completed=False)
    finally:
        await store.close()
    asset = timeline.run.asset
    digest = shot_timeline_digest(
        timeline.run, timeline.events, saved_frames(timeline), timeline.checkpoints
    )
    missing: dict[str, object] = {
        "available": False,
        "schemaVersion": SHOT_REPORT_VERSION,
        "runId": run_id,
        "project": project_reference,
    }
    target = shot_cache_path(repository, project, run_id)
    try:
        if target.stat().st_size > MAX_CACHED_REPORT_BYTES:
            return missing
        report = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return missing
    detector_record = report.get("detector") if isinstance(report, dict) else None
    if (
        not isinstance(report, dict)
        or report.get("schemaVersion") != SHOT_REPORT_VERSION
        or report.get("runId") != run_id
        or report.get("sourceSha256") != asset.sha256
        or report.get("durationUs") != asset.duration_us
        or report.get("timelineDigest") != digest
        or not isinstance(detector_record, dict)
        or detector_record.get("filterGraph") != detector.identity.filter_graph
        or detector_record.get("name") != detector.identity.detector
    ):
        return missing
    return _with_reference(report, project_reference)
