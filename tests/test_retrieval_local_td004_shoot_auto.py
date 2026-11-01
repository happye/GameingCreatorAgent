"""TD004: demo-phase0 readonly shoot/auto residual contracts.

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


@pytest.mark.parametrize("query", ["shoot", "射击", "开枪", "shooting"])
def test_demo_phase0_shoot_queries_have_no_positive_hits(query):
    _require_db()

    async def run() -> None:
        store = await _open()
        tl = await load_searchable_timeline(store, COMPLETED)
        result = await search_timeline(tl, query, mode="lexical")
        assert result.candidates == ()
        assert result.abstention_reason == "no_positive_action_evidence"

    asyncio.run(run())


def test_demo_phase0_automotive_repair_query_empty():
    _require_db()

    async def run() -> None:
        store = await _open()
        tl = await load_searchable_timeline(store, COMPLETED)
        result = await search_timeline(tl, "汽车修理工拆卸发动机维修车辆", mode="lexical")
        assert result.candidates == ()

    asyncio.run(run())
