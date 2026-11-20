"""C14: cancel a slow search, and A→B→A must not accept an earlier A result."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_search_workspace import choose_sources, guard, pool

APP = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/app.js"
INDEX = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/index.html"

HOLD_SEARCH = """(() => {
    const original = window.fetch;
    window.pendingSearches = [];
    window.fetch = async (url, options) => {
        const target = typeof url === "string" ? url : (url && (url.href || url.url)) || "";
        if (new URL(target, window.location.origin).pathname !== "/api/search-project") {
            return original(url, options);
        }
        const response = await original(url, { ...options, signal: undefined });
        const data = await response.clone().json();
        return new Promise((resolve) => {
            window.pendingSearches.push((label) => {
                if (label && Array.isArray(data.candidates) && data.candidates[0]) {
                    const row = data.candidates[0];
                    row.observableFacts = [...(row.observableFacts || []), label];
                    if (Array.isArray(row.displayFacts)) row.displayFacts = [...row.displayFacts, label];
                }
                resolve(new Response(JSON.stringify(data), {
                    status: 200,
                    headers: { "Content-Type": "application/json" },
                }));
            });
        });
    };
})();"""


def test_cancel_control_and_token_guard_are_present():
    markup = INDEX.read_text(encoding="utf-8")
    script = APP.read_text(encoding="utf-8")
    assert 'id="cancel-search"' in markup
    assert "function beginSearchToken" in script
    assert "function searchStillCurrent" in script
    assert "function cancelInFlightSearch" in script
    assign = script.find("state.projectSearch = result;")
    assert assign > 0
    prefix = script[script.rfind("if (!searchStillCurrent", 0, assign) : assign]
    assert 'searchStillCurrent(token, controller, "projectSearchController", revision)' in prefix
    assert "if (state.busy && !state.searching) return;" in script
    assert 'ui["search-button"].disabled = (busy && !state.searching) || !completed;' in script


def test_browser_cancel_ignores_late_search_result(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    pool(tmp_path)
    guard(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.add_init_script(HOLD_SEARCH)
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            page.wait_for_function("() => window.pendingSearches.length === 1")
            playwright.expect(page.locator("#cancel-search")).to_be_visible()
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            page.locator("#cancel-search").click()
            playwright.expect(page.locator("#candidate-list")).to_contain_text("查询已取消")
            playwright.expect(page.locator("#cancel-search")).to_be_hidden()
            page.evaluate("window.pendingSearches[0]('不该出现的取消结果')")
            page.wait_for_timeout(300)
            playwright.expect(page.locator(".candidate-card")).to_have_count(0)
            playwright.expect(page.locator("#candidate-list")).to_contain_text("查询已取消")
            playwright.expect(page.locator("#candidate-list")).not_to_contain_text(
                "不该出现的取消结果"
            )
        finally:
            browser.close()


def test_browser_aba_ignores_earlier_a_with_the_same_query(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    pool(tmp_path)
    guard(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.add_init_script(HOLD_SEARCH)
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            page.wait_for_function("() => window.pendingSearches.length === 1")
            page.locator("#query").fill("哨塔")
            page.locator("#search-button").click()
            page.wait_for_function("() => window.pendingSearches.length === 2")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            page.wait_for_function("() => window.pendingSearches.length === 3")
            page.evaluate("window.pendingSearches[2]('第二次查询A')")
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            playwright.expect(page.locator(".candidate-facts").first).to_contain_text("第二次查询A")
            page.evaluate("window.pendingSearches[0]('第一次查询A')")
            page.evaluate("window.pendingSearches[1]('查询B不该留下')")
            page.wait_for_timeout(300)
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            playwright.expect(page.locator(".candidate-facts").first).to_contain_text("第二次查询A")
            playwright.expect(page.locator("#candidate-list")).not_to_contain_text("第一次查询A")
            playwright.expect(page.locator("#candidate-list")).not_to_contain_text("查询B不该留下")
        finally:
            browser.close()
