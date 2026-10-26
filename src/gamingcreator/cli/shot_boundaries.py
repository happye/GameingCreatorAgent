"""Production CLI assembly for the read-only local shot-boundary report."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.shot_boundaries import (
    ShotDetector,
    build_shot_report,
    shot_summary,
)
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.ffmpeg_media import hash_source
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

_SOURCE_CHANGED = "原片已不在原位置或内容已改变，未生成镜头报告。"
_NEW_FILE = "镜头报告须写到新的文件。"


def _refuse_output(output: Path, project: Path, source: Path) -> None:
    target = output.resolve()
    project, footage = project.resolve(), source.resolve().parent
    if target.exists():
        raise AppError("input.shot_output", _NEW_FILE, ExitCode.INPUT)
    if project in target.parents or footage in target.parents:
        raise AppError(
            "input.shot_output", "镜头报告不能写进项目目录或原片所在目录。", ExitCode.INPUT
        )


async def _verified_source_hash(source: Path, context: CancellationContext) -> str:
    try:
        if not source.is_file():
            raise AppError("input.source_changed", _SOURCE_CHANGED, ExitCode.INPUT)
        return await hash_source(source, context)
    except OSError:
        raise AppError("input.source_changed", _SOURCE_CHANGED, ExitCode.INPUT) from None


def saved_frames(timeline: StoredTimeline) -> tuple[tuple[str, int], ...]:
    """The run's saved images as (evidence id, source instant)."""
    return tuple(
        (item.evidence_id, item.source_time.time_us)
        for item in timeline.evidence
        if item.kind == "image" and isinstance(item.source_time, SourceInstant)
    )


async def build_run_shot_report(
    project: Path,
    run_id: str,
    detector: ShotDetector,
    *,
    before_scan: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    """Scan the run's original footage locally; reads the project read-only, writes nothing.

    ``before_scan`` receives the source path once the run is loaded, before any decoding.
    """
    if not (project / "timeline.sqlite3").is_file():
        raise AppError("input.project", "找不到已分析的项目数据库。", ExitCode.INPUT)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timeline = await store.load_timeline(run_id, require_completed=False)
    finally:
        await store.close()
    asset = timeline.run.asset
    if before_scan is not None:
        before_scan(asset.source_path)
    seconds = asset.duration_us / 1_000_000
    context = CancellationContext("detect-shots", 600 + 2 * seconds)
    if await _verified_source_hash(asset.source_path, context) != asset.sha256:
        raise AppError("input.source_changed", _SOURCE_CHANGED, ExitCode.INPUT)
    version = await detector.tool_version(context)
    samples = await detector.samples(asset, context)
    if await _verified_source_hash(asset.source_path, context) != asset.sha256:
        raise AppError("input.source_changed", _SOURCE_CHANGED, ExitCode.INPUT)
    return build_shot_report(
        timeline.run,
        timeline.events,
        samples,
        detector.identity,
        version,
        frames=saved_frames(timeline),
        checkpoints=timeline.checkpoints,
    )


async def execute_detect_shots(
    project: Path, run_id: str, output: Path, detector: ShotDetector
) -> dict[str, object]:
    """CLI: scan the run's footage and save the report to one new file."""
    report = await build_run_shot_report(
        project,
        run_id,
        detector,
        before_scan=lambda source: _refuse_output(output, project, source),
    )
    target = output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # A hard link publishes the complete file but never replaces one created meanwhile.
        try:
            os.link(temporary, target)
        except FileExistsError:
            raise AppError("input.shot_output", _NEW_FILE, ExitCode.INPUT) from None
        except OSError:
            raise AppError(
                "input.shot_output",
                "无法在这个位置创建报告文件（该磁盘可能不支持硬链接），请换一个本机NTFS目录。",
                ExitCode.INPUT,
            ) from None
    finally:
        temporary.unlink(missing_ok=True)
    for line in shot_summary(report):
        print(line)
    print(f"报告已保存：{target}")
    return report
