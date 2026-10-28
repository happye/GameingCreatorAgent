"""Saved report summaries preserve original metrics and asynchronous identity."""

from copy import deepcopy
from urllib.parse import parse_qs, urlparse

import pytest
from test_inspection_http import workspace


def workflow(identifier="one"):
    return {
        "id": identifier,
        "name": identifier,
        "busy": False,
        "qualityGate": None,
        "attempts": [
            {
                "action": action,
                "status": "finished",
                "attemptId": action,
                "startedAt": "fixture",
                "elapsedMs": 0,
                "files": {name: "saved-sha"},
            }
            for action, name in [
                ("ranking", "benchmark-report.json"),
                ("score", "benchmark-fixed-report.json"),
            ]
        ],
    }


def report(gate=None, status="unverified"):
    return {
        "schemaVersion": 1,
        "qualityGate": gate,
        "qualityStatus": status,
        "scoring": {"schemaVersion": "benchmark-fixed-scoring-v1"},
        "mainMacroUsefulRateAt10": None,
        "mainMinimumUsefulRateAt10": None,
        "queries": [
            {
                "queryId": "q1",
                "text": "<script>原查询</script>",
                "kind": "main",
                "status": "unverified_labels",
                "returnedTop10": 3,
                "usefulRateAt10": None,
            },
            {
                "queryId": "q2",
                "text": "失败查询",
                "kind": "sparse",
                "status": "failed",
                "returnedTop10": None,
                "usefulRateAt10": None,
            },
        ],
    }


def routes(page, base, payload, saved):
    page.route(base + "/api/health", lambda route: route.fulfill(json={}))
    page.route(
        base + "/api/benchmark-workflows",
        lambda route: route.fulfill(
            json={
                "workflows": [
                    {"id": key, "name": key, "createdAt": "fixture"} for key in ["one", "two"]
                ]
            }
        ),
    )
    page.route(
        base + "/api/benchmark-workflow?*",
        lambda route: route.fulfill(
            json={
                **payload,
                "id": parse_qs(urlparse(route.request.url).query)["workflow"][0],
                "name": parse_qs(urlparse(route.request.url).query)["workflow"][0],
            }
        ),
    )
    page.route(base + "/api/benchmark-file?*", lambda route: route.fulfill(json=saved))


@pytest.mark.parametrize("width", [1366, 390])
@pytest.mark.parametrize(
    "gate,status,label",
    [(True, "passed", "通过"), (False, "failed", "未通过"), (None, "unverified", "未验证")],
)
def test_saved_summaries_preserve_null_failure_order_and_links(
    tmp_path, width, gate, status, label
):
    pw = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            saved = report(gate, status)
            saved["queries"][0]["usefulRateAt10"] = 0.7
            routes(page, base, workflow(), saved)
            page.goto(base + "/acceptance#one")
            ranking = page.locator("[data-step=ranking] .result-summary")
            score = page.locator("[data-step=score] .result-summary")
            pw.expect(ranking).to_contain_text("原十位排名已保存")
            pw.expect(score).to_contain_text(f"本报告质量状态：{label}")
            assert "门槛" not in ranking.inner_text()
            assert ranking.locator("summary").all_text_contents() == [
                "q1 · <script>原查询</script> · 主查询",
                "q2 · 失败查询 · 少例查询",
            ]
            for item in score.locator("details").all():
                item.locator("summary").click()
            assert "原报告可用率：70%" in score.inner_text()
            assert "原报告可用率：尚未验证" in score.inner_text()
            assert "返回槽位：返回数量未知；查询失败" in score.inner_text()
            assert score.locator("script").count() == 0
            assert (
                page.locator('[data-step=score] a[download="benchmark-fixed-report.json"]').count()
                == 1
            )
            assert page.locator("[data-step=review] .result-summary").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize("bad", ["schema", "scoring", "missing", "http", "unregistered"])
def test_unreadable_report_keeps_original_links(tmp_path, bad):
    pw = pytest.importorskip("playwright.sync_api")
    saved = report()
    if bad == "schema":
        saved["schemaVersion"] = "benchmark-fixed-score-result-v1"
    if bad == "scoring":
        saved["scoring"]["schemaVersion"] = "wrong"
    if bad == "missing":
        del saved["mainMacroUsefulRateAt10"]
    with workspace(tmp_path) as base, pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            payload = workflow()
            if bad == "unregistered":
                payload["attempts"][1]["files"] = {}
            routes(page, base, payload, saved)
            if bad == "http":
                page.route(
                    base + "/api/benchmark-file?*",
                    lambda route: route.fulfill(status=404, json={"message": "missing"}),
                )
            page.goto(base + "/acceptance#one")
            pw.expect(page.locator("[data-step=score] .result-summary")).to_contain_text(
                "结果摘要暂不可读"
            )
            assert page.locator(
                '[data-step=score] a[download="benchmark-fixed-report.json"]'
            ).count() == (0 if bad == "unregistered" else 1)
        finally:
            browser.close()


@pytest.mark.parametrize("switch", [False, True])
def test_late_response_cannot_fill_repainted_or_other_workflow(tmp_path, switch):
    pw = pytest.importorskip("playwright.sync_api")
    with workspace(tmp_path) as base, pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            routes(page, base, workflow(), report())
            pending = []
            page.route(base + "/api/benchmark-file?*", lambda route: pending.append(route))
            page.goto(base + "/acceptance#one")
            pw.expect(page.locator(".result-summary")).to_have_count(2)
            page.wait_for_function(
                "() => document.querySelector('#status').textContent.includes('已读取')"
            )
            old = page.locator("[data-step=score] .result-summary").element_handle()
            if switch:
                page.locator("#workflow-select").select_option("two")
                pw.expect(page.locator("#current-name")).to_have_text("two")
            else:
                page.locator("#refresh").click()
                page.wait_for_function("old => !old.isConnected", arg=old)
            page.wait_for_function("old => !old.isConnected", arg=old)
            assert len(pending) >= 2
            stale = deepcopy(report(True, "passed"))
            for route in pending[:2]:
                route.fulfill(json=stale)
            page.wait_for_timeout(150)
            assert old.inner_text() == "正在读取已保存的结果摘要…"
            assert "本报告质量状态：通过" not in page.locator("#steps").inner_text()
        finally:
            browser.close()
