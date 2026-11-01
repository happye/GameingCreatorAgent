"""TD004: demo-phase0 Boss place-name / partial-match contracts.

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


def test_demo_phase0_compound_boss_query_does_not_hit_death_forest_only():
    _require_db()

    async def run() -> None:
        store = await _open()
        tl = await load_searchable_timeline(store, COMPLETED)
        result = await search_timeline(tl, "穿着死亡铠甲的恶魔领主Boss", mode="lexical")
        for candidate in result.candidates:
            joined = " ".join(candidate.observable_facts)
            assert "死亡森林" not in joined or (
                "铠甲" in joined and ("领主" in joined or "恶魔" in joined)
            ), joined
        # This completed run has no true multi-facet Boss clip for that query.
        assert result.candidates == ()

    asyncio.run(run())
