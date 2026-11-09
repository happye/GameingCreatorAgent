"""Game knowledge: immutable cited entries, version history, game-scoped search."""

import base64
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gamingcreator.application.knowledge import (
    compare_entries,
    current,
    history,
    is_valid,
    new_entry,
    search,
)
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


def test_compare_patch_notes_preserves_text_sources_and_direction():
    old = entry("补丁一", "公共😀\n\n删除技能\n数值10")
    new = entry("补丁二", "公共😀\n\n新增技能\n数值20", old["entryId"], at="2026-11-02")
    original = json.dumps([old, new], ensure_ascii=False)
    result = compare_entries([old, new], old["entryId"], new["entryId"])
    assert result["schemaVersion"] == "game-knowledge-comparison-v1"
    assert result["before"]["entryId"] == old["entryId"]
    assert result["after"]["citation"] == "（来源：官方说明·官网公告，2026-11-02）"
    assert result["rows"][:2] == [
        {"kind": "equal", "text": "公共😀\n"},
        {"kind": "equal", "text": "\n"},
    ]
    for side, excluded in (("before", "added"), ("after", "removed")):
        assert (
            "".join(r["text"] for r in result["rows"] if r["kind"] != excluded)
            == result[side]["text"]
        )
    assert not result["sameText"]
    assert json.dumps([old, new], ensure_ascii=False) == original
    same_body = new_entry(
        {
            "game": old["game"],
            "title": "出处不同",
            "text": old["text"],
            "sourceKind": "wiki",
            "sourceLabel": "另一来源",
        },
        "2026-11-03",
    )
    same = compare_entries([old, same_body], old["entryId"], same_body["entryId"])
    assert same["sameText"] and all(row["kind"] == "equal" for row in same["rows"])
    assert same["before"]["createdAt"] != same["after"]["createdAt"]
    assert same["before"]["source"] != same["after"]["source"]
    foreign = entry("其他", "内容", game="其他游戏")
    with pytest.raises(ValueError, match="同一个游戏"):
        compare_entries([old, foreign], old["entryId"], foreign["entryId"])
    with pytest.raises(ValueError, match="不存在"):
        compare_entries([old], old["entryId"], "0" * 64)


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
        files = {p: p.read_bytes() for p in KnowledgeStore(tmp_path).root.glob("*.json")}
        compared = get(f"before={typed['entryId']}&after={filed['entryId']}")
        assert compared["before"]["text"] == typed["text"]
        assert compared["after"]["text"] == filed["text"]
        assert compared["rows"] == [
            {"kind": "removed", "text": typed["text"]},
            {"kind": "added", "text": filed["text"]},
        ]
        assert {p: p.read_bytes() for p in KnowledgeStore(tmp_path).root.glob("*.json")} == files
        foreign = post(
            {
                "game": "其他游戏",
                "title": "补丁",
                "text": "正文",
                "sourceKind": "user",
                "sourceLabel": "用户资料",
            }
        )
        for other in (foreign["entryId"], "0" * 64):
            with pytest.raises(urllib.error.HTTPError) as refused_comparison:
                get(f"before={typed['entryId']}&after={other}")
            with refused_comparison.value as error:
                assert error.code == 400
                error.read()
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


def test_entries_tolerate_disappeared_files(tmp_path, monkeypatch):
    store = KnowledgeStore(tmp_path)
    first = store.add(
        {
            "game": "代号Atom",
            "title": "A",
            "text": "保留",
            "sourceKind": "user",
            "sourceLabel": "笔记",
        }
    )
    gone = store.root / ("b" * 64 + ".json")
    gone.write_text(json.dumps({**first, "entryId": "b" * 64, "title": "将消失"}), encoding="utf-8")
    real_stat = Path.stat

    def flaky_stat(self, *args, **kwargs):
        if self == gone:
            raise FileNotFoundError(str(self))
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)
    assert [e["entryId"] for e in store.entries()] == [first["entryId"]]


def test_store_uses_bounded_read_and_exclusive_create(tmp_path, monkeypatch):
    import gamingcreator.infrastructure.knowledge_store as module

    store = KnowledgeStore(tmp_path)
    calls = {"read": 0, "write": 0}
    real_read = module.read_bounded
    real_write = module.write_exclusive_text

    def counting_read(path, limit=module.MAX_ENTRY_BYTES):
        calls["read"] += 1
        return real_read(path, limit)

    def counting_write(path, text, *, encoding="utf-8"):
        calls["write"] += 1
        return real_write(path, text, encoding=encoding)

    monkeypatch.setattr(module, "read_bounded", counting_read)
    monkeypatch.setattr(module, "write_exclusive_text", counting_write)
    store.add(
        {
            "game": "代号Atom",
            "title": "B",
            "text": "内容",
            "sourceKind": "user",
            "sourceLabel": "笔记",
        }
    )
    assert calls["write"] == 1
    assert store.entries() and calls["read"] >= 1
    target = next(store.root.glob("*.json"))
    with pytest.raises(FileExistsError):
        module.write_exclusive_text(target, "{}" + chr(10))


def test_planning_knowledge_current_literal_bounded_and_stable():
    from gamingcreator.application.knowledge import planning_knowledge

    old = entry("needle", "old needle")
    latest = entry("needle", "x" * 900 + "needle" + "y" * 900, replaces=old["entryId"])
    others = [entry("needle", f"needle {i}") for i in range(4)]
    values = [
        old,
        latest,
        *others,
        entry("needle", "needle", game="foreign"),
        entry("unrelated", "irrelevant"),
    ]
    picked = planning_knowledge(values, "代号Atom", ("needle",), "")
    assert picked == planning_knowledge(list(reversed(values)), "代号Atom", ("needle",), "")
    assert len(picked) == 3
    long_fragment = planning_knowledge([latest], "代号Atom", ("needle",), "")[0]["text"]
    assert len(long_fragment) == 400 and "needle" in long_fragment
    assert long_fragment in latest["text"]
    originals = {e["entryId"]: e for e in values}
    assert old["entryId"] not in [e["entryId"] for e in picked]
    for e in picked:
        assert len(e["text"]) <= 400 and e["text"] in originals[e["entryId"]]["text"]
        assert "needle" in e["text"]
    assert planning_knowledge(values, "代号Atom", (), "") == []
    assert planning_knowledge(values, "代号Atom", (), "missing") == []


def test_planning_knowledge_maps_casefold_index_to_original():
    from gamingcreator.application.knowledge import planning_knowledge

    # ß casefolds to "ss" (length change); slice must stay on original text.
    body = ("ß" * 200) + "needle" + ("ß" * 200)
    value = entry("needle", body)
    frag = planning_knowledge([value], "代号Atom", ("needle",), "")[0]["text"]
    assert frag and "needle" in frag and frag in body
    assert len(frag) <= 400
