"""Short-lived previews bind the saved excerpt to exactly what the user reviewed."""

import hashlib
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from gamingcreator.application.knowledge import LIMITS
from gamingcreator.infrastructure.knowledge_store import KnowledgeStore
from gamingcreator.infrastructure.public_https import read_public_page


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(
        c for c in text if c in "\n\t" or not unicodedata.category(c).startswith("C")
    ).strip()


@dataclass(frozen=True, slots=True)
class _Preview:
    game: str
    text: str
    deadline: float
    web: dict[str, str]


class KnowledgeWeb:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store
        self._guard = threading.Lock()
        self._network_slots = threading.BoundedSemaphore(2)
        self._previews: dict[str, _Preview] = {}

    def preview(self, value: object) -> dict[str, object]:
        if (
            not isinstance(value, dict)
            or set(value) != {"game", "url"}
            or any(not isinstance(field, str) or not field.strip() for field in value.values())
            or len(value["game"]) > LIMITS["game"]
        ):
            raise ValueError("请先填写游戏名和公开网页地址。")
        if not self._network_slots.acquire(blocking=False):
            raise ValueError("已有网页正在读取，请稍后重试。")
        try:
            result = read_public_page(value["url"].strip())
        finally:
            self._network_slots.release()
        text = _normalize(result["text"])
        if not text:
            raise ValueError("网页未返回可摘录的正文，可改用本地截图或文件。")
        displayed = text[: LIMITS["text"]].rstrip()
        key = uuid4().hex
        web = {field: result[field] for field in ("url", "retrievedAt", "responseSha256")}
        web["extractedTextSha256"] = hashlib.sha256(text.encode()).hexdigest()
        with self._guard:
            if len(self._previews) >= 16:
                self._previews.pop(next(iter(self._previews)))
            self._previews[key] = _Preview(
                value["game"].strip(), displayed, time.monotonic() + 600, web
            )
        return {
            "previewId": key,
            "title": _normalize(result["title"])[: LIMITS["title"]],
            "text": displayed,
            "truncated": len(text) > len(displayed),
            **web,
        }

    def save(self, value: dict[str, Any]) -> dict[str, Any]:
        required = {"game", "title", "text", "sourceKind", "webPreviewId"}
        if not required <= set(value) <= required | {"replaces"} or not all(
            isinstance(value[field], str) for field in required
        ):
            raise ValueError("网页摘录字段无效。")
        key = value["webPreviewId"]
        text = value["text"].replace("\r\n", "\n").replace("\r", "\n").strip()
        with self._guard:
            entry = self._previews.get(key)
            if (
                entry is None
                or entry.deadline <= time.monotonic()
                or entry.game != value["game"].strip()
            ):
                raise ValueError("网页预览已失效，请为当前游戏重新读取。")
            if not text or text not in entry.text:
                raise ValueError("请只保留所读网页中的连续原文摘录。")
            url = entry.web["url"]
            source = urlsplit(url)
            # Keep query parameters local to the verified receipt, outside model context.
            citation_url = source._replace(query="").geturl()
            label = (
                citation_url
                if len(citation_url) <= LIMITS["sourceLabel"]
                else source.netloc[: LIMITS["sourceLabel"]]
            )
            saved = self.store.add(
                {k: v for k, v in value.items() if k != "webPreviewId"}
                | {"text": text, "sourceLabel": label},
                web=entry.web,
            )
            del self._previews[key]
        return saved
