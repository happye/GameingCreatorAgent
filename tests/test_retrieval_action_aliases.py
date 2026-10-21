"""Known gameplay aliases retrieve Chinese descriptions without inventing actions."""

import hashlib

import pytest
from test_retrieval_negation import EqualSimilarity, search, timeline
from gamingcreator.application.retrieval import search_timeline
import asyncio


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    "query,positive,denial",
    [
        ("Find jumping clips", "角色跳跃并落地。", "角色没有跳跃。"),
        ("JUMP", "角色跳跃并落地。", "未见跳跃。"),
        ("The player jumped", "角色跳跃并落地。", "没有跳跃。"),
        ("寻找jumping片段", "角色跳跃并落地。", "未观察到跳跃。"),
        ("jumping", "角色跳跃并落地。", "未见jumping。"),
        ("ＪＵＭＰＩＮＧ", "角色跳跃并落地。", "没有跳跃。"),
        ("Find shooting clips", "角色射击目标。", "角色没有射击。"),
        ("shoots", "角色射击目标。", "没有射击。"),
        ("move", "角色向左移动。", "角色没有移动。"),
        ("moving", "角色向左移动。", "未见移动。"),
        ("movement", "角色向左移动。", "没有移动。"),
        ("interaction", "角色与按钮交互。", "没有交互。"),
        ("interacting", "角色与按钮交互。", "未见交互。"),
        ("attacked", "角色攻击目标。", "没有攻击。"),
        ("fight", "角色与敌人战斗。", "没有战斗。"),
    ],
)
def test_positive_action_alias_keeps_chinese_evidence_and_excludes_denials(
    mode, query, positive, denial
):
    data = timeline(positive, denial)
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    candidate = result.candidates[0]
    assert candidate.observable_facts == (positive,)
    assert candidate.evidence_ids == ("run:image:0",)
    assert candidate.source_range == data.events[0].source_range
    assert data.events[1].observable_facts == (denial,)
    assert result.query == query
    assert result.retrieval_version == "bm25-e5-rrf-v7"
    assert result.min_similarity == 0.80 and result.min_semantic_margin == 0.02
    if mode == "hybrid":
        assert {item.text_hash for item in result.event_embeddings} == {
            hashlib.sha256(f"passage: {fact}".encode()).hexdigest() for fact in (positive, denial)
        }


@pytest.mark.parametrize(
    "query",
    [
        "jumpsuit",
        "shootout",
        "movie",
        "removing",
        "interactional",
        "jumping2",
        "a shot of the arena",
        "jump_jumping",
    ],
)
def test_non_action_words_do_not_acquire_chinese_action_matches(query):
    data = timeline("角色跳跃。", "角色射击。", "角色移动。", "角色交互。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,expected",
    [
        ("without jumping", []),
        ("no shooting", []),
        ("exclude movement", []),
        ("not interacting", []),
        ("doesn’t move", []),
        ("doesn't move", []),
        ("不要jumping", []),
        ("没有shooting", ["event-0", "event-1", "event-2", "event-3"]),
    ],
)
def test_negative_intent_does_not_gain_new_cross_language_absence_semantics(query, expected):
    data = timeline("没有跳跃。", "没有射击。", "没有移动。", "没有交互。")
    assert [
        candidate.event_id for candidate in search(data, query, "lexical").candidates
    ] == expected


def test_missing_shooting_description_is_not_replaced_with_explosions_or_held_guns():
    data = timeline("角色手里拿着枪。", "背景出现爆炸特效。", "角色挥动指挥棒。")
    assert search(data, "shooting", "lexical").candidates == ()


