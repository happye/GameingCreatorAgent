"""C17: turning on screen-text search must not change the official Top10."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_search_workspace import body, choose_sources, guard, pool, post
from test_screen_text_search_http import _plant_cache

APP = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/service.py"
CLI = Path(__file__).resolve().parents[1] / "src/gamingcreator/cli/main.py"
TOP10_FIELDS = (
    "candidateId",
    "rank",
    "score",
    "scoreKind",
    "runId",
    "mediaId",
    "sourceSha256",
    "startUs",
    "endUs",
)


def _top10(payload):
    return [{field: row.get(field) for field in TOP10_FIELDS} for row in payload["candidates"]]


def test_payload_hashes_official_document_before_attaching_screen_text():
    service = APP.read_text(encoding="utf-8")
    cli = CLI.read_text(encoding="utf-8")
    start = service.find("async def project_search_payload")
    body_text = service[start : service.find("async def search_detail_payload", start)]
    assert "search_snapshot_sha256(document)" in body_text
    assert body_text.find("search_snapshot_sha256(document)") < body_text.find(
        "if include_screen_text:"
    )
    snippet = cli[
        cli.find("def execute_project_search") : cli.find("def execute_project_search") + 800
    ]
    assert "include_screen_text" not in snippet


def test_http_top10_stays_identical_with_screen_text_switch(tmp_path, monkeypatch):
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    _plant_cache(tmp_path, project, "run-0", "建造营地")
    with workspace(tmp_path) as base:
        off = json.loads(post(base, body(project, includeScreenText=False))[2])
        on = json.loads(post(base, body(project, includeScreenText=True))[2])
        omitted = json.loads(post(base, body(project))[2])
        assert _top10(off) == _top10(on) == _top10(omitted)
        assert [row["rank"] for row in on["candidates"]] == list(
            range(1, len(on["candidates"]) + 1)
        )
        assert off["candidates"] == on["candidates"] == omitted["candidates"]
        assert off.get("qualityGate") == on.get("qualityGate") == omitted.get("qualityGate")
        assert (
            off["modelAnalysisCalls"]
            == on["modelAnalysisCalls"]
            == omitted["modelAnalysisCalls"]
            == 0
        )
        assert "screenTextMatches" not in off and "screenTextMatches" not in omitted
        assert on["screenTextMatches"]
        assert "passes" not in on and "humanEvaluation" not in on and "humanReviewed" not in on


def test_browser_top10_cards_stay_identical_after_enabling_screen_text(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    _plant_cache(tmp_path, project, "run-0", "建造营地")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            before = page.locator("#candidate-list").inner_text()
            ranks = page.locator(".candidate-card .rank").all_text_contents()
            scores = page.locator(".candidate-card .candidate-meta").all_text_contents()
            page.locator("#include-screen-text").check()
            page.locator("#search-button").click()
            playwright.expect(page.locator(".screen-text-card")).to_have_count(1)
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            assert page.locator(".candidate-card .rank").all_text_contents() == ranks
            assert page.locator(".candidate-card .candidate-meta").all_text_contents() == scores
            assert page.locator("#candidate-list").inner_text() == before
        finally:
            browser.close()
