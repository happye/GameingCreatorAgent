"""Source/query form workflows with explicit unknowns and no source reads."""

import json
from pathlib import Path

import pytest

from gamingcreator.application.benchmark_plan_draft import decode_draft, draft_to_plan, empty_draft
from gamingcreator.application.benchmark_preparation import loads_plan
from gamingcreator.ui.benchmark_plan_editor import render_plan_editor


@pytest.mark.parametrize("width", [1366, 390])
def test_plan_form_unknown_save_reload_binding_protection_and_existing_plan_export(tmp_path, width):
    playwright = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "登记 中文.html"
    path.write_text(render_plan_editor(empty_draft()), encoding="utf-8")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900}, accept_downloads=True)
            foreign, errors = [], []
            page.on(
                "request",
                lambda request: (
                    foreign.append(request.url)
                    if not request.url.startswith(("file:", "data:", "blob:"))
                    else None
                ),
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(path.as_uri())

            def download(selector):
                with page.expect_download() as pending:
                    page.locator(selector).click()
                return Path(pending.value.path()).read_bytes()

            assert decode_draft(download("#save-draft")) == empty_draft()
            page.locator("#dataset-id").fill("程序表单示例，不是真实人评")
            for index in range(2):
                page.locator("#add-source").click()
                row = page.locator(".source-row").nth(index)
                row.locator("[data-field='path']").fill(f"G:/fixture/录像 {index}.mp4")
                row.locator("[data-field='partition']").select_option("development")
                if index:
                    row.locator("[data-field='modelResultsViewed']").select_option("yes")
                page.locator("#add-query").click()
                query = page.locator(".query-row").nth(index)
                query.locator("[data-field='text']").fill(f"事前需求{index}")
                query.locator("[data-field='family']").fill(f"需求归组{index}")
                query.locator("[data-field='kind']").select_option(
                    "main" if index == 0 else "negative"
                )
                query.locator("[data-field='sourceId']").select_option(f"source-{index + 1}")
            partial = download("#save-draft")
            assert decode_draft(partial)["sources"][0]["modelResultsViewed"] is None
            page.locator("#export-plan").click()
            playwright.expect(page.locator("#status")).to_contain_text("明确选择")
            source = page.locator(".source-row").first
            source.locator("[data-field='modelResultsViewed']").select_option("no")
            source.locator("[data-field='id']").fill("clip-1")
            playwright.expect(
                page.locator(".query-row").first.locator("[data-field='sourceId']")
            ).to_have_value("clip-1")
            source.locator("button").click()
            playwright.expect(page.locator("#status")).to_contain_text("还有关联查询")
            playwright.expect(page.locator(".source-row")).to_have_count(2)
            complete = download("#save-draft")
            plan_data = download("#export-plan")
            plan = loads_plan(plan_data.decode())
            assert plan.document == draft_to_plan(decode_draft(complete)).document
            assert plan.document["humanReferences"]["confirmed"] is False
            assert all(not query["referenceEvents"] for query in plan.document["queries"])
            page.locator("#load-draft").set_input_files(
                {"name": "partial.json", "mimeType": "application/json", "buffer": partial}
            )
            playwright.expect(page.locator("#status")).to_contain_text("草稿已载入")
            playwright.expect(
                page.locator(".source-row").first.locator("[data-field='modelResultsViewed']")
            ).to_have_value("")
            page.locator("#load-draft").set_input_files(
                {"name": "complete.json", "mimeType": "application/json", "buffer": complete}
            )
            playwright.expect(
                page.locator(".source-row").first.locator("[data-field='id']")
            ).to_have_value("clip-1")
            invalid = b'{"datasetId":"a","datasetId":"b","sources":[],"queries":[],"schemaVersion":"benchmark-plan-draft-v1"}'
            page.locator("#load-draft").set_input_files(
                {"name": "duplicate.json", "mimeType": "application/json", "buffer": invalid}
            )
            playwright.expect(page.locator("#status")).to_contain_text("重复字段")
            playwright.expect(page.locator(".source-row")).to_have_count(2)
            page.evaluate("""() => {
                const original = File.prototype.text;
                File.prototype.text = function() {
                    if (this.name !== 'late.json') return original.call(this);
                    return new Promise(resolve => { window.finishPlanLoad = () => original.call(this).then(resolve); });
                };
            }""")
            page.locator("#load-draft").set_input_files(
                {"name": "late.json", "mimeType": "application/json", "buffer": complete}
            )
            page.locator("#dataset-id").fill("保留当前新编辑")
            page.evaluate("() => window.finishPlanLoad()")
            playwright.expect(page.locator("#status")).to_contain_text("保留当前编辑")
            playwright.expect(page.locator("#dataset-id")).to_have_value("保留当前新编辑")
            assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
            assert not foreign and not errors
            assert json.loads(plan_data)["labelVersion"] is None
        finally:
            browser.close()
