"""Original saved search replay plus real read-only annotation, viewport and stale scope checks."""

import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from test_detail_query import snapshot
from test_inspection_http import workspace
from test_project_detail_query_browser import open_pool
from test_search_detail_query import (
    body,
    post,
    saved_search,  # noqa: F401 - shared real storage fixture
)

from gamingcreator.application.search_detail_query import search_snapshot_sha256


def replay_search(page, saved):
    page.route(
        "**/api/search-project",
        lambda route: route.fulfill(
            json={
                **saved,
                "project": "artifacts/project",
                "searchSha256": search_snapshot_sha256(saved),
            }
        ),
    )
    page.locator("#mode").select_option(saved["mode"])
    page.locator("#query").fill(saved["query"])
    page.locator("#search-button").click()


@pytest.mark.parametrize("width", [1366, 390])
def test_candidates_keep_rank_proof_and_download_through_source_preview_and_profile_change(
    tmp_path,
    request,
    monkeypatch,
    width,
):
    project, _, saved = request.getfixturevalue("saved_search")
    before = snapshot(project)

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Do not run another search while matching, previewing or changing profile"
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
            errors, inspections = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: inspections.append(item.url) if "/api/inspect?" in item.url else None,
            )
            open_pool(page, base, project)
            replay_search(page, saved)
            playwright.expect(page.locator(".candidate-card")).to_have_count(2)
            ranks = page.locator(".candidate-card .rank").all_text_contents()
            page.locator("#open-search-detail-query").click()
            playwright.expect(page.locator("#detail-query-target")).to_contain_text(
                "只核对原搜索的 2 个候选"
            )
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator(".candidate-condition-proof")).to_have_count(2)
            playwright.expect(page.locator("#search-detail-summary")).to_contain_text("全部满足 1")
            with page.expect_download() as pending:
                page.locator("#download-search-details").click()
            result = json.loads(Path(pending.value.path()).read_bytes())
            assert result["search"] == saved and result["qualityGate"] is None
            assert [row["rank"] for row in result["matches"]] == [1, 2]
            page.locator("#close-detail-query").click()
            assert page.locator(".candidate-card .rank").all_text_contents() == ranks
            full = page.locator('.candidate-condition-proof[data-status="full"]')
            full.locator("summary").click()
            playwright.expect(full).to_contain_text("有支持")
            unknown = page.locator('.candidate-condition-proof[data-status="unverified"]')
            unknown.locator("summary").click()
            playwright.expect(unknown).to_contain_text("不代表原片没有")
            page.locator('.candidate-card[data-run="run-2"] .clip-preview').click()
            playwright.expect(page.locator("#run-select")).to_have_value("run-2")
            playwright.expect(page.locator("#active-title")).to_contain_text("候选 #")
            assert page.locator(".candidate-card .rank").all_text_contents() == ranks
            assert page.locator(".candidate-condition-proof").count() == 2
            page.locator('.candidate-card[data-run="run-2"] .select-clip').click()
            playwright.expect(page.locator("#selection-count")).to_have_text("1")
            page.locator("#detail-profile").select_option("v4")
            playwright.expect(page.locator(".candidate-condition-proof")).to_have_count(0)
            playwright.expect(page.locator("#open-search-detail-query")).to_be_enabled()
            page.locator("#open-search-detail-query").click()
            page.locator("#match-detail-query").click()
            playwright.expect(
                page.locator('.candidate-condition-proof[data-status="unverified"]')
            ).to_have_count(2)
            page.locator("#close-detail-query").click()
            assert page.locator(".candidate-card .rank").all_text_contents() == ranks
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            if width == 1366:
                assert page.locator("#candidate-list").evaluate("list=>list.clientHeight") >= 90
            assert all(
                parse_qs(urlparse(url).query, keep_blank_values=True)["query"] == [""]
                for url in inspections
            )
            assert not errors
        finally:
            browser.close()
    assert snapshot(project) == before


def test_condition_edit_and_pending_close_clear_old_or_late_evidence(tmp_path, request):
    project, _, saved = request.getfixturevalue("saved_search")
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            open_pool(page, base, project)
            replay_search(page, saved)
            page.locator("#open-search-detail-query").click()
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator(".candidate-condition-proof")).to_have_count(2)
            page.locator(".condition-value").select_option("black")
            playwright.expect(page.locator(".candidate-condition-proof")).to_have_count(0)
            assert page.locator("#download-search-details").is_disabled()
            pending = []
            page.route("**/api/match-search-details", lambda route: pending.append(route))
            with page.expect_request("**/api/match-search-details"):
                page.locator("#match-detail-query").click()
            page.locator("#close-detail-query").click()
            pending[0].fulfill(json={"schemaVersion": "stale-invalid"})
            page.locator("#query").fill("new search")
            playwright.expect(page.locator("#open-search-detail-query")).to_be_disabled()
            assert page.locator(".candidate-condition-proof").count() == 0
        finally:
            browser.close()


@pytest.mark.parametrize("field", ["searchId", "profile", "candidateId"])
def test_mismatched_saved_search_response_never_labels_candidates(tmp_path, request, field):
    project, _, saved = request.getfixturevalue("saved_search")
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base:
        code, _, data = post(base, body(project, saved))
        assert code == 200
        report = copy.deepcopy(json.loads(data))
        report["project"] = "artifacts/project"
        if field == "searchId":
            report["search"]["searchId"] = "b" * 32
        elif field == "profile":
            report["refinementProfile"] = "v4"
        else:
            report["matches"][0]["candidateId"] = "other"
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                open_pool(page, base, project)
                replay_search(page, saved)
                page.route("**/api/match-search-details", lambda route: route.fulfill(json=report))
                page.locator("#open-search-detail-query").click()
                page.locator("#match-detail-query").click()
                playwright.expect(page.locator("#detail-match-result")).to_contain_text("不一致")
                assert page.locator(".candidate-condition-proof").count() == 0
                assert page.locator("#download-search-details").is_disabled()
            finally:
                browser.close()
