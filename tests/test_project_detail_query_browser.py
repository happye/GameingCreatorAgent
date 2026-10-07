"""Whole-recording typed conditions through the main workspace and saved-result API."""

import json
from pathlib import Path

import pytest
from test_detail_inspection import refuse_sends
from test_detail_query import snapshot
from test_inspection_http import workspace
from test_project_detail_query import (
    create_detail_pool,
    detail_pool,  # noqa: F401 - shared storage fixture
)


def open_pool(page, base, project):
    page.goto(base)
    page.locator('#project-select option[value="artifacts/project"]').wait_for(state="attached")
    page.locator("#project-select").select_option("artifacts/project")
    page.locator("#run-select").select_option("run-1")
    page.locator("#open-search-sources").click()
    for identifier in ("run-1", "run-2"):
        page.locator(f'#search-sources-list input[value="{identifier}"]').check()
    page.locator("#apply-search-sources").click()


@pytest.mark.parametrize("width", [1366, 390])
def test_typed_pool_filter_download_and_return_to_original_event(
    tmp_path, request, monkeypatch, width
):
    project, first, _ = request.getfixturevalue("detail_pool")
    refuse_sends(monkeypatch)
    before = snapshot(project)
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900}, accept_downloads=True)
            errors, calls = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: (
                    calls.append(item.url)
                    if "/api/search" in item.url or "/api/draft-detail-query" in item.url
                    else None
                ),
            )
            open_pool(page, base, project)
            playwright.expect(page.locator("#open-project-detail-query")).to_be_enabled()
            page.locator("#open-project-detail-query").click()
            playwright.expect(page.locator("#detail-query-target")).to_contain_text("已选 2 段录像")
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator(".project-detail-row")).to_have_count(2)
            playwright.expect(page.locator("#project-detail-summary")).to_contain_text("全部满足 1")
            playwright.expect(page.locator("#project-detail-summary")).to_contain_text("尚未验证 1")
            assert page.locator("#project-detail-next").is_disabled()
            page.locator("#project-detail-filter").select_option("full")
            playwright.expect(page.locator(".project-detail-row")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#project-detail-download").click()
            saved = json.loads(Path(pending.value.path()).read_bytes())
            assert saved["sources"][0]["runId"] == "run-1" and saved["totalEvents"] == 2
            assert saved["results"][0]["eventId"] == first.events[0].event_id
            assert saved["qualityGate"] is None and saved["status"] == "full"
            assert page.locator("#detail-query-dialog").evaluate(
                "dialog=>dialog.scrollWidth<=dialog.clientWidth"
            )
            page.locator(".project-detail-row button").click()
            playwright.expect(page.locator("#detail-query-dialog")).not_to_be_visible()
            playwright.expect(page.locator("#active-range")).to_contain_text("00:00:00.100")
            assert page.locator("#run-select").input_value() == "run-1"
            assert not errors and not calls
        finally:
            browser.close()
    assert snapshot(project) == before


def test_close_pending_query_discards_late_result_and_reopening_restores_controls(
    tmp_path, request
):
    project, _, _ = request.getfixturevalue("detail_pool")
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            open_pool(page, base, project)
            playwright.expect(page.locator("#open-project-detail-query")).to_be_enabled()
            pending = []
            page.route("**/api/match-project-details", lambda route: pending.append(route))
            page.locator("#open-project-detail-query").click()
            with page.expect_request("**/api/match-project-details"):
                page.locator("#match-detail-query").click()
            playwright.expect(page.locator("#project-detail-filter")).to_be_disabled()
            page.locator("#close-detail-query").click()
            pending[0].fulfill(json={"schemaVersion": "old-invalid-result"})
            page.locator("#open-project-detail-query").click()
            playwright.expect(page.locator("#project-detail-filter")).to_be_enabled()
            assert page.locator(".project-detail-row").count() == 0
            assert page.locator("#project-detail-download").is_disabled()
        finally:
            browser.close()


def test_page_navigation_keeps_snapshot_and_returns_to_second_recording(tmp_path, monkeypatch):
    project, _, _ = create_detail_pool(tmp_path, second_event_count=25)
    before = snapshot(project)
    refuse_sends(monkeypatch)
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(accept_downloads=True)
            errors, replies = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "response",
                lambda response: (
                    replies.append(response.json())
                    if response.url.endswith("/api/match-project-details")
                    else None
                ),
            )
            open_pool(page, base, project)
            page.locator("#open-project-detail-query").click()
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator(".project-detail-row")).to_have_count(20)
            page.locator("#project-detail-next").click()
            playwright.expect(page.locator(".project-detail-row")).to_have_count(6)
            assert page.locator("#project-detail-next").is_disabled()
            assert replies[0]["snapshotId"] == replies[1]["snapshotId"]
            assert replies[1]["offset"] == 20 and replies[1]["totalEvents"] == 26
            assert not {row["eventId"] for row in replies[0]["results"]} & {
                row["eventId"] for row in replies[1]["results"]
            }
            page.locator("#project-detail-previous").click()
            playwright.expect(page.locator(".project-detail-row")).to_have_count(20)
            assert replies[2]["results"] == replies[0]["results"]
            page.locator(".project-detail-row button").nth(1).click()
            playwright.expect(page.locator("#run-select")).to_have_value("run-2")
            playwright.expect(page.locator("#active-title")).to_have_text("时间轴事件")
            assert not errors
        finally:
            browser.close()
    assert snapshot(project) == before
