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


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["move", "moving", "movement", "移动"])
def test_move_tag_only_mechanic_noise_excluded_keeps_fact_evidence(mode, query):
    """Move queries must not rank clips whose only 移动 evidence is a mechanicTag."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "画面中央出现绿色光效和伤害数字",
        "角色向左移动并穿过桥面。",
        "角色跳跃并落地。",
    )
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("角色移动", "伤害"))
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
@pytest.mark.parametrize("query", ["interact", "interaction", "交互", "互动"])
def test_interact_tag_only_mechanic_noise_excluded_keeps_fact_evidence(mode, query):
    """Interact queries must not rank clips whose only 交互 evidence is a mechanicTag."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "画面右下角弹出商店图标",
        "角色与按钮交互并打开菜单。",
        "角色向左移动。",
    )
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("交互", "UI"))
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


def test_candidate_sources_are_score_free_time_ordered_and_align_with_search():
    """Inventory identities match search hits; no ranking fields; facts exclude tags."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import candidate_sources, search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "角色向左移动。",
        "画面显示伤害数字",
        "角色与按钮交互。",
    )
    events = list(base.events)
    events[1] = replace(events[1], mechanic_tags=("战斗", "伤害"))
    data = StoredTimeline(
        base.run,
        base.checkpoints,
        base.evidence,
        base.transcripts,
        tuple(events),
        base.invocations,
    )
    sources = candidate_sources(data)
    assert [s.event_id for s in sources] == ["event-0", "event-1", "event-2"]
    assert [s.source_range.start_us for s in sources] == sorted(s.source_range.start_us for s in sources)
    assert not hasattr(sources[0], "score")
    assert "战斗" not in "\n".join(sources[1].observable_facts)
    result = asyncio.run(
        search_timeline(data, "移动", mode="lexical", embedding_provider=EqualSimilarity(), top_k=5)
    )
    by_id = {s.candidate_id: s for s in sources}
    assert result.candidates
    for hit in result.candidates:
        assert hit.candidate_id in by_id
        assert by_id[hit.candidate_id].event_id == hit.event_id


def test_candidate_sources_refuse_coverage_gap_run():
    """coverage-gap timelines cannot project a candidate inventory."""
    from dataclasses import replace

    from gamingcreator.application.retrieval import candidate_sources
    from gamingcreator.application.storage import RunStatus
    from gamingcreator.domain.errors import AppError
    from test_retrieval_negation import timeline as _base_timeline

    data = _base_timeline("角色跳跃。")
    failed = replace(data.run, status=RunStatus.FAILED, error_code="analysis.coverage_gap")
    from gamingcreator.application.storage import StoredTimeline

    gap = StoredTimeline(
        failed,
        data.checkpoints,
        data.evidence,
        data.transcripts,
        data.events,
        data.invocations,
    )
    with pytest.raises(AppError) as refused:
        candidate_sources(gap)
    assert refused.value.code == "retrieval.coverage_gap"


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_lexical_evidence_marks_attack_tag_only_as_mechanic_tags(mode):
    """TD010 recall stays; why/field advertise mechanic_tags evidence channel."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "画面中央偏下出现蓝色光效和伤害数字",
        "角色攻击目标并造成伤害。",
    )
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("攻击", "伤害"))
    events[1] = replace(events[1], mechanic_tags=("攻击",))
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
    by_id = {item.event_id: item for item in result.candidates}
    assert "event-0" in by_id
    assert by_id["event-0"].lexical_evidence == "mechanic_tags"
    assert "lexicalEvidence=mechanic_tags" in by_id["event-0"].why
    assert "ranking signal, not probability" in by_id["event-0"].why
    assert "event-1" in by_id
    assert by_id["event-1"].lexical_evidence in {"positive_text", "mixed"}
    assert "lexicalEvidence=" in by_id["event-1"].why


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_lexical_evidence_marks_fight_fact_hits_as_positive_text(mode):
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "红色爆炸特效持续，出现数字820",
        "画面切换为战斗界面，多名角色在场景中交战。",
    )
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("战斗", "伤害"))
    events[1] = replace(events[1], mechanic_tags=("战斗",))
    data = StoredTimeline(
        base.run,
        base.checkpoints,
        base.evidence,
        base.transcripts,
        tuple(events),
        base.invocations,
    )
    result = asyncio.run(
        search_timeline(data, "战斗", mode=mode, embedding_provider=EqualSimilarity(), top_k=10)
    )
    hit_ids = [item.event_id for item in result.candidates]
    assert "event-0" not in hit_ids
    assert "event-1" in hit_ids
    hit = next(item for item in result.candidates if item.event_id == "event-1")
    assert hit.lexical_evidence == "mixed"
    assert "lexicalEvidence=mixed" in hit.why


