"""Explicit selection and saved choices through the actual HTTP binding path."""

import json
from urllib.parse import urlencode

import pytest
from test_benchmark_run_selection import selection_workflow  # noqa: F401 - shared fixture
from test_inspection_http import workspace


@pytest.mark.parametrize("width", [1366, 390])
def test_explicit_choices_submit_original_mapping_and_restore(tmp_path, request, width):
    manager, identifier, project, _ = request.getfixturevalue("selection_workflow")
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors, posts, foreign = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: (
                    posts.append(item.post_data_json)
                    if item.url.endswith("/api/benchmark-step")
                    else None
                ),
            )
            page.on(
                "request",
                lambda item: (
                    foreign.append(item.url)
                    if not item.url.startswith((base, "blob:", "data:"))
                    else None
                ),
            )
            page.goto(base + "/acceptance#" + identifier)
            bind = page.locator("[data-step=bind]")
            page.locator("#bind-project").fill(str(project))
            page.locator("#bind-partition").select_option("test")
            page.locator("#read-bind-options").click()
            playwright.expect(page.locator(".run-pick")).to_have_count(1)
            choice = page.locator(".run-pick")
            assert choice.input_value() == ""
            assert choice.locator("option").count() == 4
            assert choice.locator("option[value=run-pending]").evaluate("option => option.disabled")
            assert "second-fixture" in choice.inner_text()
            bind.locator("button[type=submit]").click()
            playwright.expect(page.locator("#status")).to_contain_text("明确选择每段录像")
            assert posts == []
            choice.select_option("run-2")
            bind.locator("button[type=submit]").click()
            playwright.expect(bind.locator(".state").first).to_have_text(
                "资料已保存", timeout=15000
            )
            assert len(posts) == 1 and posts[0]["action"] == "bind"
            fields = posts[0]["fields"]
            assert json.loads(fields["inputText"]) == {"source-0": "run-2"}
            freeze = next(
                row for row in manager.get(identifier)["attempts"] if row["action"] == "freeze"
            )
            assert fields["freezeSha256"] == freeze["files"]["freeze.json"]
            page.reload()
            playwright.expect(page.locator("#bind-project")).to_have_value(str(project))
            assert page.locator("#bind-partition").input_value() == ""
            page.locator("#bind-partition").select_option("test")
            page.locator("#read-bind-options").click()
            playwright.expect(page.locator(".run-pick")).to_have_value("run-2")
            playwright.expect(page.locator("#bind-options-status")).to_contain_text(
                "已恢复上次明确选择"
            )
            page.locator("#bind-partition").select_option("development")
            assert page.locator(".run-pick").count() == 0
            bind.locator("button[type=submit]").click()
            playwright.expect(page.locator("#status")).to_contain_text("先读取当前来源")
            assert len(posts) == 1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors and not foreign
        finally:
            browser.close()


def test_late_choices_cannot_cross_workflows_and_capability_keeps_legacy_form(tmp_path, request):
    manager, identifier, project, _ = request.getfixturevalue("selection_workflow")
    playwright = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            frozen = next(
                row for row in manager.get(identifier)["attempts"] if row["action"] == "freeze"
            )
            pending = []
            page.route("**/api/benchmark-bind-options?*", lambda route: pending.append(route))
            page.goto(base + "/acceptance#" + identifier)
            page.locator("#bind-project").fill(str(project))
            page.locator("#bind-partition").select_option("test")
            with page.expect_request("**/api/benchmark-bind-options?*"):
                page.locator("#read-bind-options").click()
            other = page.request.post(
                base + "/api/benchmark-workflows", data={"name": "其他流程"}
            ).json()
            page.locator("#refresh").click()
            playwright.expect(page.locator("#workflow-select option")).to_have_count(3)
            page.locator("#workflow-select").select_option(other["id"])
            playwright.expect(page.locator("#current-name")).to_have_text("其他流程")
            pending[0].fulfill(
                json={
                    "schemaVersion": "benchmark-bind-options-v1",
                    "workflow": identifier,
                    "project": str(project),
                    "partition": "test",
                    "freezeAttempt": frozen["attemptId"],
                    "freezeSha256": frozen["files"]["freeze.json"],
                    "sources": [],
                    "previousSelection": {},
                }
            )
            assert page.locator(".run-pick").count() == 0
            assert page.locator("[data-step=bind] button[type=submit]").is_disabled()
            page.unroute("**/api/benchmark-bind-options?*")
            page.route(
                "**/api/health",
                lambda route: route.fulfill(json={"capabilities": ["benchmark-workflow-v1"]}),
            )
            page.goto(base + "/acceptance#" + identifier)
            page.reload()  # A hash-only navigation retains the previous document/capabilities.
            playwright.expect(page.locator("#current-name")).to_contain_text("程序选择夹具")
            assert page.locator("#read-bind-options").count() == 0
            page.locator("[data-step=bind] button[type=submit]").click()
            playwright.expect(page.locator("#status")).to_contain_text("先选择本步骤所需的JSON文件")
            query = urlencode({"workflow": identifier})
            assert (
                page.request.get(base + "/api/benchmark-workflow?" + query).json()["qualityGate"]
                is None
            )
        finally:
            browser.close()
