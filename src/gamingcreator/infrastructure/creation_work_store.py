"""Immutable, explicitly created work identities under the creations root."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from gamingcreator.infrastructure.local_files import read_bounded, write_exclusive_text
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock


def _canonical(document: dict[str, object]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(document: dict[str, object]) -> str:
    return hashlib.sha256(_canonical(document).encode("utf-8")).hexdigest()


def _reject_links(path: Path) -> None:
    for candidate in (path, *path.parents):
        if is_link(candidate):
            raise ValueError("作品存储路径不能包含链接。")


class CreationWorkStore:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        _reject_links(self.root)

    def _path(self, work_id: str) -> Path:
        if not isinstance(work_id, str) or not re.fullmatch(r"[0-9a-f]{32}", work_id):
            raise ValueError("作品身份必须是32位小写十六进制请求ID。")
        path = self.root / f"{work_id}.json"
        _reject_links(path)
        return path

    def create(self, project_id: str, work_id: str) -> dict[str, object]:
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("作品必须属于素材项目。")
        path = self._path(work_id)
        self.root.mkdir(parents=True, exist_ok=True)
        _reject_links(self.root / ".analysis-writer.lock")
        lock = ProjectWriterLock(self.root)
        lock.acquire()
        try:
            path = self._path(work_id)
            if path.exists():
                return self.read(work_id, project_id)
            document: dict[str, object] = {
                "schemaVersion": "creation-work-v1",
                "workId": work_id,
                "projectId": project_id,
                "createdAt": datetime.now(UTC).isoformat(),
            }
            document["documentSha256"] = _digest(document)
            write_exclusive_text(path, _canonical(document) + "\n")
            return document
        finally:
            lock.close()

    def read(self, work_id: str, project_id: str | None = None) -> dict[str, object]:
        path = self._path(work_id)
        try:
            raw: object = json.loads(read_bounded(path).decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise ValueError("作品记录无法读取。") from error
        if not isinstance(raw, dict):
            raise ValueError("作品记录无效。")
        document = cast(dict[str, object], raw)
        payload = {key: value for key, value in document.items() if key != "documentSha256"}
        if (
            document.get("schemaVersion") != "creation-work-v1"
            or document.get("documentSha256") != _digest(payload)
            or document.get("workId") != work_id
            or (project_id is not None and document.get("projectId") != project_id)
        ):
            raise ValueError("作品记录版本、校验或归属不匹配。")
        return document

    def catalog(self, project_id: str) -> list[dict[str, object]]:
        _reject_links(self.root)
        if not self.root.exists():
            return []
        records = []
        for path in sorted(self.root.iterdir()):
            if re.fullmatch(r"[0-9a-f]{32}\.json", path.name):
                document = self.read(path.stem)
                if document.get("projectId") == project_id:
                    records.append(document)
        return sorted(records, key=lambda document: str(document["createdAt"]), reverse=True)
