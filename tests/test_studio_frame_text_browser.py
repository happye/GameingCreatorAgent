"""Studio keeps the verified OCR snapshot separate from media events and ranking."""

import json

import pytest
from shot_hard_case_fixtures import FFMPEG
from test_inspection_http import workspace
from test_preview_clock_align_browser import seed_playable_project

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = [pytest.mark.browser, pytest.mark.skipif(not FFMPEG.is_file(), reason="local FFmpeg")]


def test_studio_rescans_unverified_text_and_exports_literal_matches(tmp_path):
    project, bundle, _timeline = seed_playable_project(tmp_path)
    reference = project.relative_to(tmp_path).as_posix()
    line = "TaP TaP a\u0301 [.*]"
    report = {
        "schemaVersion": "frame-text-v1",
        "ocrSchemaVersion": "ocr-frames-v1",
        "available": True,
        "project": reference,
        "runId": "run-1",
        "sourceSha256": bundle.asset.sha256,
        "durationUs": bundle.asset.duration_us,
        "density": "full",
        "every": 1,
        "framesDigest": "a" * 64,
        "engine": {
            "name": "fixture",
            "platform": "Windows",
            "usedLanguages": ["en-US"],
            "unavailableLanguages": ["zh-Hans-CN"],
        },
        "summary": {"frames": 1, "framesWithText": 1, "failedFrames": 0},
        "frames": [{"timeUs": 500_000, "lines": [{"text": line, "likelyText": True}]}],
        "contentVerified": False,
        "readOnly": True,
        "paidRequests": 0,
        "humanReviewed": False,
    }
    reads, scans, pending = [], [], []

    def load(route):
        reads.append(route.request.url)
        route.fulfill(json=report)

    def scan(route):
        scans.append(route.request.post_data_json)
        pending.append(route)

    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page.route("**/api/frame-text?*", load)
            page.route("**/api/ocr-frames", scan)
            page.goto(f"{base}/studio")
            viewer = page.get_by_label("预览窗")
            playwright.expect(viewer).to_have_attribute("data-source-clock", "ready", timeout=20000)
            assert reads == scans == []
            toggle = page.get_by_role("button", name="画面文字", exact=True)
            toggle.click()
            panel = page.get_by_role("region", name="画面文字", exact=True)
            status = panel.locator("[data-frame-text-status]")
            search = panel.get_by_label("搜索画面文字")
            export = panel.get_by_role("button", name="导出画面文字 JSON")
            playwright.expect(status).to_have_attribute("data-frame-text-status", "legacy")
            playwright.expect(search).to_have_count(0)
            playwright.expect(export).to_have_count(0)
            assert len(reads) == 1 and scans == []

            panel.get_by_label("识别密度").select_option("full")
            panel.get_by_role("button", name="识别画面文字").click()
            playwright.expect(status).to_have_attribute("data-frame-text-status", "scanning")
            toggle.click()
            playwright.expect(panel).to_have_count(0)
            toggle.click()
            playwright.expect(status).to_have_attribute("data-frame-text-status", "scanning")
            assert len(reads) == 1 and len(pending) == 1
            pending[0].fulfill(json={**report, "contentVerified": True})
            playwright.expect(status).to_contain_text("本机缺少识别语言：zh-Hans-CN")
            assert scans == [{"project": reference, "run": "run-1", "density": "full"}]
            hit = panel.locator("[data-frame-text-time-us]")
            for query, marked in (
                ("taP tap", "TaP TaP"),
                ("a [.*]", "a\u0301 [.*]"),
                ("[.*]", "[.*]"),
            ):
                search.fill(query)
                if query == "a [.*]":
                    playwright.expect(hit).to_have_count(0)  # A combining accent stays significant.
                else:
                    playwright.expect(hit.locator("mark")).to_have_text(marked)
            hit.click()
            page.wait_for_function(
                "Math.abs(document.querySelector('.viewer video').currentTime - .5) < .1"
            )
            with page.expect_download() as downloaded:
                export.click()
            result = json.loads(downloaded.value.path().read_bytes())
            assert result["matches"] == [{"timeUs": 500_000, "text": line, "likelyText": True}]
            assert (
                result["runId"] == report["runId"]
                and result["sourceSha256"] == report["sourceSha256"]
            )
            assert result["report"]["framesDigest"] == report["framesDigest"]
            assert result["query"] == "[.*]" and result["humanReviewed"] is False
        finally:
            browser.close()
