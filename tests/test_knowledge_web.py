import hashlib
import http.client
import io
import socket
import time
from pathlib import Path

import pytest

from gamingcreator.infrastructure import public_https
from gamingcreator.infrastructure.knowledge_store import KnowledgeStore
from gamingcreator.infrastructure.rule_sources import html_text
from gamingcreator.ui import knowledge_web


def test_mixed_dns_answer_is_rejected_before_opening_a_socket(monkeypatch) -> None:
    endpoints = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443)),
        (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("fec0::10", 443, 0, 0)),
    ]
    monkeypatch.setattr(public_https.socket, "getaddrinfo", lambda *_a, **_kw: endpoints)

    def refuse(*_args):
        pytest.fail("A nonpublic DNS answer must fail before any network connection")

    monkeypatch.setattr(public_https.socket, "socket", refuse)
    with pytest.raises(ValueError, match="非公网"):
        public_https._connect("public.example.com", time.monotonic() + 1)


def test_public_url_only_accepts_anonymous_https() -> None:
    for url in (
        "http://example.com/",
        "https://example.com:8443/",
        "https://name@example.com/",
        "https://localhost/",
        "https://127.0.0.1/",
        "https://example.com/\nfoo",
    ):
        with pytest.raises(ValueError):
            public_https.public_url(url)
    assert public_https.public_url("https://example.com/游戏?type=update#section") == (
        "https://example.com/%E6%B8%B8%E6%88%8F?type=update"
    )


def test_partial_content_length_is_not_a_valid_preview() -> None:
    class Input:
        def makefile(self, *_args):
            return io.BytesIO(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 12\r\n\r\nshort"
            )

    response = http.client.HTTPResponse(Input())
    response.begin()
    with pytest.raises(ValueError, match="提前结束"):
        public_https._response_text(response, time.monotonic() + 1)


def test_html_patch_table_preserves_separate_number_columns() -> None:
    assert html_text(
        "<table><tr><th>旧值</th><th>新值</th></tr><tr><td>20</td><td>30</td></tr></table>"
    ) == ("旧值\t新值\n20\t30")


def test_preview_binds_game_and_original_excerpt_by_receipt(tmp_path: Path, monkeypatch) -> None:
    store = KnowledgeStore(tmp_path)
    reader = knowledge_web.KnowledgeWeb(store)
    fetched = {
        "url": "https://example.com/game-notes?edition=1",
        "title": "测试说明",
        "text": "第一段\r\n武道会须使用指定地图。\r\n第三段",
        "retrievedAt": "2026-11-21T03:00:00+00:00",
        "responseSha256": "a" * 64,
    }
    reads = []

    def read(url):
        reads.append(url)
        return fetched

    monkeypatch.setattr(knowledge_web, "read_public_page", read)
    preview = reader.preview({"game": "漫画群星", "url": "https://example.com/start"})
    assert not store.root.exists()
    body = {
        "game": "漫画群星",
        "title": "武道会",
        "sourceKind": "official",
        "text": "武道会须使用指定地图。",
        "webPreviewId": preview["previewId"],
    }
    with pytest.raises(ValueError, match="失效"):
        reader.save({**body, "game": "其他游戏"})
    with pytest.raises(ValueError, match="连续原文"):
        reader.save({**body, "text": "武道会使用任意地图。"})
    with pytest.raises(ValueError, match="字段"):
        reader.save({**body, "sourceLabel": "其他站点"})
    saved = reader.save(body)
    assert saved["text"] == body["text"]
    assert saved["source"]["label"] == "https://example.com/game-notes"
    assert saved["web"]["url"] == fetched["url"]
    assert saved["web"]["responseSha256"] == "a" * 64
    assert (
        saved["web"]["extractedTextSha256"] == hashlib.sha256(preview["text"].encode()).hexdigest()
    )
    assert store.entries() == [saved]
    with pytest.raises(ValueError, match="失效"):
        reader.save(body)
    assert reads == ["https://example.com/start"]
