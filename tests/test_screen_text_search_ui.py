"""C10: the search page shows a separate, verifiable screen-text results area."""

from __future__ import annotations

from pathlib import Path

from test_inspection_http import workspace
from test_project_search_workspace import choose_sources, guard, pool
from test_screen_text_search_http import _plant_cache

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/gamingcreator/ui/static/index.html"
APP = ROOT / "src/gamingcreator/ui/static/app.js"


def test_search_page_has_separate_screen_text_region():
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="include-screen-text"' in html
    assert "含屏幕文字" in html
    assert 'id="screen-text-results"' in html
    assert "不是事实，也不是人工验收结果" in html
    candidate_at = html.find('id="candidate-list"')
    region_at = html.find('id="screen-text-results"')
    assert 0 <= candidate_at < region_at
    between = html[candidate_at:region_at]
    assert "</div>" in between
    # The results <section> starts after the candidate list has already been closed.
    assert between.rstrip().endswith("<section")


def test_search_script_sends_option_only_when_checked_and_renders_outside_candidates():
    script = APP.read_text(encoding="utf-8")
    assert "includeScreenText: true" in script
    assert 'ui["include-screen-text"].checked' in script
    assert "renderScreenTextResults" in script
    assert 'ui["screen-text-list"].append(card)' in script
    assert 'element("article", `screen-text-card${selected ? " active" : ""}`)' in script
    assert 'ui["candidate-list"].append(card)' in script
    # Screen-text cards must not be appended to the original candidate list.
    render = script[
        script.find("function renderScreenTextResults") : script.find("function clearProjectSearch")
    ]
    assert 'ui["candidate-list"]' not in render
    assert "不是事实" in INDEX.read_text(encoding="utf-8")


def test_browser_shows_source_text_and_time_outside_candidate_list(tmp_path, monkeypatch):
    playwright = __import__("pytest").importorskip("playwright.sync_api")
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    cache, first = _plant_cache(tmp_path, project, "run-0", "建造营地")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            playwright.expect(page.locator("#search-scope-label")).to_contain_text("3 段录像")
            box = page.locator("#include-screen-text")
            playwright.expect(box).to_be_enabled()
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            playwright.expect(page.locator("#screen-text-results")).to_be_hidden()

            box.check()
            page.locator("#search-button").click()
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            region = page.locator("#screen-text-results")
            playwright.expect(region).to_be_visible()
            playwright.expect(region).to_contain_text("不是事实，也不是人工验收结果")
            card = page.locator(".screen-text-card")
            playwright.expect(card).to_have_count(1)
            playwright.expect(card).to_contain_text("建造营地")
            playwright.expect(card).to_contain_text("run-0")
            playwright.expect(card).to_contain_text(f"证据 · {first[0]}")
            playwright.expect(card).to_contain_text("源时刻")
            playwright.expect(card).to_contain_text(str(first[1]))
            playwright.expect(page.locator("#candidate-list .screen-text-card")).to_have_count(0)
            playwright.expect(page.locator(".screen-text-text")).to_have_text("建造营地")
            sha = card.locator(".screen-text-hash").inner_text()
            assert sha.startswith("原片哈希 · ")
            assert len(sha.split("·", 1)[1].strip()) == 64
        finally:
            browser.close()
