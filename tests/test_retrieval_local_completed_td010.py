"""Read-only TD010 / retrieval对照 against local artifact timeline DBs.

Verification is pytest + SqliteTimelineStore(read_only=True). No DeepSeek,
launcher, paid calls, or browser. Missing artifacts => skip, not fail.
Does not claim F006 / human-eval / gap clearance.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from gamingcreator.application.retrieval import (
    _denied_action_documents,
    _documents,
    load_searchable_timeline,
    search_timeline,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))
from test_retrieval_negation import EqualSimilarity

REPO = Path(__file__).resolve().parents[1]
DEMO_PHASE0 = REPO / "artifacts" / "demo-phase0"
INDEPENDENT_FOOTAGE = REPO / "artifacts" / "independent-footage-20261011"

COMPLETED_RUN_DEMO = "f76f5d6495314c04ae04083614d4afd6"
COVERAGE_GAP_RUN = "5c7894aa10e94b8aa82533bd77f9871e"


def _require_sqlite(project: Path) -> Path:
    db = project / "timeline.sqlite3"
    if not db.is_file():
        pytest.skip(f"local artifact DB missing: {db}")
    return db


def _completed_run_ids(db: Path) -> list[str]:
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return [
            row[0]
            for row in con.execute(
                "SELECT run_id FROM analysis_runs WHERE status = 'completed' ORDER BY run_id"
            )
        ]
    finally:
        con.close()


def test_local_completed_demo_phase0_positive_text_excludes_mechanic_tags():
    """Real Completed timeline: positive_text must not reintroduce bare mechanicTags."""
    _require_sqlite(DEMO_PHASE0)
    assert COMPLETED_RUN_DEMO in _completed_run_ids(DEMO_PHASE0 / "timeline.sqlite3")

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = _documents(timeline)
        assert len(docs) >= 50
        tagged = [doc for doc in docs if doc.tags]
        assert tagged, "fixture regression: expected mechanicTags on demo-phase0 Completed run"
        for doc in docs:
            fact_blob = "\n".join(doc.facts)
            for tag in doc.tags:
                if not tag:
                    continue
                # If the tag string is absent from observable facts, it must not enter positive_text
                # (transcripts in this fixture are unused for these tag-only attack rows).
                if tag not in fact_blob:
                    assert tag not in doc.positive_text, (
                        f"tag {tag!r} leaked into positive_text for {doc.event_id}"
                    )
            if not fact_blob.strip() and doc.tags:
                assert doc.positive_text == ""

    asyncio.run(run())


def test_local_completed_demo_phase0_denial_guard_never_leaks_into_lexical_hits():
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await load_searchable_timeline(store, COMPLETED_RUN_DEMO)
        docs = _documents(timeline)
        for query in ("跳跃", "jump", "攻击", "attack", "射击", "shooting"):
            denied = _denied_action_documents(docs, query)
            result = await search_timeline(timeline, query, mode="lexical", top_k=20)
            hit_ids = {
                f"event:{item.event_id}" for item in result.candidates if item.event_id
            }
            assert hit_ids.isdisjoint(denied), (query, sorted(hit_ids & denied))

    asyncio.run(run())


def test_local_completed_demo_phase0_tag_only_attack_still_lexical_reachable():
    """Tags may help lexical recall when facts do not deny; positive_text stays tag-free."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = _documents(timeline)
        by_event = {doc.event_id: doc for doc in docs}
        tag_only_attack = [
            doc
            for doc in docs
            if any("攻击" in tag for tag in doc.tags) and "攻击" not in doc.positive_text
        ]
        assert tag_only_attack, "fixture regression: expected tag-only 攻击 rows"
        result = await search_timeline(timeline, "攻击", mode="lexical", top_k=20)
        hit_events = {item.event_id for item in result.candidates}
        assert any(doc.event_id in hit_events for doc in tag_only_attack)
        for doc in tag_only_attack:
            assert "攻击" not in doc.positive_text
            assert doc.event_id in by_event

    asyncio.run(run())


def test_local_independent_footage_coverage_gap_refuses_searchable_load():
    """Real coverage-gap run must stay unsearchable (retrieval contract, not acceptance)."""
    _require_sqlite(INDEPENDENT_FOOTAGE)

    async def run() -> None:
        store = await SqliteTimelineStore.open(INDEPENDENT_FOOTAGE, read_only=True)
        with pytest.raises(AppError) as refused:
            await load_searchable_timeline(store, COVERAGE_GAP_RUN)
        assert refused.value.code == "retrieval.coverage_gap"

    asyncio.run(run())


