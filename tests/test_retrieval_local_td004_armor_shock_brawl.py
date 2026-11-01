"""TD004: demo-phase0 residual armor / shockwave / brawl-mode contracts.

Missing DB => skip. No paid calls. Does not close TD004/F006.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gamingcreator.application.retrieval import load_searchable_timeline, search_timeline
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "artifacts" / "demo-phase0"
COMPLETED = "f76f5d6495314c04ae04083614d4afd6"
_OPENED: list[SqliteTimelineStore] = []


async def _open() -> SqliteTimelineStore:
    store = await SqliteTimelineStore.open(DEMO, read_only=True)
    _OPENED.append(store)
    return store


@pytest.fixture(autouse=True)
def _close_stores():
    yield
    while _OPENED:
        asyncio.run(_OPENED.pop().close())


def _require_db() -> None:
    if not (DEMO / "timeline.sqlite3").is_file():
        pytest.skip(f"local artifact DB missing: {DEMO / 'timeline.sqlite3'}")


def test_demo_phase0_red_armor_query_does_not_hit_red_vfx_only():
    _require_db()

    async def run() -> None:
        store = await _open()
        tl = await load_searchable_timeline(store, COMPLETED)
        result = await search_timeline(tl, "红色铠甲", mode="lexical")
        for candidate in result.candidates:
            joined = " ".join(candidate.observable_facts)
            assert "铠甲" in joined or "armor" in joined.casefold(), joined
        # This completed run has no true armor clip for that query.
        assert result.candidates == ()

    asyncio.run(run())


def test_demo_phase0_shockwave_query_does_not_hit_bare_cast_skill():
    _require_db()

    async def run() -> None:
        store = await _open()
        tl = await load_searchable_timeline(store, COMPLETED)
        result = await search_timeline(tl, "释放冲击波", mode="lexical")
        for candidate in result.candidates:
            joined = " ".join(candidate.observable_facts)
            assert "冲击波" in joined or "shockwave" in joined.casefold(), joined
        assert result.candidates == ()
        assert result.abstention_reason == "no_positive_action_evidence"

    asyncio.run(run())


def test_demo_phase0_jump_brand_query_does_not_hit_brawl_mode_title():
    _require_db()

    async def run() -> None:
        store = await _open()
        tl = await load_searchable_timeline(store, COMPLETED)
        result = await search_timeline(tl, "JUMP明星大乱斗跳跃", mode="lexical")
        for candidate in result.candidates:
            joined = " ".join(candidate.observable_facts)
            assert "大乱斗(单人/双人)" not in joined and "大乱斗（单人/双人）" not in joined, joined
            assert "跳跃" in joined or "jump" in joined.casefold()
        assert result.candidates == ()
        assert result.abstention_reason == "no_positive_action_evidence"

    asyncio.run(run())
