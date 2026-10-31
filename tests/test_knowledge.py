"""Game knowledge: immutable cited entries, version history, game-scoped search."""

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from gamingcreator.application.knowledge import current, history, new_entry, search
from gamingcreator.infrastructure.knowledge_store import KnowledgeStore


def entry(title, text, replaces=None, game="代号Atom", at="2026-11-01T00:00:00+00:00"):
    value = {
        "game": game,
        "title": title,
        "text": text,
        "sourceKind": "official",
        "sourceLabel": "官网公告",
    }
    if replaces:
        value["replaces"] = replaces
    return new_entry(value, at)


def test_entries_are_validated_and_content_addressed():
    first = entry("新英雄", "贝多芬可以召唤音符")
    assert first == entry("新英雄", "贝多芬可以召唤音符") and len(first["entryId"]) == 64
    for bad in (
        {"game": "", "title": "t", "text": "x", "sourceKind": "user", "sourceLabel": "s"},
        {"game": "g", "title": "t", "text": "x", "sourceKind": "rumor", "sourceLabel": "s"},
        {"game": "g", "title": "t", "text": "x" * 20001, "sourceKind": "user", "sourceLabel": "s"},
        {
            "game": "g",
            "title": "t",
            "text": "x",
            "sourceKind": "user",
            "sourceLabel": "s",
            "extra": 1,
        },
        {
            "game": "g",
            "title": "t",
            "text": "x",
            "sourceKind": "user",
            "sourceLabel": "s",
            "replaces": "x",
        },
    ):
        with pytest.raises(ValueError):
            new_entry(bad, "2026-11-01")


def test_versions_search_and_citation():
    old = entry("新英雄", "贝多芬可以召唤音符")
    new = entry(
        "新英雄",
        "贝多芬可以召唤音符并击退敌人",
        replaces=old["entryId"],
        at="2026-11-02T00:00:00+00:00",
    )
    other = entry("地图", "齿轮平台会旋转")
    foreign = entry("新英雄", "别的游戏", game="其他游戏")
    entries = [old, new, other, foreign]
    assert [e["entryId"] for e in current(entries)] == [
        new["entryId"],
        other["entryId"],
        foreign["entryId"],
    ]
    assert [e["entryId"] for e in history(entries, new["entryId"])] == [
        new["entryId"],
        old["entryId"],
    ]
    found = search(entries, "代号atom", "新英雄 击退")
    assert [e["entryId"] for e in found] == [new["entryId"]]
    assert found[0]["citation"] == "（来源：官方说明·官网公告，2026-11-02）"
    assert len(search(entries, "代号Atom", "")) == 2


def test_store_keeps_files_immutable_and_game_scoped(tmp_path):
    store = KnowledgeStore(tmp_path)
    first = store.add(
        {
            "game": "代号Atom",
            "title": "新英雄",
            "text": "贝多芬",
            "sourceKind": "wiki",
            "sourceLabel": "wiki",
        }
    )
    with pytest.raises(ValueError):
        store.add(
            {
                "game": "其他游戏",
                "title": "改",
                "text": "改",
                "sourceKind": "user",
                "sourceLabel": "我",
                "replaces": first["entryId"],
            }
        )
    second = store.add(
        {
            "game": "代号Atom",
            "title": "新英雄",
            "text": "贝多芬v2",
            "sourceKind": "user",
            "sourceLabel": "我",
            "replaces": first["entryId"],
        }
    )
    assert {e["entryId"] for e in store.entries()} == {first["entryId"], second["entryId"]}


def test_http_add_from_text_and_file_then_search_and_history(tmp_path):
    from gamingcreator.ui.server import create_server

    server = create_server("127.0.0.1", 0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/api/knowledge"

    def post(body):
        request = urllib.request.Request(
            base, json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def get(query):
        with urllib.request.urlopen(base + "?" + query) as response:
            return json.loads(response.read())

    try:
        typed = post(
            {
                "game": "代号Atom",
                "title": "新英雄",
                "text": "贝多芬召唤音符",
                "sourceKind": "official",
                "sourceLabel": "官网",
            }
        )
        filed = post(
            {
                "game": "代号Atom",
                "title": "地图说明",
                "sourceKind": "wiki",
                "sourceLabel": "攻略站",
                "fileName": "map.txt",
                "dataBase64": base64.b64encode("齿轮平台会旋转".encode()).decode(),
            }
        )
        assert filed["text"] == "齿轮平台会旋转" and filed["source"]["kind"] == "wiki"
        found = get("game=%E4%BB%A3%E5%8F%B7Atom&q=%E9%BD%BF%E8%BD%AE")
        assert [e["entryId"] for e in found["entries"]] == [filed["entryId"]]
        assert get(f"entryId={typed['entryId']}")["history"][0]["entryId"] == typed["entryId"]
        with pytest.raises(urllib.error.HTTPError) as refused:
            post(
                {
                    "game": "代号Atom",
                    "title": "",
                    "text": "x",
                    "sourceKind": "user",
                    "sourceLabel": "s",
                }
            )
        assert refused.value.code == 400 and json.loads(refused.value.read())["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