def test_local_completed_demo_phase0_jump_titles_not_lexical_hits():
    """TD004 offline: real Completed JUMP title cards must not rank for bare jump."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = {doc.event_id: doc for doc in _documents(timeline)}
        title_events = {
            event_id
            for event_id, doc in docs.items()
            if "jump assemble" in doc.positive_text.casefold()
            or "jump明星大乱斗" in doc.positive_text.casefold()
            or "少年jump正版授权" in doc.positive_text.casefold()
        }
        assert title_events, "fixture regression: expected JUMP title cards in demo-phase0"
        for query in ("jump", "JUMP"):
            result = await search_timeline(timeline, query, mode="lexical", top_k=20)
            hit_events = {item.event_id for item in result.candidates}
            assert hit_events.isdisjoint(title_events), sorted(hit_events & title_events)

    asyncio.run(run())


def test_local_completed_demo_phase0_jump_titles_excluded_in_hybrid():
    """TD004: adversarial equal embeddings must not revive JUMP title cards."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = {doc.event_id: doc for doc in _documents(timeline)}
        title_events = {
            event_id
            for event_id, doc in docs.items()
            if "jump assemble" in doc.positive_text.casefold()
            or "jump明星大乱斗" in doc.positive_text.casefold()
            or "少年jump正版授权" in doc.positive_text.casefold()
        }
        assert title_events
        result = await search_timeline(
            timeline,
            "jump",
            mode="hybrid",
            embedding_provider=EqualSimilarity(),
            top_k=20,
        )
        hit_events = {item.event_id for item in result.candidates}
        assert hit_events.isdisjoint(title_events), sorted(hit_events & title_events)

    asyncio.run(run())


def test_local_completed_demo_phase0_fight_tag_only_noise_excluded():
    """demo-phase0: fight/combat lexical hits must carry fight language in positive_text."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = {doc.event_id: doc for doc in _documents(timeline)}
        fight_terms = ("战斗", "打斗", "fight", "fights", "fighting", "combat")
        for query in ("fight", "combat", "战斗", "打斗"):
            result = await search_timeline(timeline, query, mode="lexical", top_k=20)
            assert result.candidates, f"expected some fight-in-facts hits for {query!r}"
            for item in result.candidates:
                doc = docs[item.event_id]
                assert any(term in doc.positive_text for term in fight_terms), (
                    query,
                    item.event_id,
                    doc.tags,
                    doc.positive_text[:120],
                )
                # Tag-only damage floaters must not survive
                if not any(term in doc.positive_text for term in fight_terms):
                    raise AssertionError("unreachable")

    asyncio.run(run())


def test_local_completed_demo_phase0_attack_tag_only_still_reachable_after_fight_filter():
    """Regression: fight tag-noise filter must not swallow TD010 attack tag-only recall."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = _documents(timeline)
        tag_only_attack = [
            doc
            for doc in docs
            if any("攻击" in tag for tag in doc.tags) and "攻击" not in doc.positive_text
        ]
        assert tag_only_attack
        result = await search_timeline(timeline, "攻击", mode="lexical", top_k=20)
        hit_events = {item.event_id for item in result.candidates}
        assert any(doc.event_id in hit_events for doc in tag_only_attack)

    asyncio.run(run())


def test_local_completed_demo_phase0_move_hits_require_positive_text_action():
    """demo-phase0: move/移动 lexical hits must carry move language in positive_text."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = {doc.event_id: doc for doc in _documents(timeline)}
        move_terms = ("移动", "move", "moves", "moving", "movement")
        for query in ("move", "moving", "移动"):
            result = await search_timeline(timeline, query, mode="lexical", top_k=20)
            assert result.candidates, f"expected move-in-facts hits for {query!r}"
            for item in result.candidates:
                doc = docs[item.event_id]
                assert any(term in doc.positive_text for term in move_terms), (
                    query,
                    item.event_id,
                    doc.tags,
                    doc.positive_text[:120],
                )

    asyncio.run(run())


def test_local_completed_demo_phase0_candidate_sources_contract():
    """candidate_sources: score-free inventory, time-ordered, aligned with search ids."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        from gamingcreator.application.retrieval import candidate_sources

        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = _documents(timeline)
        sources = candidate_sources(timeline)
        assert len(sources) == len(docs) >= 50
        assert [s.source_range.start_us for s in sources] == sorted(
            s.source_range.start_us for s in sources
        )
        assert not hasattr(sources[0], "score")
        assert not hasattr(sources[0], "score_kind")
        by_id = {s.candidate_id: s for s in sources}
        assert len(by_id) == len(sources)

        # Observable facts only: bare mechanicTags do not substitute into inventory facts.
        for doc in docs:
            src = next(s for s in sources if s.event_id == doc.event_id)
            assert src.observable_facts == doc.facts
            assert src.evidence_ids == doc.evidence_ids
            assert src.media_id == doc.media_id
            for tag in doc.tags:
                if tag and tag not in "\n".join(doc.facts):
                    assert tag not in "\n".join(src.observable_facts)

        result = await search_timeline(timeline, "移动", mode="lexical", top_k=20)
        assert result.candidates
        for hit in result.candidates:
            assert hit.candidate_id in by_id
            src = by_id[hit.candidate_id]
            assert src.event_id == hit.event_id
            assert src.source_range == hit.source_range
            assert src.evidence_ids == hit.evidence_ids
            assert src.observable_facts == hit.observable_facts

    asyncio.run(run())


