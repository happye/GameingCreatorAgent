"""Actual lexical group attribution and raw ranking downloads on both viewport sizes."""

import json
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_detail_query_browser import open_pool
from test_saved_detail_actor_semantics import FocusedEmbedding
from test_saved_detail_retrieval import detail_pool  # noqa: F401 - shared fixture

from gamingcreator.infrastructure.detail_query_sidecar import read_saved_detail_corpus


@pytest.mark.parametrize("width", [1366, 390])
@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_grouped_lexical_ranking_downloads_actual_group_and_clears_conditions_on_profile_change(
    tmp_path, request, monkeypatch, width, mode
):
    project, timeline, _, _ = request.getfixturevalue("detail_pool")
    corpus = read_saved_detail_corpus(project, (timeline,), "v2")
    monkeypatch.setattr(
        "gamingcreator.cli.main.LocalEmbeddingProvider.from_manifest",
        lambda _: FocusedEmbedding([row.facts for row in corpus.supplement.semantic_facets]),
    )
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": width, "height": 768 if width == 1366 else 844},
                accept_downloads=True,
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            open_pool(page, base, project)
            page.locator("#query").fill("white hair")
            page.locator("#mode").select_option(mode)
            page.locator("#include-saved-details").check()
            page.locator("#search-button").click()
            playwright.expect(page.locator(".candidate-card")).to_have_count(1)
            card = page.locator(".candidate-card")
            card.locator(".candidate-detail-search summary").click()
            playwright.expect(card).to_contain_text("本次词法采用主体组 1 的独立细节")
            with page.expect_download() as pending:
                page.locator("#download-project-search").click()
            saved = json.loads(Path(pending.value.path()).read_bytes())
            assert saved["detailRetrieval"]["version"] == "saved-detail-text-v3"
            assert saved["candidates"][0]["lexicalDetailFacetId"] == card.get_attribute(
                "data-lexical-facet"
            )
            assert saved["candidates"][0]["lexicalDetailFacetId"] in {
                row.facet_id for row in corpus.supplement.semantic_facets
            }
            page.locator("#open-search-detail-query").click()
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator("#search-detail-summary")).to_contain_text("全部满足 1")
            page.locator("#close-detail-query").click()
            page.locator("#detail-profile").select_option("v4")
            playwright.expect(page.locator(".candidate-condition-proof")).to_have_count(0)
            playwright.expect(page.locator("#open-search-detail-query")).to_be_disabled()
            assert page.locator(".candidate-card").count() == 1
            assert not errors and page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        finally:
            browser.close()
