"""English gameplay actions can retrieve existing Chinese descriptions."""

import hashlib

import pytest
from test_retrieval_negation import search, timeline


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
    assert result.retrieval_version == "bm25-e5-rrf-v6"
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
