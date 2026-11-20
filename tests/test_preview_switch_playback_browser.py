"""B09: 切换预览源时保持暂停或接上播放；旧 loadedmetadata 不能把新素材拖到旧位置。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from test_benchmark_source_clock_browser import synthesize
from test_detail_inspection import refuse_sends
from test_inspection_http import workspace
from test_preview_clock_align_browser import (
    _seed_from_file,
    plant_playable_proxy,
    seed_playable_project,
)

from gamingcreator.application.browser_source_clock import build_source_clock, clock_document

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

STUDIO_BOOT = "localStorage.setItem('studio-v1', JSON.stringify({project:'artifacts/project', workspace:'assets'}));"


def media_query(page, selector="#source-video"):
    src = page.locator(selector).get_attribute("src") or ""
    return {key: values[0] for key, values in parse_qs(urlparse(src).query).items()}


def wait_ready(page, selector="#source-video"):
    page.wait_for_function(
        """(sel) => {
            const v = document.querySelector(sel);
            return v && Number.isFinite(v.duration) && v.duration > 0 && v.readyState >= 1
                && window.SourceClock;
        }""",
        arg=selector,
        timeout=20000,
    )


def seek_us(page, clock, us, selector="#source-video"):
    page.evaluate(
        """({clock, us, sel}) => {
            const v = document.querySelector(sel);
            v.currentTime = SourceClock.sourceUsToPlayerSeconds(clock, us);
            v.dispatchEvent(new Event("timeupdate"));
        }""",
        {"clock": clock, "us": us, "sel": selector},
    )
    page.wait_for_function(
        """({clock, us, sel}) => {
            const v = document.querySelector(sel);
            const now = SourceClock.playerToSourceUs(clock, v.currentTime);
            return now !== null && Math.abs(now - us) <= 80000;
        }""",
        arg={"clock": clock, "us": us, "sel": selector},
        timeout=10000,
    )


def wait_source_us(page, clock, us, *, proxy, selector="#source-video"):
    page.wait_for_function(
        """({clock, us, proxy, sel}) => {
            const v = document.querySelector(sel);
            if (!v || !v.currentSrc || v.readyState < 1) return false;
            const hasProxy = v.currentSrc.includes("proxy=1");
            if (proxy && !hasProxy) return false;
            if (!proxy && hasProxy) return false;
            const now = SourceClock.playerToSourceUs(clock, v.currentTime);
            return now !== null && Math.abs(now - us) <= 80000;
        }""",
        arg={"clock": clock, "us": us, "proxy": proxy, "sel": selector},
        timeout=20000,
    )


def play_muted(page, selector="#source-video"):
    page.evaluate(
        """(sel) => {
            const v = document.querySelector(sel);
            v.muted = true;
            return v.play();
        }""",
        selector,
    )
    page.wait_for_function(
        "(sel) => { const v = document.querySelector(sel); return v && !v.paused; }",
        arg=selector,
        timeout=10000,
    )


def is_paused(page, selector="#source-video"):
    return page.evaluate("(sel) => document.querySelector(sel).paused", selector)


def seed_two_zero_origin_media(root):
    _project, first, _timeline = seed_playable_project(root, kind="zero")
    second_path = root / "artifacts" / "source-2.mp4"
    synthesize(second_path, "audio_late")
    project, second, _second_timeline = _seed_from_file(
        root, second_path, run_id="run-2", source_name="source-2.mp4"
    )
    plant_playable_proxy(root, first.asset.source_path, first.asset.sha256, first.asset.duration_us)
    plant_playable_proxy(
        root, second.asset.source_path, second.asset.sha256, second.asset.duration_us
    )
    assert first.asset.media_id != second.asset.media_id
    return project, first, second


def test_workbench_toggle_keeps_pause_and_restores_play(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    official = clock_document(build_source_clock(bundle.asset))
    video = "#source-video"
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            wait_ready(page, video)
            seek_us(page, official, 500000, video)
            assert is_paused(page, video)
            page.locator("#proxy-toggle-input").uncheck()
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            wait_source_us(page, official, 500000, proxy=False, selector=video)
            assert is_paused(page, video)
            play_muted(page, video)
            page.evaluate("(sel) => { document.querySelector(sel).muted = true; }", video)
            page.locator("#proxy-toggle-input").check()
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            wait_source_us(page, official, 500000, proxy=True, selector=video)
            page.wait_for_function(
                """(sel) => {
                    const v = document.querySelector(sel);
                    return v && v.currentSrc && v.currentSrc.includes("proxy=1") && !v.paused;
                }""",
                arg=video,
                timeout=20000,
            )
            assert not errors, errors
        finally:
            browser.close()


def test_workbench_stale_metadata_does_not_seek_new_media(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, first, second = seed_two_zero_origin_media(tmp_path)
    first_clock = clock_document(build_source_clock(first.asset))
    second_clock = clock_document(build_source_clock(second.asset))
    video = "#source-video"
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            held = []
            holding = {"on": False}

            def handle(route):
                if holding["on"]:
                    held.append(route)
                else:
                    route.continue_()

            page.route("**/api/media**", handle)
            page.goto(base)
            expect(page.locator("#run-select")).to_be_enabled(timeout=20000)
            page.locator("#run-select").select_option("run-1")
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            wait_ready(page, video)
            seek_us(page, first_clock, 1000000, video)
            assert is_paused(page, video)
            holding["on"] = True
            page.locator("#proxy-toggle-input").uncheck()
            page.locator("#run-select").select_option("run-2")
            pending = list(held)
            holding["on"] = False
            for route in pending:
                route.continue_()
            expect(page.locator("#source-name")).to_have_text("source-2.mp4", timeout=20000)
            wait_ready(page, video)
            page.wait_for_function(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    if (!v || !v.currentSrc || v.readyState < 1) return false;
                    const now = SourceClock.playerToSourceUs(clock, v.currentTime);
                    return now !== null && Math.abs(now) <= 120000;
                }""",
                arg=second_clock,
                timeout=20000,
            )
            assert is_paused(page, video)
            now = page.evaluate(
                """(clock) => SourceClock.playerToSourceUs(
                    clock, document.getElementById("source-video").currentTime
                )""",
                second_clock,
            )
            assert now is not None and abs(now) <= 120000, now
            assert abs(now - 1000000) > 500000
            assert not errors, errors
        finally:
            holding["on"] = False
            for route in list(held):
                try:
                    route.continue_()
                except Exception:
                    pass
            browser.close()


def test_studio_asset_toggle_keeps_pause_and_restores_play(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    official = clock_document(build_source_clock(bundle.asset))
    video = ".viewer video"
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(STUDIO_BOOT)
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text(
                "编辑代理（非原片）", timeout=20000
            )
            wait_ready(page, video)
            seek_us(page, official, 500000, video)
            assert is_paused(page, video)
            page.locator("#proxy-toggle-input").uncheck()
            expect(page.locator("[data-preview-source]")).to_have_text("原始素材", timeout=20000)
            wait_source_us(page, official, 500000, proxy=False, selector=video)
            assert is_paused(page, video)
            play_muted(page, video)
            page.evaluate("(sel) => { document.querySelector(sel).muted = true; }", video)
            page.locator("#proxy-toggle-input").check()
            expect(page.locator("[data-preview-source]")).to_have_text(
                "编辑代理（非原片）", timeout=20000
            )
            wait_source_us(page, official, 500000, proxy=True, selector=video)
            page.wait_for_function(
                """(sel) => {
                    const v = document.querySelector(sel);
                    return v && v.currentSrc && v.currentSrc.includes("proxy=1") && !v.paused;
                }""",
                arg=video,
                timeout=20000,
            )
            assert not errors, errors
        finally:
            browser.close()
