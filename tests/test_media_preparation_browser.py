"""Prepare, detach, stop, resume and open the actual local task list through the page."""

import asyncio
import json
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_media_batch import batch, task_snapshot  # noqa: F401 - fixtures
from test_media_preparation_jobs import preparation  # noqa: F401 - fixture


def fill_prepare(page, document):
    page.locator("#open-preparation").click()
    page.locator("#preparation-project").fill(document["project"])
    page.locator("#preparation-paths").fill("\n".join(f'"{path}"' for path in document["paths"]))
    page.locator("#preparation-profile").select_option("frames")
    page.locator("#preparation-budget").fill("1.75")


def test_switch_project_during_catalog_read_can_explicitly_refresh_again(preparation):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    jobs, document, media = preparation
    with workspace(jobs.repository) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            held = []

            def delay_first_catalog(route):
                if not held:
                    held.append(route)
                else:
                    route.continue_()

            page.route("**/api/media-batches?**", delay_first_catalog)
            page.goto(base)
            page.locator("#open-preparation").click()
            playwright.expect(page.locator("#refresh-preparation")).to_be_disabled()
            page.locator("#preparation-project").fill(document["project"])
            playwright.expect(page.locator("#refresh-preparation")).to_be_enabled()
            page.locator("#refresh-preparation").click()
            playwright.expect(page.locator("#preparation-history-summary")).to_have_text(
                "此项目还没有准备批次。"
            )
            playwright.expect(page.locator("#refresh-preparation")).to_be_enabled()
            assert media.probes == media.extractions == []
        finally:
            browser.close()


def test_preparation_entry_stays_hidden_with_previous_running_service(preparation):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    jobs, _, media = preparation
    with workspace(jobs.repository) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()

            def previous_health(route):
                response = route.fetch()
                health = response.json()
                health.pop("capabilities")
                route.fulfill(response=response, json=health)

            page.route("**/api/health", previous_health)
            with page.expect_response("**/api/health"):
                page.goto(base)
            playwright.expect(page.locator("#open-preparation")).to_be_hidden()
            playwright.expect(page.locator("#project-select")).to_be_visible()
            assert media.probes == media.extractions == []
        finally:
            browser.close()


@pytest.mark.parametrize(
    "viewport", [{"width": 1366, "height": 768}, {"width": 390, "height": 844}]
)
def test_prepare_browser_three_materials_download_and_open_waiting_tasks(preparation, viewport):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    jobs, document, media = preparation
    media.probe_delay = 0.1
    with workspace(jobs.repository) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport=viewport)
            errors = []
            requests = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request))
            page.goto(base)
            fill_prepare(page, document)
            assert page.locator("#preparation-dialog").evaluate(
                "dialog => dialog.scrollWidth <= dialog.clientWidth"
            )
            page.locator("#start-preparation").click()
            playwright.expect(page.locator(".preparation-item.prepared")).to_have_count(
                3, timeout=10000
            )
            playwright.expect(page.locator("#download-preparation")).to_be_enabled()
            playwright.expect(page.locator("#preparation-status")).to_have_text("本批次检查已完成")
            playwright.expect(page.locator("#preparation-summary")).to_contain_text("已准备 3 段")
            with page.expect_download() as info:
                page.locator("#download-preparation").click()
            result = json.loads(Path(info.value.path()).read_bytes())
            assert result["schemaVersion"] == "media-batch-result-v1"
            assert result["modelInvocations"] == result["newReservations"] == 0
            assert (
                len(
                    [
                        request
                        for request in requests
                        if request.url.endswith("/api/prepare-media-batch")
                    ]
                )
                == 1
            )
            page.locator("#open-prepared-tasks").click()
            playwright.expect(page.locator(".task-card")).to_have_count(3)
            assert all(
                "素材已保存，等待分析" in text
                for text in page.locator(".task-card").all_text_contents()
            )
            playwright.expect(page.locator("#search-button")).to_be_disabled()
            assert not errors
            assert not any("/api/search-project" in request.url for request in requests)
        finally:
            browser.close()
    snapshots = asyncio.run(task_snapshot(jobs.repository / document["project"], result["items"]))
    assert all(
        str(run.configuration.max_cost_cny) == "1.75" and not calls for run, _, calls in snapshots
    )


