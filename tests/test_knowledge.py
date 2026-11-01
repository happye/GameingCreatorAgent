"""Game knowledge: immutable cited entries, version history, game-scoped search."""

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from gamingcreator.application.knowledge import current, history, is_valid, new_entry, search
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


def test_stale_replace_damaged_files_and_windows_line_breaks(tmp_path):
    store = KnowledgeStore(tmp_path)
    base = {"game": "代号Atom", "title": "冷却", "sourceKind": "user", "sourceLabel": "笔记"}
    first = store.add({**base, "text": "冷却10秒"})
    store.add({**base, "text": "冷却8秒", "replaces": first["entryId"]})
    with pytest.raises(ValueError, match="更新的版本"):
        store.add({**base, "text": "冷却6秒", "replaces": first["entryId"]})
    assert [e["text"] for e in current(store.entries())] == ["冷却8秒"]
    damaged = store.root / f"{'a' * 64}.json"
    damaged.write_text(json.dumps({"entryId": "a" * 64}), encoding="utf-8")
    forged = {**first, "text": "改过的内容"}
    (store.root / f"{first['entryId']}.json").write_text(json.dumps(forged), encoding="utf-8")
    assert not is_valid(forged)
    assert all(e["entryId"] != "a" * 64 for e in store.entries())
    assert search(store.entries(), "代号Atom", "冷却")
    crlf = store.add({**base, "title": "规则", "text": "第一行\r\n第二行"})
    assert crlf["text"] == "第一行\n第二行"


def test_draft_quotes_the_matching_clause_whole_or_not_at_all():
    from gamingcreator.application.narration_script import build_narration_script
    from gamingcreator.domain.creation import CreativeBrief

    brief = CreativeBrief(
        "代号Atom", "guide", ("bilibili",), 30, "冷却", "新玩家", "简洁", ("冷却",), ()
    )
    rows = [{"clipId": "a", "scriptDraft": "角色奔跑", "outputStartFrame": 0}]
    later = search([entry("技能", "背景故事很长。冷却时间是10秒。")], brief.game, "冷却")
    draft = build_narration_script(brief, rows, 900, 30, later)
    assert "冷却时间是10秒" in draft["text"] and "背景故事" not in draft["text"]
    long_rule = "冷却技能A可以无限使用，除非角色处于沉默状态或者被敌方控制时无法施放"
    risky = search([entry("技能", long_rule)], brief.game, "冷却")
    quoted = build_narration_script(brief, rows, 900, 30, risky)
    assert quoted["citations"] == [] and "无限使用" not in quoted["text"]
    marker = search([entry("操作", "冷却时按f12打开面板")], brief.game, "冷却")
    assert "按f12打开面板" in build_narration_script(brief, rows, 900, 30, marker)["text"]


def test_narration_draft_cites_matching_knowledge_without_speaking_the_source():
    from gamingcreator.application.knowledge import search
    from gamingcreator.application.narration_script import build_narration_script
    from gamingcreator.domain.creation import CreativeBrief

    brief = CreativeBrief(
        "代号Atom", "guide", ("bilibili",), 30, "新英雄玩法", "新玩家", "简洁", ("新英雄",), ()
    )
    knowledge = search(
        [entry("新英雄", "贝多芬可以召唤音符击退敌人")], brief.game, "新英雄 新英雄玩法"
    )
    rows = [{"clipId": "a", "scriptDraft": "角色奔跑", "outputStartFrame": 0}]
    draft = build_narration_script(brief, rows, 900, 30, knowledge)
    assert "贝多芬可以召唤音符击退敌人" in draft["text"] and "来源" not in draft["text"]
    assert draft["citations"][0]["citation"].startswith("（来源：官方说明")
    tight = build_narration_script(brief, rows, 120, 30, knowledge)
    assert tight["citations"] == [] and "贝多芬" not in tight["text"]
