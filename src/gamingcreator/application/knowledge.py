"""Game knowledge entries: versioned, source-cited text a person adds (no model, no crawling).

An entry is immutable. Editing creates a new entry that names the one it replaces, so every
earlier version stays readable and every quoted sentence can be traced to its source.
"""

import hashlib
import json
import re
import unicodedata
from typing import Any

SOURCE_KINDS = {"official": "官方说明", "wiki": "Wiki/攻略站", "user": "用户资料"}
LIMITS = {"game": 100, "title": 100, "text": 20000, "sourceLabel": 200}


def _clean(value: object, field: str) -> str:
    if isinstance(value, str):
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    if not isinstance(value, str) or not value.strip() or len(value) > LIMITS[field]:
        raise ValueError(f"{field} 需为1–{LIMITS[field]}字。")
    if any(unicodedata.category(c).startswith("C") and c not in "\n\t" for c in value):
        raise ValueError(f"{field} 含不支持的控制字符。")
    return value.strip()


def new_entry(value: object, created_at: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or not {"game", "title", "text", "sourceKind", "sourceLabel"} <= set(value)
        or set(value) - {"game", "title", "text", "sourceKind", "sourceLabel", "replaces"}
    ):
        raise ValueError("知识条目字段不完整。")
    if value["sourceKind"] not in SOURCE_KINDS:
        raise ValueError("来源类型只能是官方说明、Wiki/攻略站或用户资料。")
    replaces = value.get("replaces")
    if replaces is not None and (
        not isinstance(replaces, str) or re.fullmatch(r"[0-9a-f]{64}", replaces) is None
    ):
        raise ValueError("替换的条目编号无效。")
    entry: dict[str, Any] = {
        "schemaVersion": "game-knowledge-v1",
        "game": _clean(value["game"], "game"),
        "title": _clean(value["title"], "title"),
        "text": _clean(value["text"], "text"),
        "source": {
            "kind": value["sourceKind"],
            "label": _clean(value["sourceLabel"], "sourceLabel"),
        },
        "replaces": replaces,
        "createdAt": created_at,
    }
    entry["entryId"] = hashlib.sha256(
        json.dumps(entry, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return entry


def is_valid(entry: object) -> bool:
    """A stored entry whose fields are complete and whose ID is the hash of its content."""
    if not isinstance(entry, dict) or not isinstance(entry.get("source"), dict):
        return False
    if not all(isinstance(entry.get(k), str) for k in ("game", "title", "text", "createdAt")):
        return False
    body = {k: v for k, v in entry.items() if k != "entryId"}
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return entry.get("entryId") == digest.hexdigest()


def current(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Latest versions only: an entry named by another entry's ``replaces`` is history."""
    replaced = {e["replaces"] for e in entries if e.get("replaces")}
    return [e for e in entries if e["entryId"] not in replaced]


def history(entries: list[dict[str, Any]], entry_id: str) -> list[dict[str, Any]]:
    by_id = {e["entryId"]: e for e in entries}
    chain, seen = [], set()
    while entry_id in by_id and entry_id not in seen:
        seen.add(entry_id)
        chain.append(by_id[entry_id])
        entry_id = by_id[entry_id].get("replaces") or ""
    return chain


def query_words(query: str) -> list[str]:
    return [w for w in re.split(r"[\s,，、；;]+", query.casefold()) if w]


def search(entries: list[dict[str, Any]], game: str, query: str) -> list[dict[str, Any]]:
    """Current entries of one game ranked by how often the query's words occur (title ×3)."""
    words = query_words(query)
    results = []
    for entry in current([e for e in entries if e["game"].casefold() == game.casefold()]):
        title, text = entry["title"].casefold(), entry["text"].casefold()
        score = sum(3 * title.count(w) + text.count(w) for w in words) if words else 1
        if score:
            results.append({**entry, "score": score, "citation": citation(entry)})
    return sorted(results, key=lambda e: (-e["score"], e["createdAt"]), reverse=False)


def citation(entry: dict[str, Any]) -> str:
    return f"（来源：{SOURCE_KINDS[entry['source']['kind']]}·{entry['source']['label']}，{entry['createdAt'][:10]}）"
