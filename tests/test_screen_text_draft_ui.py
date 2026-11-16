"""C13: screen-text toggle and query drafts stay isolated to the current project."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_search_workspace import choose_sources, guard, pool
from test_screen_text_search_http import _plant_cache

APP = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/app.js"


def test_draft_helpers_are_keyed_by_project_and_uncheck_does_not_clear_search():
    script = APP.read_text(encoding="utf-8")
    assert "gamingcreator:screen-text-search-draft:" in script
    assert "function writeScreenTextDraft" in script
    assert "function applyScreenTextDraft" in script
    start = script.find('ui["include-screen-text"].addEventListener("change"')
    end = script.find('ui.query.addEventListener("input"')
    assert 0 <= start < end
    body = script[start:end]
    assert "renderScreenTextResults()" in body
    assert "clearProjectSearch" not in body
    load = script[
        script.find("async function loadRuns") : script.find("async function loadProjects")
    ]
    assert "writeScreenTextDraft(state.project)" in load
    assert "applyScreenTextDraft(project)" in load
    assert "clearProjectSearch()" in load


def test_browser_isolates_drafts_and_closes_group_without_clearing_candidates(
    tmp_path, monkeypatch
):
    playwright = pytest.importorskip("playwright.sync_api")
    project_a, _ = pool(tmp_path)
    project_b = tmp_path / "artifacts" / "project-b"
    shutil.copytree(project_a, project_b)
    guard(monkeypatch)
    _plant_cache(tmp_path, project_a, "run-0", "建造营地")
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
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            playwright.expect(page.locator(".screen-text-card")).to_have_count(1)

            page.locator("#include-screen-text").uncheck()
            playwright.expect(page.locator("#screen-text-results")).to_be_hidden()
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            playwright.expect(page.locator("#download-project-search")).to_be_enabled()

            page.locator("#query").fill("我的草稿A")
            page.locator("#include-screen-text").check()
            playwright.expect(page.locator(".screen-text-card")).to_have_count(1)
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)

            page.locator("#project-select").select_option("artifacts/project-b")
            playwright.expect(page.locator("#query")).to_have_value("")
            playwright.expect(page.locator("#include-screen-text")).not_to_be_checked()
            playwright.expect(page.locator(".screen-text-card")).to_have_count(0)
            playwright.expect(page.locator(".candidate-card")).to_have_count(0)

            page.locator("#query").fill("我的草稿B")
            page.locator("#project-select").select_option("artifacts/project")
            playwright.expect(page.locator("#query")).to_have_value("我的草稿A")
            playwright.expect(page.locator("#include-screen-text")).to_be_checked()
            playwright.expect(page.locator(".screen-text-card")).to_have_count(0)
            playwright.expect(page.locator(".candidate-card")).to_have_count(0)
        finally:
            browser.close()
