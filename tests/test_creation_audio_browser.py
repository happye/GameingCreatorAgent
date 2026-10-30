"""Audio UI mock contract; real mixing is verified by the renderer integration."""

import json
from pathlib import Path

import pytest


def test_audio_browser_snapshot_and_clear():
    pw = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
    root = "a" * 32
    track = {
        "trackId": "1" * 32,
        "title": "测试曲",
        "licenseStatus": "test_only",
        "trackReceiptSha256": "2" * 64,
    }
    editor = {
        "parentJobId": root,
        "planId": "p",
        "expectedParentReceiptSha256": "c" * 64,
        "fps": 30,
        "clips": [{"clipId": "c", "startUs": 0, "endUs": 1000000, "outputFrames": 30}],
        "ancestry": [],
    }
    posts = []
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})

        def route(r):
            path = r.request.url.split("http://workspace.test")[1]
            if path == "/creation":
                r.fulfill(
                    body=(static / "creation.html").read_text("utf-8-sig"), content_type="text/html"
                )
            elif path.startswith("/assets/"):
                r.fulfill(
                    body=(static / path.rsplit("/", 1)[1]).read_text("utf-8-sig"),
                    content_type="text/css" if path.endswith("css") else "text/javascript",
                )
            elif path == "/api/creation/music":
                r.fulfill(json={"tracks": [track], "issues": []})
            elif path == "/api/projects":
                r.fulfill(json={"projects": [{"path": "one"}]})
            elif path.startswith("/api/runs"):
                r.fulfill(json={"runs": []})
            elif r.request.method == "POST":
                posts.append(json.loads(r.request.post_data))
                r.fulfill(status=400, json={"error": "已捕获保存请求"})
            elif path.startswith("/api/creation/jobs?"):
                r.fulfill(
                    json={
                        "jobs": [
                            {
                                "jobId": root,
                                "kind": "revision",
                                "status": "completed",
                                "createdAt": "2026-10-30",
                            }
                        ]
                    }
                )
            elif "/edit?" in path:
                r.fulfill(json=editor)
            else:
                r.fulfill(
                    json={
                        "jobId": root,
                        "kind": "revision",
                        "status": "completed",
                        "projectId": "one",
                        "editor": editor,
                    }
                )

        page.route("**/*", route)
        try:
            page.goto("http://workspace.test/creation")
            page.locator("#history button").click()
            pw.expect(page.locator("#bgm-track")).to_be_visible()
            assert not posts
            page.locator("#bgm-track").select_option(track["trackId"])
            page.locator("#source-gain").fill("-6")
            page.locator("#bgm-gain").fill("-18")
            page.locator("#bgm-ducking").check()
            page.locator("[data-field=subtitle-override]").check()
            page.locator("[data-field=subtitle-text]").fill("配乐字幕共存")
            pw.expect(page.locator("#render")).to_be_disabled()
            page.locator("#save-revision").click()
            pw.expect(page.locator("#notice")).to_contain_text("已捕获")
            assert posts[-1]["audioMix"] == {
                "bgm": {
                    "trackId": track["trackId"],
                    "trackReceiptSha256": track["trackReceiptSha256"],
                    "gainDb": -18,
                },
                "sourceGainDb": -6,
                "ducking": "source-v1",
            }
            assert posts[-1]["subtitleOverrides"] == [{"clipId": "c", "text": "配乐字幕共存"}]
            page.locator("#remove-bgm").click()
            page.locator("#save-revision").click()
            page.wait_for_timeout(100)
            assert posts[-1]["audioMix"]["bgm"] is None
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.reload()
            pw.expect(page.locator("#bgm-track")).to_have_value("")
            assert len(posts) == 2
        finally:
            browser.close()
