"""Local game-knowledge files: one immutable JSON file per entry, never overwritten."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gamingcreator.application.knowledge import new_entry
from gamingcreator.infrastructure.local_paths import is_link

MAX_ENTRIES = 5000


class KnowledgeStore:
    def __init__(self, repository: Path) -> None:
        self.root = repository.resolve() / ".cache/workspace/knowledge"

    def _directory(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        if any(is_link(p) for p in (self.root, *self.root.parents)):
            raise ValueError("知识库目录不能使用链接。")
        return self.root

    def entries(self) -> list[dict[str, Any]]:
        directory = self._directory()
        files = sorted(directory.glob("*.json"))[:MAX_ENTRIES]
        loaded = []
        for path in files:
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # A damaged file is skipped rather than guessed.
            if isinstance(entry, dict) and entry.get("entryId") == path.stem:
                loaded.append(entry)
        return loaded

    def add(self, value: object) -> dict[str, Any]:
        entry = new_entry(value, datetime.now(UTC).isoformat())
        if entry["replaces"] is not None:
            previous = next((e for e in self.entries() if e["entryId"] == entry["replaces"]), None)
            if previous is None or previous["game"] != entry["game"]:
                raise ValueError("要替换的条目不存在或不属于同一个游戏。")
        target = self._directory() / f"{entry['entryId']}.json"
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, indent=2) + "\n")
        return entry
