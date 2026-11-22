"""Workbench on-screen text: an explicit local OCR scan, cached outside the project."""

import hashlib
import json
import threading
from pathlib import Path
from typing import cast
from uuid import uuid4

from gamingcreator.application.ocr_frames import FullResolutionFrames, OcrEngine
from gamingcreator.application.screen_text_reports import (
    FRAME_TEXT_VERSION,
    MAX_CACHED_REPORT_BYTES,
    frames_digest,
    scanned_frames,
)
from gamingcreator.cli.local_reports import load_saved_timeline
from gamingcreator.cli.ocr_frames import build_run_ocr_report
from gamingcreator.cli.shot_boundaries import saved_frames
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_files import read_bounded, write_exclusive_text
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

DENSITIES = ("quick", "full")
# "Quick" reads about one saved frame every two seconds; "full" reads every saved frame.
QUICK_SPACING_MS = 2000
_busy: set[Path] = set()
_busy_guard = threading.Lock()


def frame_text_cache_path(
    repository: Path, project: Path, run_id: str, *, for_write: bool = False
) -> Path:
    """Write only v2 caches; prefer v2 reads, with a read-only legacy fallback."""
    key = hashlib.sha256(f"{project.resolve()}\n{run_id}".encode()).hexdigest()[:32]
    directory = repository.resolve() / ".cache" / "workspace" / "frame-text"
    current = directory / f"{key}.v2.json"
    return current if for_write or current.exists() else directory / f"{key}.json"


def density_every(sampling_interval_ms: int, density: str) -> int:
    """How many saved frames to step over for a density choice."""
    if density == "full":
        return 1
    if density == "quick":
        return max(1, round(QUICK_SPACING_MS / sampling_interval_ms))
    raise AppError("input.frame_text", "识别密度须为quick或full。", ExitCode.INPUT)


def slim_report(report: dict[str, object], density: str) -> dict[str, object]:
    """What the page needs: texts and instants only, no word boxes or file paths."""
    rows = cast(list[dict[str, object]], report["frames"])
    engine = cast(dict[str, object], report["engine"])
    frames: list[dict[str, object]] = []
    for row in rows:
        if row["status"] != "text":
            continue
        lines: dict[str, bool] = {}
        for line in cast(list[dict[str, object]], row["lines"]):
            text = cast(str, line["text"])
            lines[text] = lines.get(text, False) or line["likelyText"] is True
        frames.append(
            {
                "timeUs": row["timeUs"],
                "lines": [{"text": text, "likelyText": likely} for text, likely in lines.items()],
            }
        )
    return {
        "schemaVersion": FRAME_TEXT_VERSION,
        "ocrSchemaVersion": report["schemaVersion"],
        "runId": report["runId"],
        "sourceSha256": report["sourceSha256"],
        "durationUs": report["durationUs"],
        "density": density,
        "every": report["every"],
        "framesDigest": frames_digest(
            [(cast(str, row["evidenceId"]), cast(int, row["timeUs"])) for row in rows]
        ),
        "engine": {
            "name": engine["name"],
            "platform": engine["platform"],
            "usedLanguages": engine["usedLanguages"],
            "unavailableLanguages": engine["unavailableLanguages"],
        },
        "seconds": report["seconds"],
        "summary": report["summary"],
        "recurringTexts": report["recurringTexts"],
        "frames": frames,
        "readOnly": True,
        "paidRequests": 0,
        "humanReviewed": False,
    }


def _with_reference(report: dict[str, object], reference: str) -> dict[str, object]:
    return {**report, "available": True, "project": reference}


async def scan_frame_text_payload(
    project: Path,
    run_id: str,
    repository: Path,
    frames: FullResolutionFrames,
    engine: OcrEngine,
    *,
    density: str,
    project_reference: str,
) -> dict[str, object]:
    """Read the run's on-screen text now (local, read-only) and replace its cached report."""
    if density not in DENSITIES:
        raise AppError("input.frame_text", "识别密度须为quick或full。", ExitCode.INPUT)
    target = frame_text_cache_path(repository, project, run_id, for_write=True)
    with _busy_guard:
        if target in _busy:
            raise AppError(
                "frame_text.busy", "这个任务正在识别画面文字，请稍候。", ExitCode.STORAGE
            )
        _busy.add(target)
    try:
        timeline = await load_saved_timeline(project, run_id)
        every = density_every(timeline.run.configuration.analysis.sampling_interval_ms, density)
        report = await build_run_ocr_report(
            project,
            run_id,
            frames,
            engine,
            repository.resolve() / ".cache" / "ocr-frames",
            every=every,
        )
        payload = slim_report(report, density)
        temporary = target.with_name(target.name + "." + uuid4().hex + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(payload, ensure_ascii=False) + "\n"
            write_exclusive_text(temporary, content)
            temporary.replace(target)
            receipt = target.with_name(target.name + ".sha256")
            write_exclusive_text(
                temporary, hashlib.sha256(content.encode("utf-8")).hexdigest() + "\n"
            )
            temporary.replace(receipt)
        except (OSError, ValueError):
            raise AppError(
                "frame_text.cache",
                "画面文字已识别，但保存到工作台缓存失败（磁盘空间或权限），请稍后重试。",
                ExitCode.STORAGE,
            ) from None
        finally:
            temporary.unlink(missing_ok=True)
        return _with_reference({**payload, "contentVerified": True}, project_reference)
    finally:
        with _busy_guard:
            _busy.discard(target)


async def cached_frame_text_payload(
    project: Path,
    run_id: str,
    repository: Path,
    engine: OcrEngine,
    *,
    project_reference: str,
) -> dict[str, object]:
    """The saved report when it still describes this run's footage, frames and engine.

    No scan: a report whose source, saved frame instants or engine changed is not shown.
    """
    missing: dict[str, object] = {
        "available": False,
        "schemaVersion": FRAME_TEXT_VERSION,
        "runId": run_id,
        "project": project_reference,
    }
    target = frame_text_cache_path(repository, project, run_id)
    if not target.is_file():
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            await store.load_run(run_id)
        finally:
            await store.close()
        return missing
    try:
        if target.stat().st_size > MAX_CACHED_REPORT_BYTES:
            return missing
        raw = read_bounded(target, MAX_CACHED_REPORT_BYTES)
        report = json.loads(raw)
        receipt = target.with_name(target.name + ".sha256")
        verified = receipt.exists()
        if target.name.endswith(".v2.json") and not verified:
            return missing
        if (
            verified
            and read_bounded(receipt, 65).decode("ascii").strip() != hashlib.sha256(raw).hexdigest()
        ):
            return missing
    except (OSError, ValueError):
        return missing
    if not isinstance(report, dict):
        return missing
    timeline = await load_saved_timeline(project, run_id)
    asset = timeline.run.asset
    every, recorded = report.get("every"), report.get("engine")
    identity = engine.identity()
    if (
        report.get("schemaVersion") != FRAME_TEXT_VERSION
        or report.get("runId") != run_id
        or report.get("sourceSha256") != asset.sha256
        or report.get("durationUs") != asset.duration_us
        or type(every) is not int
        or every < 1
        or report.get("framesDigest")
        != frames_digest(scanned_frames(saved_frames(timeline), every))
        or not isinstance(recorded, dict)
        or recorded.get("name") != identity.engine
        or recorded.get("platform") != identity.platform
    ):
        return missing
    return _with_reference({**report, "contentVerified": verified}, project_reference)
