"""A new frontend cannot select v5 against a backend without that capability."""

import json

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query import snapshot
from test_inspection_http import workspace


def test_older_backend_keeps_v5_disabled_and_existing_profiles_available(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, _ = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def legacy_health(route):
                response = route.fetch()
                body = response.json()
                body["capabilities"].remove("detail-temporal-json-v1")
                route.fulfill(
                    response=response, content_type="application/json", body=json.dumps(body)
                )

            page.route("**/api/health", legacy_health)
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            playwright.expect(page.locator("#detail-profile")).to_be_enabled()
            assert page.locator('#detail-profile option[value="v5"]').evaluate(
                "option=>option.disabled"
            )
            page.locator("#detail-profile").select_option("v4")
            playwright.expect(page.locator("#detail-profile")).to_have_value("v4")
            assert not errors
        finally:
            browser.close()
    assert snapshot(project) == before
