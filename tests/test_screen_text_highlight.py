"""C12: screen-text highlight keeps Unicode intact and renders HTML as text."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_search_workspace import choose_sources, guard, pool
from test_screen_text_search_http import _plant_cache

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src/gamingcreator/ui/static/screen-text-highlight.js"


def _parts(text: str, query: str):
    import json
    import subprocess

    script = """
const api = require(process.argv[1]);
const text = process.argv[2];
const query = process.argv[3];
process.stdout.write(JSON.stringify(api.screenTextHighlightRanges(text, query)));
"""
    result = subprocess.run(
        ["node", "-e", script, str(HELPER), text, query],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_highlight_keeps_emoji_combining_and_fullwidth_characters():
    family = "家人们👨‍👩‍👧在场"
    parts = _parts(family, "👨‍👩‍👧")
    assert "".join(item["value"] for item in parts) == family
    hits = [item["value"] for item in parts if item["hit"]]
    assert hits == ["👨‍👩‍👧"]

    combining = "cafe\u0301店"
    parts = _parts(combining, "café")
    assert "".join(item["value"] for item in parts) == combining
    assert [item["value"] for item in parts if item["hit"]] == ["cafe\u0301"]
    assert all(item["value"] != "e" for item in parts if item["hit"])

    fullwidth = "全角Ｂｕｉｌｄ完成"
    parts = _parts(fullwidth, "BUILD")
    assert "".join(item["value"] for item in parts) == fullwidth
    assert [item["value"] for item in parts if item["hit"]] == ["Ｂｕｉｌｄ"]


def test_highlight_treats_html_as_plain_text_parts():
    raw = "<b>建造</b>"
    parts = _parts(raw, "建造")
    assert "".join(item["value"] for item in parts) == raw
    assert [item["value"] for item in parts if item["hit"]] == ["建造"]
    assert [item["value"] for item in parts if not item["hit"]] == ["<b>", "</b>"]


def test_browser_highlight_shows_html_as_text_and_keeps_emoji(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    _plant_cache(tmp_path, project, "run-0", "<b>建造</b>👨‍👩‍👧")
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
            text = page.locator(".screen-text-text")
            playwright.expect(text).to_have_count(1)
            playwright.expect(text).to_have_text("<b>建造</b>👨‍👩‍👧")
            assert text.locator("b").count() == 0
            assert text.locator("img").count() == 0
            mark = text.locator("mark.screen-text-hit")
            playwright.expect(mark).to_have_text("建造")
            playwright.expect(text).to_contain_text("👨‍👩‍👧")
        finally:
            browser.close()
