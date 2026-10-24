"""Known gameplay aliases retrieve Chinese descriptions without inventing actions."""

import asyncio
import hashlib

import pytest
from test_retrieval_negation import EqualSimilarity, search, timeline

from gamingcreator.application.retrieval import search_timeline


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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import candidate_sources, search_timeline
    from gamingcreator.application.storage import StoredTimeline

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
    assert [s.source_range.start_us for s in sources] == sorted(
        s.source_range.start_us for s in sources
    )
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

    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import candidate_sources
    from gamingcreator.application.storage import RunStatus
    from gamingcreator.domain.errors import AppError

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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
    from test_retrieval_negation import search, timeline

    from gamingcreator.application.retrieval import assert_search_result_contract

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
    from test_retrieval_negation import search, timeline

    from gamingcreator.application.retrieval import assert_search_result_contract
    from gamingcreator.domain.errors import AppError

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


def test_assert_search_result_contract_rejects_mode_media_event_and_duplicate_candidate():
    """Deeper in-memory gates mirroring search-document: mode, media, owned eventId, unique ids."""
    from dataclasses import replace

    import pytest
    from test_retrieval_negation import search, timeline

    from gamingcreator.application.retrieval import assert_search_result_contract
    from gamingcreator.domain.errors import AppError

    hit = search(timeline("角色向左移动。"), "移动", "lexical")
    assert hit.candidates
    assert_search_result_contract(hit)

    bad_mode = replace(hit, mode="not-a-mode")  # type: ignore[arg-type]
    with pytest.raises(AppError) as mode_err:
        assert_search_result_contract(bad_mode)
    assert mode_err.value.code == "retrieval.contract"

    bad_media = replace(
        hit,
        candidates=(replace(hit.candidates[0], media_id=""),),
    )
    with pytest.raises(AppError) as media_err:
        assert_search_result_contract(bad_media)
    assert media_err.value.code == "retrieval.contract"

    foreign = replace(
        hit,
        candidates=(
            replace(
                hit.candidates[0], event_id=f"foreign-run:{hit.candidates[0].media_id}:event:x"
            ),
        ),
    )
    with pytest.raises(AppError) as event_err:
        assert_search_result_contract(foreign)
    assert event_err.value.code == "retrieval.contract"

    none_event = replace(
        hit,
        candidates=(replace(hit.candidates[0], event_id=None),),
    )
    assert_search_result_contract(none_event)

    empty_event = replace(
        hit,
        candidates=(replace(hit.candidates[0], event_id=""),),
    )
    with pytest.raises(AppError) as empty_err:
        assert_search_result_contract(empty_event)
    assert empty_err.value.code == "retrieval.contract"

    if len(hit.candidates) >= 1:
        dup = replace(
            hit,
            candidates=(
                hit.candidates[0],
                replace(hit.candidates[0], score=hit.candidates[0].score * 0.5),
            ),
        )
        with pytest.raises(AppError) as dup_err:
            assert_search_result_contract(dup)
        assert dup_err.value.code == "retrieval.contract"


def test_assert_candidate_sources_contract_rejects_blank_media_and_empty_span():
    from dataclasses import replace

    import pytest
    from test_retrieval_negation import timeline

    from gamingcreator.application.retrieval import (
        assert_candidate_sources_contract,
        candidate_sources,
    )
    from gamingcreator.domain.errors import AppError

    sources = candidate_sources(timeline("角色跳跃。", "角色向左移动。"))
    assert_candidate_sources_contract(sources)

    bad_media = (replace(sources[0], media_id=""),) + sources[1:]
    with pytest.raises(AppError) as media_err:
        assert_candidate_sources_contract(bad_media)
    assert media_err.value.code == "retrieval.contract"

    # SourceRange validates nonempty on construction — forge via object.__new__ bypass is heavy;
    # instead duplicate id still refused (existing), and empty event string refused.
    empty_event = (replace(sources[0], event_id=""),) + sources[1:]
    with pytest.raises(AppError) as event_err:
        assert_candidate_sources_contract(empty_event)
    assert event_err.value.code == "retrieval.contract"