def test_action_alias_does_not_assert_all_conditions_of_a_long_query():
    data = timeline("角色跳跃并落地。")
    result = search(data, "a red armored demon jumping with a staff", "lexical")
    assert len(result.candidates) == 1
    assert result.candidates[0].observable_facts == ("角色跳跃并落地。",)
    assert "ranking signal, not probability" in result.candidates[0].why


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    "query,positive,denial",
    [
        ("起跳", "角色跳跃并落地。", "没有跳跃。"),
        ("跳起", "角色跳跃并落地。", "未见起跳。"),
        ("跳跃", "角色起跳并落地。", "没有跳起。"),
        ("jumping", "角色跳起并落地。", "没有起跳。"),
        ("jump", "角色起跳并落地。", "未见跳起。"),
        ("开枪", "角色射击目标。", "没有射击。"),
        ("射击", "角色开枪命中目标。", "没有开枪。"),
        ("shooting", "角色开枪命中目标。", "未见开枪。"),
        ("打斗", "角色与敌人战斗。", "没有战斗。"),
        ("战斗", "角色与敌人打斗。", "没有打斗。"),
        ("fighting", "角色与敌人打斗。", "未见战斗。"),
        ("互动", "角色与按钮交互。", "没有交互。"),
        ("交互", "角色与按钮互动。", "没有互动。"),
        ("interacting", "角色与按钮互动。", "未见互动。"),
    ],
)
def test_known_chinese_action_aliases_preserve_evidence_and_denial_guard(
    mode, query, positive, denial
):
    data = timeline(positive, denial)
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    candidate = result.candidates[0]
    assert candidate.observable_facts == (positive,)
    assert candidate.evidence_ids == data.events[0].evidence_ids
    assert candidate.source_range == data.events[0].source_range
    assert result.query == query
    assert result.min_similarity == 0.80 and result.min_semantic_margin == 0.02
    assert data.events[1].observable_facts == (denial,)
    if mode == "hybrid":
        assert {item.text_hash for item in result.event_embeddings} == {
            hashlib.sha256(f"passage: {fact}".encode()).hexdigest() for fact in (positive, denial)
        }


@pytest.mark.parametrize("query", ["跳跃", "起跳", "跳起", "jumping", "jumped", "jump", "JUMP"])
def test_jump_game_titles_do_not_become_translated_action_evidence(query):
    """TD004: frozen JUMP title brands are not gameplay jump evidence."""
    data = timeline(
        "画面显示“JUMP明星大乱斗”标题。",
        "画面显示“JUMP ASSEMBLE”游戏标志。",
        "少年JUMP正版授权出现在角落。",
        "角色跳跃并落地。",
    )
    result = search(data, query, "lexical")
    assert [item.event_id for item in result.candidates] == ["event-3"]


@pytest.mark.parametrize(
    "query",
    ["没有起跳", "不要跳起", "没有开枪", "不要打斗", "未见互动", "without jumping"],
)
def test_negative_intent_does_not_translate_chinese_aliases(query):
    data = timeline("角色跳跃。", "角色射击。", "角色战斗。", "角色交互。")
    assert search(data, query, "lexical").candidates == ()



@pytest.mark.parametrize("query", ["jump", "JUMP", "jumping"])
def test_jump_title_brands_excluded_in_hybrid_against_adversarial_embeddings(query):
    """TD004: semantic channel must not revive JUMP title cards for jump queries."""
    data = timeline(
        "画面显示“JUMP明星大乱斗”标题。",
        "画面显示“JUMP ASSEMBLE”游戏标志。",
        "少年JUMP正版授权出现在角落。",
        "角色跳跃并落地。",
    )
    result = asyncio.run(
        search_timeline(
            data,
            query,
            mode="hybrid",
            embedding_provider=EqualSimilarity(),
            top_k=10,
        )
    )
    assert [item.event_id for item in result.candidates] == ["event-3"]


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["fight", "combat", "fighting", "战斗", "打斗"])
def test_fight_tag_only_mechanic_noise_excluded_keeps_fact_evidence(mode, query):
    """Fight/combat queries must not rank damage-floater UI solely via bare 战斗 tags."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "红色爆炸特效持续，出现数字820",
        "画面切换为战斗界面，多名角色在场景中交战。",
        "角色跳跃并落地。",
    )
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("战斗", "伤害"))
    data = StoredTimeline(
        base.run,
        base.checkpoints,
        base.evidence,
        base.transcripts,
        tuple(events),
        base.invocations,
    )
    result = asyncio.run(
        search_timeline(data, query, mode=mode, embedding_provider=EqualSimilarity(), top_k=10)
    )
    hit_ids = [item.event_id for item in result.candidates]
    assert "event-0" not in hit_ids, hit_ids
    assert "event-1" in hit_ids, hit_ids


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_attack_tag_only_recall_still_kept(mode):
    """TD010: attack tag-only remains reachable; fight tag-noise filter must not broaden."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "画面中央偏下出现蓝色光效和伤害数字",
        "角色向左移动。",
    )
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("攻击", "伤害"))
    data = StoredTimeline(
        base.run,
        base.checkpoints,
        base.evidence,
        base.transcripts,
        tuple(events),
        base.invocations,
    )
    result = asyncio.run(
        search_timeline(data, "攻击", mode=mode, embedding_provider=EqualSimilarity(), top_k=10)
    )
    assert any(item.event_id == "event-0" for item in result.candidates)
