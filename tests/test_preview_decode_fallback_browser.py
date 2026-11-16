"""B08: 代理解码失败退回原片；拒绝旧素材迟到 error；原片失败显示真实错误。"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import pytest
from test_detail_inspection import refuse_sends
from test_inspection_http import workspace
from test_preview_clock_align_browser import plant_playable_proxy, seed_playable_project

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def media_query(page, selector="#source-video"):
    src = page.locator(selector).get_attribute("src") or ""
    return {key: values[0] for key, values in parse_qs(urlparse(src).query).items()}


def corrupt_mid(data: bytes, span: int = 8000) -> bytes:
    body = bytearray(data)
    mid = max(0, len(body) // 2)
    width = min(span, max(0, len(body) - mid))
    body[mid : mid + width] = b"\x00" * width
    return bytes(body)


def test_workbench_proxy_decode_failure_falls_back_to_original(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path,
        bundle.asset.source_path,
        bundle.asset.sha256,
        bundle.asset.duration_us,
        body=corrupt_mid(bundle.asset.source_path.read_bytes()),
    )
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            hits = {"proxy": 0}

            def handle(route):
                if "proxy=1" in route.request.url:
                    hits["proxy"] += 1
                route.continue_()

            page.route("**/api/media**", handle)
            page.goto(base)
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("[data-preview-clock-reason]")).to_have_attribute(
                "data-preview-clock-reason", "proxy_decode_failed", timeout=20000
            )
            expect(page.locator("#preview-clock-reason")).to_have_text("代理解码失败，已改用原片")
            assert "proxy" not in media_query(page)
            page.wait_for_function(
                "() => document.getElementById('source-video')?.readyState >= 1",
                timeout=20000,
            )
            assert hits["proxy"] > 0
            time.sleep(1.2)
            second = hits["proxy"]
            time.sleep(1.2)
            assert hits["proxy"] == second, (
                "proxy was requested again after decode fallback settled"
            )
            assert not errors, errors
        finally:
            browser.close()


def test_studio_asset_proxy_decode_failure_falls_back_to_original(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path,
        bundle.asset.source_path,
        bundle.asset.sha256,
        bundle.asset.duration_us,
        body=corrupt_mid(bundle.asset.source_path.read_bytes()),
    )
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(
                "localStorage.setItem('studio-v1', JSON.stringify({project:'artifacts/project', workspace:'assets'}));"
            )
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("[data-preview-clock-reason]")).to_have_attribute(
                "data-preview-clock-reason", "proxy_decode_failed", timeout=20000
            )
            expect(page.locator("[data-preview-clock-reason]")).to_have_text(
                "代理解码失败，已改用原片"
            )
            assert "proxy" not in media_query(page, ".viewer video")
            assert not errors, errors
        finally:
            browser.close()


def test_workbench_ignores_stale_proxy_error_after_switching_to_original(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    late = []
    freeze = {"on": False}
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                if "proxy=1" in route.request.url and freeze["on"]:
                    late.append(route)
                    return
                route.continue_()

            page.route("**/api/media**", handle)
            page.goto(base)
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            page.wait_for_function(
                "() => document.getElementById('source-video')?.readyState >= 1",
                timeout=20000,
            )
            freeze["on"] = True
            page.evaluate("document.getElementById('source-video').load()")
            for _ in range(40):
                if late:
                    break
                page.wait_for_timeout(100)
            assert late, "did not capture an in-flight proxy request to abort late"
            page.locator("#proxy-toggle-input").uncheck()
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            page.wait_for_function(
                "() => document.getElementById('source-video')?.readyState >= 1 && !(document.getElementById('source-video')?.currentSrc || '').includes('proxy=1')",
                timeout=20000,
            )
            for route in list(late):
                try:
                    route.abort("failed")
                except Exception:
                    pass
            page.wait_for_timeout(800)
            expect(page.locator("#video-empty")).to_be_hidden()
            assert page.locator("[data-original-playback-error]").count() == 0
            assert "proxy" not in media_query(page)
            assert not errors, errors
        finally:
            browser.close()


def test_workbench_shows_real_error_when_original_also_fails(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            hits = {"all": 0}

            def handle(route):
                hits["all"] += 1
                route.fulfill(status=404, body=b"missing", headers={"Content-Type": "text/plain"})

            page.route("**/api/media**", handle)
            page.goto(base)
            expect(page.locator("[data-original-playback-error]")).to_be_visible(timeout=20000)
            heading = page.locator("[data-original-playback-error]").inner_text()
            assert heading in {"原片加载失败，暂时无法播放", "浏览器无法播放该原片"}, heading
            expect(page.locator("#video-empty")).to_be_visible()
            first = hits["all"]
            assert first > 0
            time.sleep(1.2)
            second = hits["all"]
            time.sleep(1.2)
            assert hits["all"] == second, "media was requested again after original failure settled"
            assert not errors, errors
        finally:
            browser.close()