def test_cli_search_document_projects_score_is_probability_false():
    from test_retrieval_negation import search, timeline

    from gamingcreator.cli.main import _search_document

    result = search(timeline("角色向左移动。"), "移动", "lexical")
    document = _search_document(result, elapsed_ms=1)
    assert document["scoreIsProbability"] is False
    assert document["abstentionReason"] is None
    assert "formalAcceptancePassed" not in document
    assert "qualityGate" not in document
    for row in document["candidates"]:
        assert "ranking signal, not probability" in row["why"]


def test_assert_search_document_contract_accepts_cli_projection_and_rejects_claims():
    from test_retrieval_negation import search, timeline

    from gamingcreator.application.retrieval import assert_search_document_contract
    from gamingcreator.cli.main import _search_document
    from gamingcreator.domain.errors import AppError

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
    from test_retrieval_negation import timeline

    from gamingcreator.application.retrieval import (
        assert_candidate_sources_contract,
        candidate_sources,
    )

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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
        search_timeline(
            data, "对战", mode="lexical", embedding_provider=EqualSimilarity(), top_k=10
        )
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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    "query,positive",
    [
        ("cast", "角色释放蓝色环形技能。"),
        ("casting", "角色释放蓝色环形技能。"),
        ("casts", "角色施放紫色光束。"),
        ("skill", "角色释放蓝色光效技能。"),
        ("skills", "右侧技能图标可见，角色释放技能。"),
        ("技能", "角色释放蓝色环形技能。"),
        ("释放", "角色释放蓝色环形技能。"),
        ("施法", "角色施法并出现光效。"),
    ],
)
def test_cast_skill_aliases_keep_chinese_evidence(mode, query, positive):
    # Exclusive single-term denials so 释放／技能 do not leak as affirmative clauses.
    data = timeline(positive, "没有释放。", "没有技能。", "未见施法。", "没有施放。")
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    ["skillful", "forecast", "broadcast", "castable", "skillshot", "overcast"],
)
def test_cast_skill_non_action_words_do_not_match(query):
    data = timeline("角色释放蓝色环形技能。", "角色施法并出现光效。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["cast", "skill", "casting", "skills", "释放", "技能"])
def test_cast_skill_tag_only_mechanic_noise_excluded(mode, query):
    """Bare 技能释放／技能特效 mechanicTags without cast language in facts are chrome."""
    import asyncio
    from dataclasses import replace

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

    base = _base_timeline("角色向左移动。", "地面出现橙色区域。")
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("技能释放", "伤害数字"))
    events[1] = replace(events[1], mechanic_tags=("技能特效",))
    data = StoredTimeline(
        base.run, base.checkpoints, base.evidence, base.transcripts, tuple(events), base.invocations
    )
    empty = asyncio.run(
        search_timeline(data, query, mode=mode, embedding_provider=EqualSimilarity(), top_k=10)
    )
    assert empty.candidates == ()
    assert empty.abstention_reason == "no_positive_action_evidence"


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_cast_skill_tag_only_excluded_keeps_fact_evidence(mode):
    import asyncio
    from dataclasses import replace

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

    base = _base_timeline("角色释放蓝色环形技能。", "角色向左移动。")
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("技能释放", "伤害数字"))
    events[1] = replace(events[1], mechanic_tags=("技能特效",))
    data = StoredTimeline(
        base.run, base.checkpoints, base.evidence, base.transcripts, tuple(events), base.invocations
    )
    result = asyncio.run(
        search_timeline(data, "skill", mode=mode, embedding_provider=EqualSimilarity(), top_k=10)
    )
    assert [c.event_id for c in result.candidates] == ["event-0"]
    assert result.candidates[0].lexical_evidence in {"positive_text", "mixed"}


