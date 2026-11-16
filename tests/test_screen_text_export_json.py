"""C15: project-search JSON export includes on-screen screen-text sources."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_search_workspace import choose_sources, guard, pool
from test_screen_text_search_http import _plant_cache

APP = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/app.js"
BLOCKED = {
    "cost",
    "costs",
    "fee",
    "fees",
    "budget",
    "secret",
    "secrets",
    "apiKey",
    "api_key",
    "password",
    "ledger",
    "paidRequests",
    "maxCostCny",
    "costCny",
    "providerKey",
    "authorization",
    "accessToken",
}
MATCH_FIELDS = {"runId", "sourceSha256", "evidenceId", "timeUs", "timeTimecode", "text"}


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_export_helpers_keep_on_screen_fields_and_drop_secrets():
    script = APP.read_text(encoding="utf-8")
    assert "function projectSearchExportDocument" in script
    assert "function screenTextExportMatches" in script
    assert "BLOCKED_SEARCH_EXPORT_KEYS" in script
    assert "本机识别出的文字，不是事实，也不是人工验收结果" in script
    assert "JSON.stringify(state.projectSearch, null, 2)" not in script
    body = script[
        script.find("function screenTextExportMatches") : script.find(
            "function projectSearchExportDocument"
        )
    ]
    for field in ("runId", "sourceSha256", "evidenceId", "timeUs", "timeTimecode", "text"):
        assert field in body


def test_browser_json_export_matches_visible_screen_text_and_omits_hidden_group(
    tmp_path, monkeypatch
):
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
            page.locator("#include-screen-text").check()
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            card = page.locator(".screen-text-card")
            playwright.expect(card).to_have_count(1)
            run_id = card.get_attribute("data-run")
            evidence_id = card.get_attribute("data-evidence")
            time_us = int(card.get_attribute("data-time-us"))
            digest = re.search(
                r"[a-f0-9]{64}", card.locator(".screen-text-hash").inner_text()
            ).group(0)
            with page.expect_download() as pending:
                page.locator("#download-project-search").click()
            payload = json.loads(Path(pending.value.path()).read_text(encoding="utf-8"))
            assert payload["schemaVersion"] == "project-search-v1"
            assert [row["rank"] for row in payload["candidates"]] == [1, 2, 3]
            assert set(_keys(payload)).isdisjoint(BLOCKED)
            dumped = json.dumps(payload, ensure_ascii=False)
            assert "新证据" not in dumped
            assert (
                payload["screenTextDisclaimer"] == "本机识别出的文字，不是事实，也不是人工验收结果"
            )
            assert len(payload["screenTextMatches"]) == 1
            row = payload["screenTextMatches"][0]
            assert set(row) == MATCH_FIELDS
            assert row["runId"] == run_id == "run-0"
            assert row["evidenceId"] == evidence_id
            assert row["timeUs"] == time_us
            assert row["timeTimecode"] in card.locator(".screen-text-meta").inner_text()
            assert row["sourceSha256"] == digest
            assert row["text"] == "建造营地"
            assert card.locator(".screen-text-text").inner_text() == "建造营地"

            page.locator("#include-screen-text").uncheck()
            playwright.expect(page.locator("#screen-text-results")).to_be_hidden()
            with page.expect_download() as pending:
                page.locator("#download-project-search").click()
            hidden = json.loads(Path(pending.value.path()).read_text(encoding="utf-8"))
            assert [row["rank"] for row in hidden["candidates"]] == [1, 2, 3]
            assert "screenTextMatches" not in hidden
            assert "screenTextPrepared" not in hidden
            assert "screenTextNotice" not in hidden
            assert "screenTextDiagnostics" not in hidden
            assert "screenTextDisclaimer" not in hidden
        finally:
            browser.close()
