"""Batch-import local folder files into the game knowledge store (no network).

Reads only direct children of a chosen directory. Text/markdown are default; screenshots
and PDFs are opt-in and reuse the same local OCR path as single-file knowledge upload.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from gamingcreator.application.knowledge import LIMITS, SOURCE_KINDS, current
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.knowledge_store import KnowledgeStore
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.rule_sources import (
    IMAGE_SUFFIXES,
    MAX_BYTES,
    read_rule_source,
)

SCHEMA = "knowledge-directory-import-v1"
MAX_FILES = 50
TEXT_SUFFIXES = {".txt", ".md"}
MEDIA_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}


def _suffixes(*, include_media: bool) -> set[str]:
    return TEXT_SUFFIXES | MEDIA_SUFFIXES if include_media else set(TEXT_SUFFIXES)


def _title_from_name(name: str) -> str:
    stem = Path(name).stem.strip() or name
    return stem[: LIMITS["title"]]


def _source_label(base: str, relative: str, extra: str = "") -> str:
    parts = [part for part in (base.strip(), "目录导入", relative, extra.strip()) if part]
    label = " · ".join(parts)
    return label[: LIMITS["sourceLabel"]]


def list_import_candidates(directory: Path, *, include_media: bool = False) -> list[Path]:
    """Sorted direct child files matching allowed suffixes; refuses links."""
    root = directory.expanduser()
    if not root.exists():
        raise ValueError("目录不存在。")
    root = root.resolve()
    if not root.is_dir() or is_link(root):
        raise ValueError("请选择本机普通文件夹（不能是文件或符号链接）。")
    if any(is_link(p) for p in root.parents if p.exists()):
        raise ValueError("知识导入目录路径不能经过符号链接。")
    allowed = _suffixes(include_media=include_media)
    found: list[Path] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if is_link(path) or not path.is_file():
            continue
        if path.suffix.casefold() in allowed:
            found.append(path)
    if len(found) > MAX_FILES:
        raise ValueError(f"目录内可导入文件超过 {MAX_FILES} 个，请拆分后再导入。")
    return found


async def _read_file(path: Path, scratch: Path) -> dict[str, object]:
    data = read_bounded(path, MAX_BYTES)
    if not data:
        raise ValueError("文件为空。")
    return await read_rule_source(
        path.name, data, scratch, CancellationContext(f"knowledge-import-{path.name}", 180)
    )


async def import_knowledge_directory(
    store: KnowledgeStore,
    *,
    game: str,
    directory: Path,
    source_kind: str,
    source_label: str,
    include_media: bool = False,
    scratch: Path | None = None,
) -> dict[str, Any]:
    """Import eligible files from one folder into the knowledge store."""
    if source_kind not in SOURCE_KINDS:
        raise ValueError("来源类型只能是官方说明、Wiki/攻略站或用户资料。")
    if not isinstance(source_label, str) or len(source_label) > LIMITS["sourceLabel"]:
        raise ValueError(f"来源说明需在 0–{LIMITS['sourceLabel']} 字。")
    candidates = list_import_candidates(directory, include_media=include_media)
    work = (scratch or (store.root.parent / "knowledge-import")).resolve()
    items: list[dict[str, Any]] = []
    known_texts = {(entry["game"], entry["text"]) for entry in current(store.entries())}
    for path in candidates:
        relative = path.name
        try:
            source = await _read_file(path, work)
            text = str(source["text"]).replace("\r\n", "\n").replace("\r", "\n")
            if not text.strip():
                raise ValueError("读出的正文为空。")
            if len(text) > LIMITS["text"]:
                raise ValueError(f"读出 {len(text)} 字，超过单条 {LIMITS['text']} 字上限。")
            extra = ""
            if source.get("sourceKind") in ("image", "pdf"):
                extra = "文字由本机OCR识别，可能有错字"
            if source.get("pagesRead") != source.get("pages") and source.get("pages"):
                extra = (
                    f"{extra + '；' if extra else ''}"
                    f"只读了前 {source['pagesRead']}/{source['pages']} 页"
                )
            payload = {
                "game": game,
                "title": _title_from_name(path.name),
                "text": text,
                "sourceKind": source_kind,
                "sourceLabel": _source_label(source_label, relative, extra),
            }
            # createdAt is hashed into entryId, so identical notes re-imported later
            # would otherwise create duplicates; compare stripped body like new_entry.
            normalized = text.strip()
            if (game.strip(), normalized) in known_texts:
                items.append(
                    {
                        "file": relative,
                        "status": "skipped",
                        "reason": "相同正文已在知识库中。",
                    }
                )
                continue
            try:
                entry = store.add(payload)
            except FileExistsError:
                items.append(
                    {
                        "file": relative,
                        "status": "skipped",
                        "reason": "相同内容已在知识库中。",
                    }
                )
                continue
            known_texts.add((entry["game"], entry["text"]))
            items.append(
                {
                    "file": relative,
                    "status": "imported",
                    "entryId": entry["entryId"],
                    "title": entry["title"],
                }
            )
        except (AppError, OSError, ValueError, UnicodeError) as error:
            message = getattr(error, "message", None) or str(error)
            items.append({"file": relative, "status": "failed", "reason": message})
    summary = {
        "imported": sum(1 for item in items if item["status"] == "imported"),
        "skipped": sum(1 for item in items if item["status"] == "skipped"),
        "failed": sum(1 for item in items if item["status"] == "failed"),
        "considered": len(candidates),
    }
    return {
        "schemaVersion": SCHEMA,
        "directory": str(directory.expanduser().resolve()),
        "includeMedia": bool(include_media),
        "items": items,
        "summary": summary,
    }


def import_knowledge_directory_sync(
    store: KnowledgeStore,
    *,
    game: str,
    directory: Path,
    source_kind: str,
    source_label: str,
    include_media: bool = False,
    scratch: Path | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        import_knowledge_directory(
            store,
            game=game,
            directory=directory,
            source_kind=source_kind,
            source_label=source_label,
            include_media=include_media,
            scratch=scratch,
        )
    )