@pytest.mark.parametrize(
    "query,positive",
    [
        ("explode", "画面中央出现红色爆炸特效。"),
        ("exploding", "画面中央出现红色爆炸特效。"),
        ("explosion", "金色爆炸特效持续可见。"),
        ("exploded", "场景中出现爆炸。"),
    ],
)
def test_explode_cross_lingual_keeps_chinese_evidence(query, positive):
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize("query", ["unexploded", "exploderx", "explosion2"])
def test_explode_non_action_words_do_not_cross_lingual_match(query):
    data = timeline("画面中央出现红色爆炸特效。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("countdown", "顶部显示倒计时“02:33”。"),
        ("countdowns", "顶部倒计时显示“02:32”。"),
        ("timer", "顶部显示比分与计时。"),
        ("timers", "顶部计时器显示01:43。"),
        ("score", "顶部有双方角色头像与比分条。"),
        ("scores", "顶部比分条仍可见。"),
        ("scoreboard", "顶部显示比分与计时。"),
        ("scoreboards", "顶部有双方角色头像与比分条。"),
        ("beam", "中央有大量蓝色垂直光束特效。"),
        ("beams", "画面出现紫色光束与金色光束。"),
    ],
)
def test_countdown_timer_score_beam_cross_lingual_keeps_chinese_evidence(query, positive):
    """English UI observation words expand to 倒计时／计时／比分／光束 (lexical)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    ["countdownx", "scoreboard2", "beamingly", "timerswitch", "highscorex"],
)
def test_countdown_timer_score_beam_non_words_do_not_cross_lingual_match(query):
    data = timeline("顶部显示倒计时“02:33”。", "顶部比分条仍可见。", "中央有蓝色垂直光束。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["交战", "fight", "combat"])
def test_jiaozhan_fight_alias_keeps_chinese_evidence(mode, query):
    data = timeline("多名角色在场景中交战。", "没有战斗。", "未见打斗。")
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == ("多名角色在场景中交战。",)


def test_jiaozhan_tag_only_mechanic_noise_excluded_lexical():
    """Bare 交战 mechanicTag without fight language in facts is chrome noise (lexical)."""
    import asyncio
    from dataclasses import replace

    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

    base = _base_timeline("角色向左移动。", "地面出现橙色区域。")
    events = list(base.events)
    events[0] = replace(events[0], mechanic_tags=("交战", "伤害数字"))
    data = StoredTimeline(
        base.run, base.checkpoints, base.evidence, base.transcripts, tuple(events), base.invocations
    )
    empty = asyncio.run(search_timeline(data, "交战", mode="lexical", top_k=10))
    assert empty.candidates == ()
    assert empty.abstention_reason == "no_positive_action_evidence"


@pytest.mark.parametrize(
    "query,positive",
    [
        ("avatar", "顶部有双方角色头像与比分条。"),
        ("avatars", "左上角显示角色头像。"),
        ("icon", "下方出现一个圆形图标。"),
        ("icons", "右侧有技能图标。"),
        ("vfx", "场地中央出现蓝色旋风特效。"),
        ("fx", "出现绿色特效和伤害数字。"),
        ("glow", "场地内出现黄色光效。"),
        ("glowing", "中央有角色释放蓝色光效技能。"),
    ],
)
def test_avatar_icon_vfx_glow_cross_lingual_keeps_chinese_evidence(query, positive):
    """English UI portrait／icon／vfx words expand to 头像／图标／特效／光效 (lexical)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)
    assert result.abstention_reason is None


def test_avatar_alone_is_not_empty_query_stopword():
    """Portrait queries must remain searchable; avatar is not filler."""
    data = timeline("顶部有双方角色头像与比分条。")
    result = search(data, "avatar", "lexical")
    assert result.abstention_reason != "empty_query"
    assert [c.event_id for c in result.candidates] == ["event-0"]