def test_local_completed_demo_phase0_lexical_evidence_channels():
    """demo-phase0: attack tag-only => mechanic_tags; fight/move hits => positive_text|mixed."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        docs = {doc.event_id: doc for doc in _documents(timeline)}

        attack = await search_timeline(timeline, "攻击", mode="lexical", top_k=20)
        assert attack.candidates
        tag_only = [
            item
            for item in attack.candidates
            if "攻击" not in docs[item.event_id].positive_text
        ]
        assert tag_only, "fixture regression: expected tag-only attack hits"
        for item in tag_only:
            assert item.lexical_evidence == "mechanic_tags"
            assert "lexicalEvidence=mechanic_tags" in item.why

        for query, terms in (
            ("战斗", ("战斗", "打斗", "fight", "combat")),
            ("移动", ("移动", "move", "moving", "movement")),
        ):
            result = await search_timeline(timeline, query, mode="lexical", top_k=20)
            assert result.candidates, query
            for item in result.candidates:
                assert item.lexical_evidence in {"positive_text", "mixed"}, (
                    query,
                    item.event_id,
                    item.lexical_evidence,
                    docs[item.event_id].positive_text[:80],
                )
                assert item.lexical_evidence != "mechanic_tags"
                assert any(term in docs[item.event_id].positive_text for term in terms)

    asyncio.run(run())


def test_local_completed_demo_phase0_jump_title_only_abstains():
    """demo-phase0: jump/跳跃 with only JUMP title cards => no_positive_action_evidence."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        for query in ("jump", "跳跃", "JUMP"):
            result = await search_timeline(timeline, query, mode="lexical", top_k=10)
            assert result.candidates == ()
            assert result.abstention_reason == "no_positive_action_evidence", query

        # Positive controls: action hits must not abstain.
        move = await search_timeline(timeline, "移动", mode="lexical", top_k=5)
        assert move.candidates
        assert move.abstention_reason is None
        attack = await search_timeline(timeline, "攻击", mode="lexical", top_k=5)
        assert attack.candidates
        assert attack.abstention_reason is None

    asyncio.run(run())


def test_local_completed_demo_phase0_search_result_ranking_contract():
    """demo-phase0 lexical results always satisfy ranking inert contract."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        from gamingcreator.application.retrieval import assert_search_result_contract

        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        for query in ("移动", "攻击", "战斗", "jump", "草地", ""):
            result = await search_timeline(timeline, query, mode="lexical", top_k=10)
            assert result.score_is_probability is False
            assert_search_result_contract(result)
            if query == "jump":
                assert result.abstention_reason == "no_positive_action_evidence"
            if query == "":
                assert result.abstention_reason == "empty_query"

    asyncio.run(run())


def test_local_completed_demo_phase0_project_search_ranking_contract():
    """demo-phase0 joint lexical search satisfies project ranking inert contract."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        from gamingcreator.application.retrieval import (
            PROJECT_RETRIEVAL_VERSION,
            assert_project_search_result_contract,
            search_timelines,
        )

        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        move = await search_timelines((timeline,), "移动", mode="lexical", top_k=5)
        assert move.candidates
        assert move.retrieval_version == PROJECT_RETRIEVAL_VERSION
        assert move.score_is_probability is False
        assert all(row.run_id == COMPLETED_RUN_DEMO for row in move.candidates)
        assert_project_search_result_contract(move)

        jump = await search_timelines((timeline,), "jump", mode="lexical", top_k=5)
        assert jump.candidates == ()
        assert jump.abstention_reason == "no_positive_action_evidence"
        assert_project_search_result_contract(jump)

    asyncio.run(run())


def test_local_completed_demo_phase0_search_document_and_sources_contracts():
    """demo-phase0: CLI search projection + candidate_sources inventory contracts."""
    _require_sqlite(DEMO_PHASE0)

    async def run() -> None:
        from gamingcreator.application.retrieval import (
            assert_candidate_sources_contract,
            assert_search_document_contract,
            candidate_sources,
        )
        from gamingcreator.cli.main import _search_document

        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        timeline = await store.load_completed_timeline(COMPLETED_RUN_DEMO)
        sources = candidate_sources(timeline)
        assert_candidate_sources_contract(sources)
        assert len(sources) >= 50

        move = await search_timeline(timeline, "移动", mode="lexical", top_k=5)
        move_doc = _search_document(move, elapsed_ms=2)
        assert_search_document_contract(move_doc)
        assert all(row["candidateId"] in {s.candidate_id for s in sources} for row in move_doc["candidates"])

        jump = await search_timeline(timeline, "jump", mode="lexical", top_k=5)
        jump_doc = _search_document(jump, elapsed_ms=1)
        assert jump_doc["abstentionReason"] == "no_positive_action_evidence"
        assert jump_doc["candidates"] == []
        assert_search_document_contract(jump_doc)

    asyncio.run(run())