def test_non_action_query_leaves_lexical_evidence_none():
    from test_retrieval_negation import search, timeline

    result = search(timeline("草地上有一座塔。"), "草地塔", "lexical")
    assert result.candidates
    assert result.candidates[0].lexical_evidence is None
    assert "lexicalEvidence=" not in result.candidates[0].why
    assert "ranking signal, not probability" in result.candidates[0].why


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_query_abstains_without_hits(query):
    from test_retrieval_negation import search, timeline

    result = search(timeline("角色跳跃。"), query, "lexical")
    assert result.candidates == ()
    assert result.abstention_reason == "empty_query"


def test_action_query_with_only_title_brand_noise_abstains():
    """Jump titles alone are not gameplay evidence; empty result must explain why."""
    from test_retrieval_negation import search, timeline

    result = search(
        timeline(
            "画面显示“JUMP明星大乱斗”标题。",
            "画面显示“JUMP ASSEMBLE”游戏标志。",
            "少年JUMP正版授权出现在角落。",
        ),
        "jump",
        "lexical",
    )
    assert result.candidates == ()
    assert result.abstention_reason == "no_positive_action_evidence"


def test_action_query_with_fact_hit_does_not_abstain():
    from test_retrieval_negation import search, timeline

    result = search(
        timeline(
            "画面显示“JUMP明星大乱斗”标题。",
            "角色跳跃并落地。",
        ),
        "jump",
        "lexical",
    )
    assert [item.event_id for item in result.candidates] == ["event-1"]
    assert result.abstention_reason is None


def test_negative_intent_empty_does_not_claim_missing_action_evidence():
    from test_retrieval_negation import search, timeline

    result = search(timeline("角色跳跃。"), "without jumping", "lexical")
    assert result.candidates == ()
    assert result.abstention_reason is None


def test_non_action_empty_corpus_does_not_set_action_abstention():
    from test_retrieval_negation import search, timeline

    result = search(timeline("草地上有一座塔。"), "飞机跑道", "lexical")
    assert result.candidates == ()
    assert result.abstention_reason is None


def test_assert_search_result_contract_accepts_live_hits_and_known_abstentions():
    from gamingcreator.application.retrieval import assert_search_result_contract
    from test_retrieval_negation import search, timeline

    hit = search(timeline("角色跳跃并落地。"), "jump", "lexical")
    assert hit.abstention_reason is None
    assert hit.score_is_probability is False
    assert_search_result_contract(hit)
    assert all(item.score_kind == "bm25" for item in hit.candidates)

    empty = search(timeline("角色跳跃。"), "", "lexical")
    assert empty.abstention_reason == "empty_query"
    assert empty.score_is_probability is False
    assert_search_result_contract(empty)

    title_only = search(
        timeline("画面显示“JUMP明星大乱斗”标题。"),
        "jump",
        "lexical",
    )
    assert title_only.abstention_reason == "no_positive_action_evidence"
    assert_search_result_contract(title_only)


def test_assert_search_result_contract_rejects_probability_flag_and_unknown_kind():
    from dataclasses import replace

    import pytest

    from gamingcreator.application.retrieval import assert_search_result_contract
    from gamingcreator.domain.errors import AppError
    from test_retrieval_negation import search, timeline

    hit = search(timeline("角色跳跃并落地。"), "jump", "lexical")
    with pytest.raises(AppError) as flagged:
        assert_search_result_contract(replace(hit, score_is_probability=True))
    assert flagged.value.code == "retrieval.contract"

    bad_kind = replace(
        hit,
        candidates=(replace(hit.candidates[0], score_kind="probability"),),
    )
    with pytest.raises(AppError) as kinded:
        assert_search_result_contract(bad_kind)
    assert kinded.value.code == "retrieval.contract"

    bad_abs = replace(hit, candidates=(), abstention_reason="cleared_gaps")
    with pytest.raises(AppError) as absed:
        assert_search_result_contract(bad_abs)
    assert absed.value.code == "retrieval.contract"


def test_cli_search_document_projects_score_is_probability_false():
    from gamingcreator.cli.main import _search_document
    from test_retrieval_negation import search, timeline

    result = search(timeline("角色向左移动。"), "移动", "lexical")
    document = _search_document(result, elapsed_ms=1)
    assert document["scoreIsProbability"] is False
    assert document["abstentionReason"] is None
    assert "formalAcceptancePassed" not in document
    assert "qualityGate" not in document
    for row in document["candidates"]:
        assert "ranking signal, not probability" in row["why"]