@pytest.mark.parametrize(
    "query",
    ["avatarx", "iconic2", "vfxz", "glowworm", "prefix", "postfix"],
)
def test_avatar_icon_vfx_glow_non_words_do_not_cross_lingual_match(query):
    data = timeline(
        "顶部有双方角色头像与比分条。", "右侧有技能图标。", "出现绿色特效。", "黄色光效。"
    )
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("healthbar", "右上角显示红色血条和文字。"),
        ("hp", "右上角显示红色血条。"),
        ("building", "周围有多个角色和建筑。"),
        ("buildings", "场景中可见石质建筑。"),
        ("arena", "俯视视角的方形场地。"),
        ("field", "绿色场地上有角色移动。"),
        ("grass", "周围有绿色草地和石质建筑。"),
        ("cover", "两侧有木制掩体与桶状物体。"),
    ],
)
def test_scene_healthbar_arena_grass_cross_lingual_keeps_chinese_evidence(query, positive):
    """English scene／HUD words expand to 血条／建筑／场地／草地／掩体 (lexical)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    ["healthbarx", "hpx", "building2", "arenax", "grassland", "discover", "covering", "infield"],
)
def test_scene_healthbar_arena_grass_non_words_do_not_cross_lingual_match(query):
    data = timeline(
        "右上角显示红色血条。",
        "周围有多个角色和建筑。",
        "俯视视角的方形场地。",
        "周围有绿色草丛。",
        "两侧有木制掩体。",
    )
    assert search(data, query, "lexical").candidates == ()


def test_avatar_still_searchable_after_scene_alias_sprint():
    """Regression: avatar must remain a searchable portrait term (not a stopword)."""
    from gamingcreator.application.retrieval import _STOP_WORDS

    assert "avatar" not in _STOP_WORDS
    data = timeline("顶部有双方角色头像与比分条。")
    result = search(data, "avatar", "lexical")
    assert result.abstention_reason != "empty_query"
    assert [c.event_id for c in result.candidates] == ["event-0"]


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    "query,positive,denial",
    [
        ("running", "角色向左移动。", "没有移动。"),
        ("runs", "角色向左移动。", "未见移动。"),
        ("ran", "角色向左移动。", "没有移动。"),
        ("runner", "角色向左移动。", "未见移动。"),
        ("runners", "角色向左移动。", "没有移动。"),
        ("奔跑", "角色向城堡方向奔跑。", "没有奔跑。"),
        ("迈步", "粉色头发角色向前迈步。", "未见迈步。"),
        ("move", "角色奔跑穿过平台。", "没有奔跑。"),
    ],
)
def test_run_gait_aliases_keep_chinese_move_evidence(mode, query, positive, denial):
    """running／奔跑／迈步 are move synonyms (demo-phase0 real 奔跑／迈步); bare run avoided."""
    data = timeline(positive, denial)
    result = search(data, query, mode)
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("query", ["running", "runs", "ran", "runner", "奔跑", "迈步"])
def test_run_gait_tag_only_mechanic_noise_excluded(mode, query):
    """Run／gait aliases must apply the same move tag-only chrome filter."""
    import asyncio
    from dataclasses import replace

    from test_retrieval_negation import EqualSimilarity
    from test_retrieval_negation import timeline as _base_timeline

    from gamingcreator.application.retrieval import search_timeline
    from gamingcreator.application.storage import StoredTimeline

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
    ["running2", "ran2", "runnerx", "outrun", "forerunner", "run"],
)
def test_run_gait_non_action_words_do_not_match(query):
    """Bare run and lookalikes must not become move queries (run-id / substring safety)."""
    data = timeline("角色向左移动。")
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("platform", "一个绿色角色从悬浮平台下方出现，最终落在粉色圆形平台上。"),
        ("platforms", "一个绿色角色从悬浮平台下方出现，最终落在粉色圆形平台上。"),
        ("smoke", "角色向城堡方向奔跑，身后有白色烟雾轨迹。"),
        ("smokes", "角色向城堡方向奔跑，身后有白色烟雾轨迹。"),
        ("smoking", "角色向城堡方向奔跑，身后有白色烟雾轨迹。"),
        ("landing", "角色完成一次跳跃，随后落地并向前移动。"),
        ("landed", "角色完成一次跳跃，随后落地并向前移动。"),
        ("landings", "角色完成一次跳跃，随后落地并向前移动。"),
        ("lands", "角色完成一次跳跃，随后落地并向前移动。"),
        ("castle", "角色在绿色阶梯上向城堡方向奔跑。"),
        ("castles", "角色在绿色阶梯上向城堡方向奔跑。"),
    ],
)
def test_scene_platform_smoke_landing_castle_cross_lingual_keeps_chinese_evidence(query, positive):
    """English scene nouns expand to 平台／烟雾／落地／城堡 (demo-phase0 real corpus)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    [
        "platformx",
        "platforms2",
        "smokehouse",
        "smokestack",
        "landing2",
        "landingsx",
        "homeland",
        "inland",
        "land",
        "castled",
        "forecastle",
        "castle2",
    ],
)
def test_scene_platform_smoke_landing_castle_non_words_do_not_cross_lingual_match(query):
    data = timeline(
        "一个绿色角色从悬浮平台下方出现，最终落在粉色圆形平台上。",
        "角色向城堡方向奔跑，身后有白色烟雾轨迹。",
        "角色完成一次跳跃，随后落地并向前移动。",
        "角色在绿色阶梯上向城堡方向奔跑。",
    )
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("bleacher", "背景为蓝紫色未来风格竞技场，有看台、气球和立柱。"),
        ("bleachers", "背景为蓝紫色未来风格竞技场，有看台、气球和立柱。"),
        ("grandstand", "背景为蓝紫色未来风格竞技场，有看台、气球和立柱。"),
        ("grandstands", "背景为蓝紫色未来风格竞技场，有看台、气球和立柱。"),
        ("flash", "角色周围出现紫色环形光效和白色闪光。"),
        ("flashes", "角色周围出现紫色环形光效和白色闪光。"),
        ("flashing", "角色周围出现紫色环形光效和白色闪光。"),
        ("trail", "角色向城堡方向奔跑，身后有白色烟雾轨迹。"),
        ("trails", "角色向城堡方向奔跑，身后有白色烟雾轨迹。"),
        ("trajectory", "角色向城堡方向奔跑，身后有白色烟雾轨迹。"),
        ("trajectories", "角色向城堡方向奔跑，身后有白色烟雾轨迹。"),
    ],
)
def test_scene_bleacher_flash_trail_cross_lingual_keeps_chinese_evidence(query, positive):
    """English scene nouns expand to 看台／闪光／轨迹 (demo-phase0 real corpus)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    [
        "bleacherx",
        "bleachers2",
        "grandstanding",
        "flashback",
        "flashlight",
        "flashy",
        "trailhead",
        "trailing",
        "trail2",
        "stand",
        "stands",
        "standing",
    ],
)
def test_scene_bleacher_flash_trail_non_words_do_not_cross_lingual_match(query):
    data = timeline(
        "背景为蓝紫色未来风格竞技场，有看台、气球和立柱。",
        "角色周围出现紫色环形光效和白色闪光。",
        "角色向城堡方向奔跑，身后有白色烟雾轨迹。",
    )
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("rising", "一个绿色圆润角色从画面下方出现，向上升起。"),
        ("rises", "一个绿色圆润角色从画面下方出现，向上升起。"),
        ("shield", "蓝色角色周围出现半透明球形护罩，护罩随角色移动。"),
        ("shields", "蓝色角色周围出现半透明球形护罩，护罩随角色移动。"),
        ("barrier", "蓝色角色周围出现半透明球形护罩，护罩随角色移动。"),
        ("barriers", "蓝色角色周围出现半透明球形护罩，护罩随角色移动。"),
        ("floating", "一个绿色角色从悬浮平台下方出现，向上移动并穿过平台。"),
        ("hover", "一个绿色角色从悬浮平台下方出现，向上移动并穿过平台。"),
        ("hovering", "一个绿色角色从悬浮平台下方出现，向上移动并穿过平台。"),
        ("stairs", "角色在绿色阶梯上向城堡方向奔跑。"),
        ("stair", "角色在绿色阶梯上向城堡方向奔跑。"),
        ("staircase", "角色在绿色阶梯上向城堡方向奔跑。"),
        ("ladder", "角色在绿色阶梯上向城堡方向奔跑。"),
        ("hug", "绿色头发角色向前倾身并拥抱粉色角色。"),
        ("hugging", "绿色头发角色向前倾身并拥抱粉色角色。"),
        ("embrace", "绿色头发角色向前倾身并拥抱粉色角色。"),
        ("ring", "角色穿过带有粉色圆环的悬浮平台。"),
        ("rings", "角色穿过带有粉色圆环的悬浮平台。"),
        ("note", "绿色头发角色周围有黄色音符。"),
        ("notes", "绿色头发角色周围有黄色音符。"),
    ],
)
def test_scene_rising_shield_float_stair_hug_ring_note_cross_lingual_keeps_chinese_evidence(
    query, positive
):
    """English scene nouns → 升起／护罩／悬浮／阶梯／拥抱／圆环／音符 (demo-phase0)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    [
        "rising2",
        "arise",
        "rose",
        "windshield",
        "shielding",
        "float",
        "floater",
        "upstairs",
        "downstairs",
        "huggable",
        "earring",
        "ringing",
        "notebook",
        "noted",
        "noteworthy",
    ],
)
def test_scene_rising_shield_float_stair_hug_ring_note_non_words_do_not_cross_lingual_match(query):
    data = timeline(
        "一个绿色圆润角色从画面下方出现，向上升起。",
        "蓝色角色周围出现半透明球形护罩，护罩随角色移动。",
        "一个绿色角色从悬浮平台下方出现，向上移动并穿过平台。",
        "角色在绿色阶梯上向城堡方向奔跑。",
        "绿色头发角色向前倾身并拥抱粉色角色。",
        "角色穿过带有粉色圆环的悬浮平台。",
        "绿色头发角色周围有黄色音符。",
    )
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("collect", "绿色头发角色周围有黄色音符可供收集。"),
        ("collecting", "绿色头发角色周围有黄色音符可供收集。"),
        ("collects", "绿色头发角色周围有黄色音符可供收集。"),
        ("collected", "绿色头发角色周围有黄色音符可供收集。"),
        ("mount", "角色骑乘在载具上向前移动。"),
        ("mounts", "角色骑乘在载具上向前移动。"),
        ("mounted", "角色骑乘在载具上向前移动。"),
        ("mounting", "角色骑乘在载具上向前移动。"),
        ("ride", "角色骑乘在载具上向前移动。"),
        ("riding", "角色骑乘在载具上向前移动。"),
        ("rides", "角色骑乘在载具上向前移动。"),
        ("cutscene", "过场画面中出现标题文字与角色展示。"),
        ("cutscenes", "过场画面中出现标题文字与角色展示。"),
        ("cinematic", "过场画面中出现标题文字与角色展示。"),
        ("cinematics", "过场画面中出现标题文字与角色展示。"),
        ("scroll", "镜头随平台滚动，角色保持向前移动。"),
        ("scrolling", "镜头随平台滚动，角色保持向前移动。"),
        ("scrolls", "镜头随平台滚动，角色保持向前移动。"),
        ("scrolled", "镜头随平台滚动，角色保持向前移动。"),
        ("shockwave", "角色举起权杖释放冲击波。"),
        ("shockwaves", "角色举起权杖释放冲击波。"),
    ],
)
def test_scene_collect_mount_cutscene_scroll_shockwave_cross_lingual_keeps_chinese_evidence(
    query, positive
):
    """English collect／mount／cutscene／scroll／shockwave → 收集／骑乘／过场／滚动／冲击波 (demo-phase0)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    [
        "collection",
        "collective",
        "collector",
        "recollect",
        "mountain",
        "mountable",
        "dismount",
        "rider",
        "rideable",
        "override",
        "cutscenesx",
        "precinematic",
        "scrollable",
        "scrollbar",
        "roll",
        "rolling",
        "shock",
        "wave",
        "aftershock",
    ],
)
def test_scene_collect_mount_cutscene_scroll_shockwave_non_words_do_not_cross_lingual_match(
    query,
):
    data = timeline(
        "绿色头发角色周围有黄色音符可供收集。",
        "角色骑乘在载具上向前移动。",
        "过场画面中出现标题文字与角色展示。",
        "镜头随平台滚动，角色保持向前移动。",
        "角色举起权杖释放冲击波。",
    )
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("overhead", "画面切换为俯视视角，显示一块方形场地。"),
        ("overheads", "画面切换为俯视视角，显示一块方形场地。"),
        ("topdown", "画面切换为俯视视角，显示一块方形场地。"),
        ("topdowns", "画面切换为俯视视角，显示一块方形场地。"),
        ("button", "俯视对战场景右侧有技能按钮和方向摇杆。"),
        ("buttons", "俯视对战场景右侧有技能按钮和方向摇杆。"),
        ("map", "俯视视角的方形地图，中央有多个角色单位。"),
        ("maps", "俯视视角的方形地图，中央有多个角色单位。"),
        ("sand", "蓝色角色在沙地上移动，身后留下白色烟雾轨迹。"),
        ("sands", "蓝色角色在沙地上移动，身后留下白色烟雾轨迹。"),
        ("sandy", "蓝色角色在沙地上移动，身后留下白色烟雾轨迹。"),
        ("water", "棕色方格平台漂浮在蓝色水域上方。"),
        ("waters", "棕色方格平台漂浮在蓝色水域上方。"),
        ("glitch", "画面出现条纹状失真与色彩错位。"),
        ("glitches", "画面出现条纹状失真与色彩错位。"),
        ("distortion", "文字被扭曲，场地与角色出现重影。"),
        ("distortions", "文字被扭曲，场地与角色出现重影。"),
        ("pillar", "竞技场入口两侧立着石柱。"),
        ("pillars", "竞技场入口两侧立着石柱。"),
    ],
)
def test_scene_overhead_button_map_sand_water_glitch_cross_lingual_keeps_chinese_evidence(
    query, positive
):
    """English overhead／button／map／sand／water／glitch／distortion／pillar → 俯视／按钮／地图／沙地／水域／失真／扭曲／石柱."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    [
        "overheading",
        "head",
        "top",
        "down",
        "buttoned",
        "buttoning",
        "mapping",
        "mapped",
        "bitmap",
        "roadmap",
        "sandal",
        "sandwich",
        "waterfall",
        "waterproof",
        "glitchy",
        "unglitch",
        "distort",
        "distorted",
        "pillarless",
        "pillow",
    ],
)
def test_scene_overhead_button_map_sand_water_glitch_non_words_do_not_cross_lingual_match(
    query,
):
    data = timeline(
        "画面切换为俯视视角，显示一块方形场地。",
        "俯视对战场景右侧有技能按钮和方向摇杆。",
        "俯视视角的方形地图，中央有多个角色单位。",
        "蓝色角色在沙地上移动，身后留下白色烟雾轨迹。",
        "棕色方格平台漂浮在蓝色水域上方。",
        "画面出现条纹状失真与色彩错位。",
        "文字被扭曲，场地与角色出现重影。",
        "竞技场入口两侧立着石柱。",
    )
    assert search(data, query, "lexical").candidates == ()


