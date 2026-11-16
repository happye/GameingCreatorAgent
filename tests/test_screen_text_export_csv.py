"""C16: project-search CSV keeps Chinese text, escapes cells, and blocks formula prefixes."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_search_workspace import choose_sources, guard, pool
from test_screen_text_search_http import _plant_cache

APP = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/app.js"
INDEX = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/index.html"
SCREEN_TEXT = "=1+1，建造营地\n第二行,仍是原文"


def test_csv_export_control_and_formula_guard_are_present():
    markup = INDEX.read_text(encoding="utf-8")
    script = APP.read_text(encoding="utf-8")
    assert 'id="download-project-search-csv"' in markup
    assert "function exportProjectSearchCsv" in script
    assert "function downloadProjectSearchCsv" in script
    body = script[script.find("function csvCell") : script.find("function exportProjectSearchCsv")]
    assert r"\uFF1D" in body and r"\uFF0B" in body
    assert (
        r"\uFEFF"
        in script[
            script.find("function exportProjectSearchCsv") : script.find(
                "function downloadProjectSearchCsv"
            )
        ]
    )


def test_browser_csv_keeps_chinese_escapes_breaks_and_formula_prefix(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    _plant_cache(tmp_path, project, "run-0", SCREEN_TEXT)
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
            playwright.expect(page.locator(".screen-text-card")).to_have_count(1)
            playwright.expect(page.locator("#download-project-search-csv")).to_be_enabled()
            with page.expect_download() as pending:
                page.locator("#download-project-search-csv").click()
            raw = Path(pending.value.path()).read_bytes()
            assert raw.startswith(b"\xef\xbb\xbf")
            text = raw.decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(text)))
            candidates = [row for row in rows if row["rowKind"] == "candidate"]
            matches = [row for row in rows if row["rowKind"] == "screen-text"]
            assert len(candidates) == 3
            assert len(matches) == 1
            row = matches[0]
            assert row["runId"] == "run-0"
            assert row["text"] == "'" + SCREEN_TEXT
            assert "\n" in row["text"]
            assert "，建造营地" in row["text"]
            assert "第二行,仍是原文" in row["text"]
            assert row["sourceSha256"] and len(row["sourceSha256"]) == 64
            assert "\"'=1+1，建造营地" in text or "\"'=1+1，建造营地" in text

            page.locator("#include-screen-text").uncheck()
            with page.expect_download() as pending:
                page.locator("#download-project-search-csv").click()
            hidden = list(
                csv.DictReader(
                    io.StringIO(Path(pending.value.path()).read_text(encoding="utf-8-sig"))
                )
            )
            assert [row["rowKind"] for row in hidden] == ["candidate", "candidate", "candidate"]
            assert all(
                row["text"] == "" or "建造营地" not in row["text"] or row["rowKind"] == "candidate"
                for row in hidden
            )
            assert not any(row["rowKind"] == "screen-text" for row in hidden)
        finally:
            browser.close()
