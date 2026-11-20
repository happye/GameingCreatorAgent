"""B11: 无声代理在工作台和 Studio 可播放，并诚实显示没有声音。"""

from __future__ import annotations

import pytest
from test_detail_inspection import refuse_sends
from test_inspection_http import workspace
from test_preview_clock_align_browser import _seed_from_file, plant_playable_proxy
from test_proxy_silent_audio import encode

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def playable(page, selector: str) -> None:
    expect(page.locator(selector)).to_be_visible(timeout=20000)
    page.evaluate(
        """(sel) => {
            const video = document.querySelector(sel);
            video.muted = true;
            return video.play().then(() => {
                if (video.readyState < 2) throw new Error("not playable");
                return true;
            });
        }""",
        selector,
    )


def test_workbench_and_studio_play_silent_proxy_and_show_honest_status(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)
    source = encode(
        tmp_path / "artifacts" / "source.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=2",
        "-an",
        "-c:v",
        "libx264",
    )
    _project, bundle, _timeline = _seed_from_file(tmp_path, source)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#timeline-count")).not_to_have_text("0", timeout=15000)
            expect(page.locator("[data-audio-status=silent]")).to_have_text(
                "这段录像没有声音", timeout=20000
            )
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            playable(page, "#source-video")
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text(
                "编辑代理（非原片）", timeout=20000
            )
            expect(page.locator("[data-audio-status=silent]")).to_have_text(
                "这段录像没有声音", timeout=20000
            )
            playable(page, ".viewer video")
            assert not errors, errors
        finally:
            browser.close()
