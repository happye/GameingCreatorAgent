"""CLI: import a local folder of notes into the game knowledge store."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from gamingcreator.application.knowledge_import import import_knowledge_directory
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.knowledge_store import KnowledgeStore


async def execute_import_knowledge(
    repository: Path,
    *,
    game: str,
    directory: Path,
    source_kind: str,
    source_label: str,
    include_media: bool,
) -> None:
    try:
        report = await import_knowledge_directory(
            KnowledgeStore(repository),
            game=game,
            directory=directory,
            source_kind=source_kind,
            source_label=source_label,
            include_media=include_media,
            scratch=repository.resolve() / ".cache/workspace/knowledge-import",
        )
    except ValueError as error:
        raise AppError("knowledge.import", str(error), ExitCode.INPUT) from error
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if report["summary"]["imported"] == 0 and report["summary"]["considered"] > 0:
        raise AppError(
            "knowledge.import",
            "目录导入没有成功写入任何条目（见上方明细）。",
            ExitCode.INPUT,
        )