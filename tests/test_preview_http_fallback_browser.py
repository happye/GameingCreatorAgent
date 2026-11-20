"""B07: 代理 HTTP 失败时退回原片一次，恢复源位置，不反复重载、不改剪辑区间。"""
# ruff: noqa: F811

from __future__ import annotations

import json
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest
from test_benchmark_source_clock_browser import probe_source, synthesize
from test_creation_jobs import finish, service  # noqa: F401
from test_detail_inspection import refuse_sends
from test_inspection_http import workspace
from test_preview_clock_align_browser import plant_playable_proxy, seed_playable_project
from test_studio_audio_graph_browser import saved_plan

from gamingcreator.application.browser_source_clock import build_source_clock, clock_document
from gamingcreator.ui import server

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def media_query(page, selector="#source-video"):
    src = page.locator(selector).get_attribute("src") or ""
    return {key: values[0] for key, values in parse_qs(urlparse(src).query).items()}


def block_proxy(page):
    hits = {"proxy": 0}

    def handle(route):
        if "proxy=1" in route.request.url:
            hits["proxy"] += 1
            route.fulfill(status=404, body=b"missing", headers={"Content-Type": "text/plain"})
        else:
            route.continue_()

    page.route("**/api/media**", handle)
    return hits


def test_workbench_proxy_http_failure_falls_back_once_and_keeps_source_moment(
    tmp_path, monkeypatch
):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    official = clock_document(build_source_clock(bundle.asset))
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            hits = block_proxy(page)
            page.goto(base)
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("[data-preview-clock-reason]")).to_have_attribute(
                "data-preview-clock-reason", "proxy_http_failed", timeout=20000
            )
            expect(page.locator("#preview-clock-reason")).to_have_text("代理无法加载，已改用原片")
            assert "proxy" not in media_query(page)
            page.wait_for_function(
                "() => document.getElementById('source-video')?.readyState >= 1",
                timeout=20000,
            )
            first = hits["proxy"]
            assert first > 0
            page.evaluate(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    v.currentTime = SourceClock.sourceUsToPlayerSeconds(clock, 500000);
                }""",
                official,
            )
            page.wait_for_function(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    const us = SourceClock.playerToSourceUs(clock, v.currentTime);
                    return us !== null && Math.abs(us - 500000) <= 80000;
                }""",
                arg=official,
                timeout=10000,
            )
            page.locator("#proxy-toggle-input").check()
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("[data-preview-clock-reason]")).to_have_attribute(
                "data-preview-clock-reason", "proxy_http_failed"
            )
            assert "proxy" not in media_query(page)
            page.wait_for_function(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    const us = SourceClock.playerToSourceUs(clock, v.currentTime);
                    return us !== null && Math.abs(us - 500000) <= 80000;
                }""",
                arg=official,
                timeout=20000,
            )
            time.sleep(1.5)
            second = hits["proxy"]
            time.sleep(1.5)
            assert hits["proxy"] == second, "proxy was requested again after fallback settled"
            assert second >= first
            assert not errors, errors
        finally:
            browser.close()


def test_studio_asset_proxy_http_failure_falls_back_once(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            hits = block_proxy(page)
            page.add_init_script(
                "localStorage.setItem('studio-v1', JSON.stringify({project:'artifacts/project', workspace:'assets'}));"
            )
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("[data-preview-clock-reason]")).to_have_attribute(
                "data-preview-clock-reason", "proxy_http_failed", timeout=20000
            )
            expect(page.locator("[data-preview-clock-reason]")).to_have_text(
                "代理无法加载，已改用原片"
            )
            assert "proxy" not in media_query(page, ".viewer video")
            first = hits["proxy"]
            assert first > 0
            time.sleep(1.5)
            second = hits["proxy"]
            time.sleep(1.5)
            assert hits["proxy"] == second, "proxy was requested again after fallback settled"
            assert not errors, errors
        finally:
            browser.close()


def test_plan_proxy_http_failure_falls_back_without_changing_clips(service, monkeypatch, tmp_path):  # noqa: ARG001
    playwright = pytest.importorskip("playwright.sync_api")
    root_job, _track, asset = saved_plan(service, monkeypatch)
    preview = tmp_path / "preview-proxy.mp4"
    synthesize(preview, "zero")
    official = clock_document(build_source_clock(probe_source(preview)))
    plant_playable_proxy(service.repository, preview, asset.sha256, official["durationUs"])
    edit = service.edit(root_job, "hook-first")
    rows = [
        {
            **{key: row[key] for key in ("clipId", "startUs", "endUs")},
            "speed": {"numerator": 1, "denominator": 1},
        }
        for row in edit["clips"][:2]
    ]
    rows[0]["transitionIn"] = {"type": "cut", "frames": 0}
    rows[1]["transitionIn"] = {"type": "crossfade", "frames": 30}
    revision = service.submit(
        "revision",
        dict(
            requestId="e" * 32,
            parentJobId=root_job,
            planId="hook-first",
            expectedParentReceiptSha256=edit["expectedParentReceiptSha256"],
            clips=rows,
        ),
    )["jobId"]
    completed = finish(service, revision)
    assert completed["status"] == "completed", completed
    video = "/api/media?project=artifacts/project&run=run"
    posted = []

    async def runs(_project, *args, **kwargs):
        return {
            "runs": [
                {
                    "id": "run",
                    "sourceName": "tone.mp4",
                    "status": "completed",
                    "completedEligible": True,
                    "sourceClock": official,
                    "videoUrl": video,
                    "proxyUrl": video + "&proxy=1",
                    "mediaId": asset.media_id if hasattr(asset, "media_id") else "media-run",
                }
            ]
        }

    monkeypatch.setattr(server, "project_runs_payload", runs)
    http = server.create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps({"artifacts/project": {"id": revision, "kind": "revision"}})
            page.add_init_script(
                f"if(!localStorage.getItem('studio-v1'))localStorage.setItem('studio-v1',{prefs!r});"
                f"if(!localStorage.getItem('studio-last-job-v1'))localStorage.setItem('studio-last-job-v1',{last!r});"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            hits = {"proxy": 0}

            def media_route(route):
                if "proxy=1" in route.request.url:
                    hits["proxy"] += 1
                    route.fulfill(
                        status=404, body=b"missing", headers={"Content-Type": "text/plain"}
                    )
                    return
                route.continue_()

            page.route("**/api/media**", media_route)

            def capture(route):
                request = route.request
                if request.method == "POST" and "/api/creation/" in request.url:
                    posted.append(json.loads(request.post_data or "{}"))
                route.continue_()

            page.route("**/api/creation/**", capture)
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            expect(page.locator(".timeline .clip")).to_have_count(2)
            before = page.evaluate(
                """() => [...document.querySelectorAll('.timeline .clip')].map((el) => ({
                    text: el.textContent,
                    clip: el.getAttribute('data-clip-id') || el.dataset.clipId || null,
                }))"""
            )
            page.get_by_title("第 1 个镜头", exact=False).click(force=True)
            start = page.locator('fieldset[aria-label="镜头编辑"] label:has-text("入点") input')
            end = page.locator('fieldset[aria-label="镜头编辑"] label:has-text("出点") input')
            expect(start).to_be_visible()
            before_range = (start.input_value(), end.input_value())
            page.get_by_role("button", name="预览方案").click()
            expect(page.locator("[data-preview-clock-reason]")).to_have_attribute(
                "data-preview-clock-reason", "proxy_http_failed", timeout=20000
            )
            expect(page.locator("[data-preview-clock-reason]")).to_have_text(
                "代理无法加载，已改用原片"
            )
            page.wait_for_function(
                """() => {
                    const slots = [...document.querySelectorAll('[data-preview-slot]')];
                    const srcs = slots.map((v) => v.getAttribute('src') || v.src || '');
                    return srcs.some((src) => src.includes('/api/media'))
                        && srcs.filter(Boolean).every((src) => !src.includes('proxy=1'));
                }""",
                timeout=20000,
            )
            after = page.evaluate(
                """() => [...document.querySelectorAll('.timeline .clip')].map((el) => ({
                    text: el.textContent,
                    clip: el.getAttribute('data-clip-id') || el.dataset.clipId || null,
                }))"""
            )
            assert after == before
            page.get_by_title("第 1 个镜头", exact=False).click(force=True)
            expect(start).to_be_visible()
            assert (start.input_value(), end.input_value()) == before_range
            first = hits["proxy"]
            assert first > 0
            time.sleep(1.5)
            second = hits["proxy"]
            time.sleep(1.5)
            assert hits["proxy"] == second, "proxy was requested again after fallback settled"
            assert not posted, posted
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
