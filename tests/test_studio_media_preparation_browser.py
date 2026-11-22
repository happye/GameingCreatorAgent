"""A new Studio project prepares real tasks and resumes only on a user action."""

import pytest
from test_inspection_http import workspace
from test_media_batch import batch  # noqa: F401
from test_media_preparation_jobs import preparation  # noqa: F401

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser


def check_late_startup_cannot_override_import(page, open_dialog, dialog, project_select, project):
    held = []

    def delay_first(route):
        if held:
            route.continue_()
        else:
            held.append(route)

    page.evaluate("localStorage.removeItem('studio-v1')")
    page.route("**/api/projects", delay_first)
    page.reload(wait_until="domcontentloaded")
    open_dialog.click()
    dialog.get_by_role("button", name="打开准备项目").click()
    playwright.expect(project_select).to_have_value(project)
    assert len(held) == 1
    held[0].fulfill(json={"projects": [{"path": "artifacts/other", "name": "Other"}]})
    page.evaluate(
        "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    playwright.expect(project_select).to_have_value(project)


def test_studio_import_remembers_and_explicitly_resumes_nested_project(preparation):  # noqa: F811
    jobs, document, media = preparation
    project = "./artifacts/series/recordings"
    bad = list(media.bundles)[1]
    media.bad.add(bad)
    with workspace(jobs.repository) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 950})
            errors, posts = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def allow_local_preparation(route):
                if route.request.method == "POST":
                    posts.append(route.request.post_data_json)
                    if route.request.url != f"{base}/api/prepare-media-batch":
                        route.abort()
                        return
                route.continue_()

            page.route("**/api/**", allow_local_preparation)
            page.goto(f"{base}/studio")
            open_dialog = page.get_by_role("button", name="导入录像", exact=True).first
            dialog = page.get_by_role("dialog", name="导入录像")
            open_dialog.click()
            dialog.get_by_label("准备项目").fill(project)
            dialog.get_by_label("录像路径（每行一段）").fill("\n".join(document["paths"]))
            dialog.get_by_label("准备方案").select_option("frames")
            dialog.get_by_label("以后每段分析上限（元）").fill("1.25")
            dialog.get_by_role("button", name="开始本地准备").click()

            batch = dialog.locator("[data-batch]")
            playwright.expect(batch).to_contain_text("部分准备完成", timeout=15000)
            original = batch.locator("[data-run]").evaluate_all(
                "rows => rows.map(r => r.dataset.run)"
            )
            assert len(original) == 3 and len(posts) == 1
            batch_id = batch.get_attribute("data-batch")
            dialog.get_by_role("button", name="关闭", exact=True).click()
            page.reload()
            open_dialog.click()
            playwright.expect(dialog.get_by_label("准备项目")).to_have_value(project)
            playwright.expect(batch).to_have_attribute("data-batch", batch_id)
            assert len(posts) == 1

            media.bad.remove(bad)
            batch.get_by_role("button", name="继续本地准备").click()
            playwright.expect(batch.locator('[data-preparation-state="prepared"]')).to_have_count(
                3, timeout=15000
            )
            assert original == batch.locator("[data-run]").evaluate_all(
                "rows => rows.map(r => r.dataset.run)"
            )
            assert posts[1] == {"project": project, "resume": batch_id, "timeoutSeconds": 3600}
            dialog.get_by_role("button", name="打开准备项目").click()
            playable_project = page.get_by_label("项目", exact=True)
            playwright.expect(playable_project).to_have_value(project)
            playwright.expect(
                page.get_by_text("这个项目还没有分析完成的录像。", exact=True)
            ).to_be_visible()
            page.reload()
            playwright.expect(playable_project).to_have_value(project)
            check_late_startup_cannot_override_import(
                page, open_dialog, dialog, playable_project, project
            )
            assert len(posts) == 2 and not errors, (posts, errors)
        finally:
            browser.close()