def test_browser_page_reload_recovers_live_job_then_explicit_stop_and_same_batch_resume(
    preparation,  # noqa: F811
):
    playwright = pytest.importorskip("playwright.sync_api")
    jobs, document, media = preparation
    media.probe_delay = 1
    with workspace(jobs.repository) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            requests = []
            page.on("request", lambda request: requests.append(request))
            page.goto(base)
            fill_prepare(page, document)
            page.locator("#start-preparation").click()
            playwright.expect(page.locator("#stop-preparation")).to_be_enabled()
            page.reload()
            page.locator("#open-preparation").click()
            playwright.expect(page.locator("#preparation-project")).to_have_value(
                document["project"]
            )
            playwright.expect(page.locator("#stop-preparation")).to_be_enabled()
            playwright.expect(page.locator(".preparation-item.prepared").first).to_be_visible(
                timeout=10000
            )
            page.locator("#stop-preparation").click()
            playwright.expect(page.locator("#preparation-status")).to_have_text(
                "本次准备已停止", timeout=10000
            )
            playwright.expect(page.locator(".preparation-batch")).to_have_count(1)
            original = page.locator(".preparation-item").evaluate_all(
                "rows => rows.map(row => row.dataset.run)"
            )
            media.probe_delay = 0
            page.locator("#preparation-budget").fill("999")
            page.locator(".preparation-batch button").click()
            playwright.expect(page.locator(".preparation-item.prepared")).to_have_count(
                3, timeout=10000
            )
            playwright.expect(page.locator("#download-preparation")).to_be_enabled()
            assert (
                page.locator(".preparation-item").evaluate_all(
                    "rows => rows.map(row => row.dataset.run)"
                )
                == original
            )
            starts = [
                request.post_data_json
                for request in requests
                if request.url.endswith("/api/prepare-media-batch")
            ]
            assert len(starts) == 2
            assert set(starts[1]) == {"project", "resume", "timeoutSeconds"}
            with page.expect_download() as info:
                page.locator("#download-preparation").click()
            result = json.loads(Path(info.value.path()).read_bytes())
        finally:
            browser.close()
    snapshots = asyncio.run(task_snapshot(jobs.repository / document["project"], result["items"]))
    assert all(
        str(run.configuration.max_cost_cny) == "1.75" and not calls for run, _, calls in snapshots
    )


def test_browser_saved_batch_is_explicit_and_bad_video_does_not_stop_the_rest(preparation):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    jobs, document, media = preparation
    bad = list(media.bundles)[1]
    media.bad.add(bad)
    with workspace(jobs.repository) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            requests = []
            page.on("request", lambda request: requests.append(request))
            page.goto(base)
            fill_prepare(page, document)
            page.locator("#start-preparation").click()
            playwright.expect(page.locator("#preparation-status")).to_have_text(
                "部分素材尚未准备好", timeout=10000
            )
            playwright.expect(page.locator(".preparation-item.prepared")).to_have_count(2)
            playwright.expect(page.locator(".preparation-item.failed")).to_have_count(1)
            playwright.expect(page.locator(".preparation-batch")).to_have_count(1)
            page.locator("#close-preparation").click()
            page.reload()
            page.locator("#open-preparation").click()
            playwright.expect(page.locator(".preparation-batch")).to_have_count(1)
            playwright.expect(page.locator("#preparation-status")).to_have_text("尚未开始新批次")
            assert (
                len(
                    [
                        request
                        for request in requests
                        if request.url.endswith("/api/prepare-media-batch")
                    ]
                )
                == 1
            )
            media.bad.clear()
            page.locator(".preparation-batch button").click()
            playwright.expect(page.locator(".preparation-item.prepared")).to_have_count(
                3, timeout=10000
            )
            assert (
                len(
                    [
                        request
                        for request in requests
                        if request.url.endswith("/api/prepare-media-batch")
                    ]
                )
                == 2
            )
        finally:
            browser.close()
