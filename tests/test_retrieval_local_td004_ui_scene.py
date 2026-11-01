"""TD004: demo-phase0 UI scene-label chrome vs real fight observations.

Read-only against artifacts/demo-phase0. Missing DB => skip. No paid calls.
Does not claim TD004/F006 closed.
"""

from __future__ import annotations

import asyncio
import sqlite3
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


def test_demo_phase0_jump_title_cards_excluded_for_jump_query():
    _require_db()

    async def run() -> None:
        store = await _open()
        tl = await load_searchable_timeline(store, COMPLETED)
        result = await search_timeline(tl, "jump", mode="lexical")
        facts = [" ".join(c.observable_facts) for c in result.candidates]
        assert all("JUMP明星大乱斗" not in text and "JUMP ASSEMBLE" not in text for text in facts)
        # Title-only corpus for jump should abstain on this completed run.
        assert result.candidates == ()
        assert result.abstention_reason == "no_positive_action_evidence"

    asyncio.run(run())


def test_demo_phase0_fight_query_drops_skill_button_scene_chrome():
    """Layout lines whose only fight token sits in 「对战场景」stay out; 交战 can remain."""
    _require_db()

    async def run() -> None:
        store = await _open()
        tl = await load_searchable_timeline(store, COMPLETED)
        result = await search_timeline(tl, "对战", mode="lexical")
        for candidate in result.candidates:
            joined = " ".join(candidate.observable_facts)
            if "技能按钮" in joined or "方向摇杆" in joined:
                # Must still have free-standing fight evidence beyond UI collocation.
                assert ("交战" in joined) or ("战斗" in joined and "战斗界面" not in joined) or (
                    "对战" in joined and "对战场景" not in joined
                ), joined

    asyncio.run(run())
