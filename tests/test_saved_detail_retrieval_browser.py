"""Explicit saved-detail option, real ranking and source-safe evidence on two viewports."""

import json
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_detail_query_browser import open_pool
from test_saved_detail_retrieval import detail_pool  # noqa: F401 - shared storage fixture


@pytest.mark.parametrize("width", [1366, 390])
def test_explicit_saved_details_find_missing_candidate_and_profile_change_keeps_old_query_identity(
    tmp_path, request, monkeypatch, width
):
    project, _, _, _ = request.getfixturevalue("detail_pool")

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Do not perform a single-source search during joint preview or profile change"
        )

    monkeypatch.setattr("gamingcreator.ui.service.execute_search", forbidden)
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": width, "height": 768 if width == 1366 else 844},
                accept_downloads=True,
            )
            errors, searches = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: (
                    searches.append(item.post_data_json)
                    if item.url.endswith("/api/search-project")
                    else None
                ),
            )
            open_pool(page, base, project)
            playwright.expect(page.locator("#saved-details-control")).to_be_visible()
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("white hair")
            page.locator("#search-button").click()
            playwright.expect(page.locator("#candidate-count")).to_have_text("0")
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            assert "detailProfile" not in searches[-1]
            page.locator("#include-saved-details").check()
            page.locator("#search-button").click()
            playwright.expect(page.locator(".candidate-card")).to_have_count(1)
            assert searches[-1]["detailProfile"] == "v2"
            playwright.expect(page.locator("#search-context")).to_contain_text(
                "1/2 个事件有可检索细节"
            )
            proof = page.locator(".candidate-detail-search")
            proof.locator("summary").click()
            playwright.expect(proof).to_contain_text("白色头发")
            playwright.expect(proof).to_contain_text("待人工核对")
            assert "法杖" not in proof.inner_text()
            assert page.locator("img[src=x]").count() == 0
            with page.expect_download() as pending:
                page.locator("#download-project-search").click()
            saved = json.loads(Path(pending.value.path()).read_bytes())
            assert saved["detailRetrieval"]["profile"] == "v2"
            assert saved["qualityGate"] is None
            assert (
                saved["candidates"][0]["detailSearchEvidence"]["attributes"][0]["kind"]
                == "hair_color"
            )
            page.locator("#open-search-detail-query").click()
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator(".candidate-condition-proof")).to_have_count(1)
            playwright.expect(page.locator("#search-detail-summary")).to_contain_text("全部满足 1")
            page.locator("#close-detail-query").click()
            page.locator(".clip-preview").first.click()
            playwright.expect(page.locator("#active-title")).to_contain_text("候选 #1")
            page.locator("#detail-profile").select_option("v4")
            playwright.expect(page.locator(".candidate-condition-proof")).to_have_count(0)
            playwright.expect(page.locator("#open-search-detail-query")).to_be_disabled()
            playwright.expect(page.locator("#search-context")).to_contain_text(
                "含精分析 v2 已有细节"
            )
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            assert len(searches) == 2
            page.locator("#search-button").click()
            playwright.expect(page.locator("#candidate-count")).to_have_text("0")
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            assert searches[-1]["detailProfile"] == "v4"
            playwright.expect(page.locator("#search-context")).to_contain_text(
                "0/2 个事件有可检索细节"
            )
            assert not errors and page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            if width == 1366:
                assert page.locator("#candidate-list").evaluate("list=>list.clientHeight") >= 90
        finally:
            browser.close()


def test_legacy_backend_keeps_saved_detail_option_hidden(tmp_path, request):
    project, _, _, _ = request.getfixturevalue("detail_pool")
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(
                "**/api/health",
                lambda route: route.fulfill(
                    json={
                        "application": "gamingcreator-workspace",
                        "capabilities": ["search-detail-query-v1", "project-detail-query-v1"],
                    }
                ),
            )
            open_pool(page, base, project)
            playwright.expect(page.locator("#saved-details-control")).not_to_be_visible()
            playwright.expect(page.locator("#include-saved-details")).to_be_disabled()
        finally:
            browser.close()
