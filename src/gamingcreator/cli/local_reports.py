"""Where read-only local reports may be written, and how they are published."""

import json
import os
from pathlib import Path
from uuid import uuid4

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import MediaAsset
from gamingcreator.infrastructure.ffmpeg_media import hash_source
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

NEW_FILE = "报告须写到新的文件。"


async def load_saved_timeline(project: Path, run_id: str) -> StoredTimeline:
    """The run's saved timeline (any status), with the project opened read-only."""
    if not (project / "timeline.sqlite3").is_file():
        raise AppError("input.project", "找不到已分析的项目数据库。", ExitCode.INPUT)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        return await store.load_timeline(run_id, require_completed=False)
    finally:
        await store.close()


async def require_unchanged_source(
    asset: MediaAsset, context: CancellationContext, message: str
) -> None:
    """The original footage is still at its registered path with its registered bytes."""
    try:
        if asset.source_path.is_file() and await hash_source(asset.source_path, context) == (
            asset.sha256
        ):
            return
    except OSError:
        pass
    raise AppError("input.source_changed", message, ExitCode.INPUT)


def refuse_report_output(output: Path, project: Path, source: Path) -> None:
    """A report is a new file outside the project and outside the footage directory."""
    target = output.resolve()
    project, footage = project.resolve(), source.resolve().parent
    if target.exists():
        raise AppError("input.report_output", NEW_FILE, ExitCode.INPUT)
    if project in target.parents or footage in target.parents:
        raise AppError(
            "input.report_output", "报告不能写进项目目录或原片所在目录。", ExitCode.INPUT
        )


def publish_new_report(output: Path, report: dict[str, object]) -> Path:
    """Write the complete JSON, then hard-link it into place; never replaces a file."""
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
            raise AppError("input.report_output", NEW_FILE, ExitCode.INPUT) from None
        except OSError:
            raise AppError(
                "input.report_output",
                "无法在这个位置创建报告文件（该磁盘可能不支持硬链接），请换一个本机NTFS目录。",
                ExitCode.INPUT,
            ) from None
    finally:
        temporary.unlink(missing_ok=True)
    return target
