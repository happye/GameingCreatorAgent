"""C11: clicking a screen-text hit locates the matching source run and evidence."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_search_workspace import choose_sources, guard, pool
from test_screen_text_search_http import _plant_cache

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/gamingcreator/ui/static/app.js"


def _timecode(us: int) -> str:
    ms = us // 1000
    seconds = ms // 1000
    return f"{seconds // 3600:02d}:{(seconds // 60) % 60:02d}:{seconds % 60:02d}.{ms % 1000:03d}"


def test_locate_script_uses_source_clock_not_output_timeline():
    script = APP.read_text(encoding="utf-8")
    start = script.find("function seekSourceInstant")
    end = script.find("async function openJointCandidate")
    assert 0 <= start < end
    body = script[start:end]
    assert "SourceClock.sourceUsToPlayerSeconds" in body
    assert "clipFrames" not in body
    assert "editTimeline" not in body
    assert "state.run !== row.runId" in body
    assert "switchRun(row.runId, true)" in body


def test_browser_click_locates_correct_run_source_time_and_evidence(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    _, first = _plant_cache(tmp_path, project, "run-0", "建造营地")
    _, second = _plant_cache(tmp_path, project, "run-1", "建造哨塔")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            page.locator("#include-screen-text").check()
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            cards = page.locator(".screen-text-card")
            playwright.expect(cards).to_have_count(2)

            cards.nth(1).click()
            playwright.expect(page.locator("#run-select")).to_have_value("run-1")
            playwright.expect(page.locator("#active-title")).to_have_text("屏幕文字 · run-1")
            playwright.expect(page.locator("#active-range")).to_have_text(
                f"源时刻 {_timecode(second[1])}"
            )
            playwright.expect(page.locator("#active-facts")).to_have_text("建造哨塔")
            playwright.expect(page.locator("#current-time")).to_have_text(_timecode(second[1]))
            playwright.expect(page.locator("#evidence-panel")).to_be_visible()
            playwright.expect(page.locator("#evidence-list .evidence-card.active")).to_have_count(1)
            playwright.expect(page.locator(".screen-text-card.active")).to_have_attribute(
                "data-run", "run-1"
            )
            playwright.expect(page.locator(".screen-text-card.active")).to_have_attribute(
                "data-evidence", second[0]
            )

            cards.nth(0).click()
            playwright.expect(page.locator("#run-select")).to_have_value("run-0")
            playwright.expect(page.locator("#active-title")).to_have_text("屏幕文字 · run-0")
            playwright.expect(page.locator("#active-range")).to_have_text(
                f"源时刻 {_timecode(first[1])}"
            )
            playwright.expect(page.locator("#active-facts")).to_have_text("建造营地")
            playwright.expect(page.locator("#current-time")).to_have_text(_timecode(first[1]))
            playwright.expect(page.locator(".screen-text-card.active")).to_have_attribute(
                "data-run", "run-0"
            )
            playwright.expect(page.locator(".screen-text-card.active")).to_have_attribute(
                "data-evidence", first[0]
            )
        finally:
            browser.close()
