"""Local game-knowledge files: one immutable JSON file per entry, never overwritten."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gamingcreator.application.knowledge import is_valid, new_entry
from gamingcreator.infrastructure.local_paths import is_link

MAX_ENTRIES = 5000


class KnowledgeStore:
    def __init__(self, repository: Path) -> None:
        self.root = repository.resolve() / ".cache/workspace/knowledge"

    def _directory(self) -> Path:
        # Check before creating, so a linked .cache never gets a folder made on its target.
        if any(is_link(p) for p in (self.root, *self.root.parents) if p.exists()):
            raise ValueError("知识库目录不能使用链接。")
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def entries(self) -> list[dict[str, Any]]:
        directory = self._directory()
        # Newest files first, so a cap never drops the latest versions of an entry.
        files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        files = files[:MAX_ENTRIES]
        loaded = []
        for path in files:
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # A damaged file is skipped rather than guessed.
            if is_valid(entry) and entry["entryId"] == path.stem:
                loaded.append(entry)
        return loaded

    def add(self, value: object) -> dict[str, Any]:
        entry = new_entry(value, datetime.now(UTC).isoformat())
        if entry["replaces"] is not None:
            entries = self.entries()
            previous = next((e for e in entries if e["entryId"] == entry["replaces"]), None)
            if previous is None or previous["game"] != entry["game"]:
                raise ValueError("要替换的条目不存在或不属于同一个游戏。")
            if any(e.get("replaces") == entry["replaces"] for e in entries):
                # Replacing an old version again would leave two "latest" entries side by side.
                raise ValueError("这个条目已经有更新的版本，请在最新版本上修改。")
        target = self._directory() / f"{entry['entryId']}.json"
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, indent=2) + "\n")
        return entry