def test_assert_search_document_contract_accepts_cli_projection_and_rejects_claims():
    from gamingcreator.application.retrieval import assert_search_document_contract
    from gamingcreator.cli.main import _search_document
    from gamingcreator.domain.errors import AppError
    from test_retrieval_negation import search, timeline

    hit = search(timeline("角色向左移动。"), "移动", "lexical")
    document = _search_document(hit, elapsed_ms=3)
    assert document["scoreIsProbability"] is False
    assert document["abstentionReason"] is None
    assert_search_document_contract(document)

    empty = search(timeline("角色跳跃。"), "", "lexical")
    empty_doc = _search_document(empty, elapsed_ms=1)
    assert empty_doc["abstentionReason"] == "empty_query"
    assert empty_doc["candidates"] == []
    assert_search_document_contract(empty_doc)

    forged = dict(document)
    forged["formalAcceptancePassed"] = True
    with pytest.raises(AppError) as claimed:
        assert_search_document_contract(forged)
    assert claimed.value.code == "retrieval.contract"

    gated = dict(document)
    gated["qualityGate"] = "passed"
    with pytest.raises(AppError) as gate:
        assert_search_document_contract(gated)
    assert gate.value.code == "retrieval.contract"


def test_assert_candidate_sources_contract_pins_inventory_without_scores():
    from gamingcreator.application.retrieval import (
        assert_candidate_sources_contract,
        candidate_sources,
    )
    from test_retrieval_negation import timeline

    sources = candidate_sources(timeline("角色跳跃。", "角色向左移动。"))
    assert len(sources) == 2
    assert_candidate_sources_contract(sources)
    assert not hasattr(sources[0], "score")


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    "query,positive,denial",
    [
        ("打架", "角色与敌人打架。", "没有打架。"),
        ("对战", "俯视视角对战场景，多名角色交锋。", "没有对战。"),
        ("团战", "画面中央发生团战，多名角色聚集。", "未见团战。"),
        ("fight", "俯视视角对战场景，多名角色交锋。", "没有对战。"),
        ("战斗", "画面中央发生团战，多名角色聚集。", "没有团战。"),
    ],
)
def test_fight_duel_brawl_aliases_keep_chinese_evidence(mode, query, positive, denial):
    """打架／对战／团战 are fight synonyms; cross-term positive evidence still retrieves."""
    data = timeline(positive, denial)
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["对战", "团战", "打架", "战斗", "fight", "combat"])
def test_fight_duel_brawl_tag_only_mechanic_noise_excluded(mode, query):
    """Bare 对战／团战 mechanicTags without fight language in facts are chrome noise."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "俯视视角的绿色场地，中央有角色释放蓝色光效技能。",
        "俯视视角对战场景，多名角色在中央交锋。",
        "角色跳跃并落地。",
    )
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("对战", "技能释放"))
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
    if query in {"对战", "团战", "打架", "战斗", "fight", "combat"}:
        assert "event-1" in hit_ids, hit_ids


def test_duel_query_with_only_tag_noise_abstains():
    """对战 query over tag-only chrome yields no_positive_action_evidence."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline("俯视视角的绿色场地，中央有角色释放蓝色光效技能。")
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("对战", "技能按钮"))
    data = StoredTimeline(
        base.run,
        base.checkpoints,
        base.evidence,
        base.transcripts,
        tuple(events),
        base.invocations,
    )
    result = asyncio.run(
        search_timeline(data, "对战", mode="lexical", embedding_provider=EqualSimilarity(), top_k=10)
    )
    assert result.candidates == ()
    assert result.abstention_reason == "no_positive_action_evidence"


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    "query,positive,denial",
    [
        ("fighter", "角色与敌人战斗。", "没有战斗。"),
        ("fighters", "俯视视角对战场景，多名角色交锋。", "没有对战。"),
        ("duel", "俯视视角对战场景，多名角色交锋。", "没有对战。"),
        ("brawl", "角色与敌人打架。", "没有打架。"),
        ("dueling", "画面中央发生团战，多名角色聚集。", "没有团战。"),
        ("brawling", "角色与敌人打架。", "未见打架。"),
    ],
)
def test_fighter_duel_brawl_english_aliases_keep_chinese_evidence(mode, query, positive, denial):
    """fighter／duel／brawl are fight actions; Chinese body evidence still retrieves."""
    data = timeline(positive, denial)
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["fighter", "fighters", "duel", "brawl", "dueling", "brawling"])
def test_fighter_duel_brawl_tag_only_mechanic_noise_excluded(mode, query):
    """English fight synonyms must apply the same tag-only chrome filter as fight."""
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