@pytest.mark.parametrize(
    "query,positive",
    [
        ("title", "画面显示带有字样的标题画面，背景为像素化场景。"),
        ("titles", "画面显示带有字样的标题画面，背景为像素化场景。"),
        ("transition", "镜头切换时出现转场光效，中央建筑被光束遮挡。"),
        ("transitions", "镜头切换时出现转场光效，中央建筑被光束遮挡。"),
        ("logo", "画面中央显示 NARUTO 标志，场景变为绿色区域。"),
        ("logos", "画面中央显示 NARUTO 标志，场景变为绿色区域。"),
    ],
)
def test_scene_title_transition_logo_cross_lingual_keeps_chinese_evidence(query, positive):
    """English title／transition／logo → 标题／转场／标志 (demo-phase0)."""
    data = timeline(positive, "角色向左移动。")
    result = search(data, query, "lexical")
    assert [candidate.event_id for candidate in result.candidates] == ["event-0"]
    assert result.candidates[0].observable_facts == (positive,)


@pytest.mark.parametrize(
    "query",
    [
        "titled",
        "subtitle",
        "untitled",
        "entitle",
        "titlebrand",
        "transitional",
        "transit",
        "logon",
        "logic",
        "catalogue",
        "analog",
    ],
)
def test_scene_title_transition_logo_non_words_do_not_cross_lingual_match(query):
    data = timeline(
        "画面显示带有字样的标题画面，背景为像素化场景。",
        "镜头切换时出现转场光效，中央建筑被光束遮挡。",
        "画面中央显示 NARUTO 标志，场景变为绿色区域。",
    )
    assert search(data, query, "lexical").candidates == ()
