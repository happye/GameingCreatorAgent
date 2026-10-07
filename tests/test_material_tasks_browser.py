"""Browse saved materials and open a task; no analysis or retrieval is dispatched."""

import json

import pytest
from test_detail_inspection import refuse_sends
from test_detail_query import snapshot
from test_inspection_http import workspace
from test_material_tasks import seed_tasks
from test_material_tasks_http import unknown_attempt


@pytest.mark.parametrize(
    "viewport", [{"width": 1366, "height": 768}, {"width": 390, "height": 844}]
)
def test_browser_tasks_page_and_open_pending_task_without_writing(tmp_path, monkeypatch, viewport):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = seed_tasks(tmp_path / "artifacts", 25)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport=viewport)
            requests = []
            page.on("request", lambda request: requests.append(request.url))
            page.goto(base)
            playwright.expect(page.locator("#run-select")).to_be_enabled()
            page.locator("#open-tasks").click()
            playwright.expect(page.locator(".task-card")).to_have_count(20)
            playwright.expect(page.locator("#tasks-page-summary")).to_have_text("1–20 / 25 个任务")
            playwright.expect(page.locator("#tasks-previous")).to_be_disabled()
            assert page.locator(".task-card").first.inner_text().find("素材已保存，等待分析") >= 0
            assert page.evaluate(
                "document.getElementById('tasks-dialog').scrollWidth <= document.getElementById('tasks-dialog').clientWidth"
            )
            page.locator("#tasks-next").click()
            playwright.expect(page.locator(".task-card")).to_have_count(5)
            playwright.expect(page.locator("#tasks-page-summary")).to_have_text("21–25 / 25 个任务")
            playwright.expect(page.locator("#tasks-next")).to_be_disabled()
            page.locator("#tasks-previous").click()
            playwright.expect(page.locator(".task-card")).to_have_count(20)
            page.locator("#tasks-next").click()
            playwright.expect(page.locator(".task-card")).to_have_count(5)
            target = page.locator(".task-card").first.locator(".task-id").inner_text().split()[-1]
            page.locator(".task-card").first.get_by_role("button", name="打开此任务").click()
            playwright.expect(page.locator("#tasks-dialog")).not_to_be_visible()
            playwright.expect(page.locator("#run-select")).to_have_value(target)
            playwright.expect(page.locator("#run-state")).to_contain_text("等待分析")
            playwright.expect(page.locator("#search-button")).to_be_disabled()
            assert not any(
                "query=" in url and "query=&" not in url and not url.endswith("query=")
                for url in requests
                if "/api/inspect?" in url
            )
        finally:
            browser.close()
    assert snapshot(project) == before


def test_browser_unknown_fee_is_visible_and_task_names_are_plain_text(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    unknown_attempt(project)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()

            def markup(route):
                response = route.fetch()
                payload = response.json()
                payload["tasks"][0]["sourceName"] = '<img src=x onerror="window.taskInjected=true">'
                route.fulfill(response=response, json=payload)

            page.route("**/api/tasks?**", markup)
            page.goto(base)
            playwright.expect(page.locator("#run-select")).to_be_enabled()
            page.locator("#open-tasks").click()
            playwright.expect(page.locator(".task-card")).to_have_count(1)
            playwright.expect(page.locator(".task-card")).to_contain_text("未知预留 ¥2")
            playwright.expect(page.locator(".task-card")).to_contain_text("需明确选择重试")
            assert page.locator("#tasks-list img").count() == 0
            assert page.evaluate("window.taskInjected === undefined")
        finally:
            browser.close()
    assert snapshot(project) == before


@pytest.mark.parametrize("wrong_source", [False, True])
def test_browser_task_failure_or_wrong_project_is_unread_not_empty(
    tmp_path, monkeypatch, wrong_source
):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_tasks(tmp_path / "artifacts", 1)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()

            def failed(route):
                if wrong_source:
                    response = route.fetch()
                    payload = response.json()
                    payload["project"] = "another-project"
                    route.fulfill(response=response, json=payload)
                else:
                    route.fulfill(
                        status=409,
                        content_type="application/json",
                        body=json.dumps({"message": "已保存记录读取失败。"}),
                    )

            page.route("**/api/tasks?**", failed)
            page.goto(base)
            playwright.expect(page.locator("#run-select")).to_be_enabled()
            page.locator("#open-tasks").click()
            playwright.expect(page.locator("#tasks-page-summary")).to_have_text(
                "未读取，不能据此判断没有任务。"
            )
            assert page.locator(".task-card").count() == 0
            playwright.expect(page.locator("#tasks-next")).to_be_disabled()
        finally:
            browser.close()


@pytest.mark.parametrize("change", ["close", "project"])
def test_browser_late_task_page_cannot_replace_reopened_or_other_project(
    tmp_path, monkeypatch, change
):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    other_project, _ = seed_tasks(tmp_path / "other" / "artifacts", 2)
    refuse_sends(monkeypatch)
    before = snapshot(project), snapshot(other_project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.add_init_script("""
                const realTaskFetch = window.fetch.bind(window);
                window.holdTaskReply = true;
                window.fetch = async (...arguments_) => {
                    const reply = await realTaskFetch(...arguments_);
                    if (!String(arguments_[0]).includes('/api/tasks?') || !window.holdTaskReply) return reply;
                    const payload = await reply.clone().json();
                    payload.tasks[0].sourceName = '迟到旧任务';
                    const deferred = await new Promise(resolve => {
                        window.deliverOldTask = () => resolve(new Response(JSON.stringify(payload), {status:200, headers:{'Content-Type':'application/json'}}));
                    });
                    window.oldTaskReturned = true;
                    return deferred;
                };
            """)
            page.goto(base)
            playwright.expect(page.locator("#run-select")).to_be_enabled()
            page.locator("#open-tasks").click()
            page.wait_for_function("() => typeof window.deliverOldTask === 'function'")
            page.locator("#close-tasks").click()
            page.evaluate("window.holdTaskReply = false")
            if change == "project":
                page.locator(".manual-project summary").click()
                page.locator("#project-path").fill(str(other_project))
                page.locator("#project-form").evaluate("node => node.requestSubmit()")
                playwright.expect(page.locator("#run-select option")).to_have_count(2)
                playwright.expect(page.locator("#run-select")).to_be_enabled()
            page.locator("#open-tasks").click()
            playwright.expect(page.locator(".task-card")).to_have_count(
                2 if change == "project" else 1
            )
            page.evaluate("window.deliverOldTask()")
            page.wait_for_function("() => window.oldTaskReturned === true")
            playwright.expect(page.locator("#tasks-list")).not_to_contain_text("迟到旧任务")
            playwright.expect(page.locator(".task-card")).to_have_count(
                2 if change == "project" else 1
            )
        finally:
            browser.close()
    assert (snapshot(project), snapshot(other_project)) == before