@pytest.mark.parametrize(
    "query",
    ["firefighter", "duelist", "brawlerx", "fighters2", "dueling2"],
)
def test_fighter_duel_brawl_non_action_words_do_not_match(query):
    data = timeline("角色与敌人战斗。", "俯视视角对战场景。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["attacker", "attackers"])
def test_attacker_aliases_keep_attack_tag_only_td010(mode, query):
    """TD010: attacker／attackers must stay action-recognized and keep tag-only attack recall."""
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
        search_timeline(data, query, mode=mode, embedding_provider=EqualSimilarity(), top_k=10)
    )
    hits = [item for item in result.candidates if item.event_id == "event-0"]
    assert hits, result.candidates
    assert hits[0].lexical_evidence == "mechanic_tags"
    assert "lexicalEvidence=mechanic_tags" in hits[0].why


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    "query,positive,denial",
    [
        ("attacker", "角色攻击目标。", "没有攻击。"),
        ("attackers", "角色攻击目标。", "未见攻击。"),
    ],
)
def test_attacker_aliases_keep_chinese_body_evidence(mode, query, positive, denial):
    data = timeline(positive, denial)
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].lexical_evidence == "positive_text"


@pytest.mark.parametrize("query", ["firefighter", "attackers2", "attackerx", "reattacker"])
def test_attacker_non_action_words_do_not_match(query):
    data = timeline("角色攻击目标。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    "query,positive,denial",
    [
        ("walk", "角色向左移动。", "没有移动。"),
        ("walking", "角色向左移动。", "未见移动。"),
        ("walked", "角色向左移动。", "没有移动。"),
        ("行走", "角色向左移动。", "没有移动。"),
        ("走动", "角色向左移动。", "未见移动。"),
        ("位移", "角色向左移动。", "没有移动。"),
        ("move", "角色行走穿过平台。", "没有行走。"),
    ],
)
def test_walk_gait_aliases_keep_chinese_move_evidence(mode, query, positive, denial):
    """walk／行走／走动／位移 are move synonyms; body-text evidence still retrieves."""
    data = timeline(positive, denial)
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["walk", "walking", "walked", "行走", "走动", "位移"])
def test_walk_gait_tag_only_mechanic_noise_excluded(mode, query):
    """Walk／gait aliases must apply the same move tag-only chrome filter."""
    import asyncio
    from dataclasses import replace

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline
    from test_retrieval_negation import EqualSimilarity, timeline as _base_timeline

    base = _base_timeline(
        "俯视视角的绿色场地，中央有角色释放蓝色光效技能。",
        "场地中央有角色移动，出现绿色特效。",
        "角色跳跃并落地。",
    )
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("角色移动", "技能按钮"))
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


@pytest.mark.parametrize(
    "query",
    ["sidewalk", "walkway", "catwalk", "walking2", "walk_walk"],
)
def test_walk_non_action_words_do_not_match(query):
    data = timeline("角色向左移动。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("heal", "画面中央出现绿色治疗数字+195。"),
        ("healing", "画面中央出现绿色治疗数字+195。"),
        ("healed", "角色受到治疗并恢复生命。"),
        ("damage", "画面中央出现伤害数字2200。"),
        ("damaging", "画面中央出现伤害数字2200。"),
        ("damages", "角色受到伤害并显示数字。"),
    ],
)
def test_heal_damage_cross_lingual_keeps_chinese_evidence(query, positive):
    """English heal／damage expand to 治疗／伤害 against Chinese body text (lexical)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    ["healthbar", "healerx", "damages2", "damagingly", "selfheal"],
)
def test_heal_damage_non_action_words_do_not_cross_lingual_match(query):
    data = timeline("画面中央出现绿色治疗数字+195。", "画面中央出现伤害数字2200。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_interacted_alias_keeps_chinese_evidence(mode):
    data = timeline("角色与按钮交互。", "没有交互。")
    result = search(data, "interacted", mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]


def test_interacted_alias_abstains_when_no_positive_lexical_evidence():
    empty = search(timeline("角色向左移动。"), "interacted", "lexical")
    assert empty.candidates == ()
    assert empty.abstention_reason == "no_positive_action_evidence"
