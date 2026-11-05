"""Material identity, explicit search scope and bounded source playback in the real studio."""

import json
import subprocess
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from test_creation_jobs import service  # noqa: F401

from gamingcreator.ui.server import create_server


@pytest.fixture
def assets_page(service, monkeypatch, tmp_path):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as implementation

    source = tmp_path / "source.mp4"
    ffmpeg = Path(__file__).resolve().parents[1] / ".tools/ffmpeg/bin/ffmpeg.exe"
    subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48:r=10:d=8",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            "-fs",
            "1048576",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    media = source.read_bytes()
    runs = [
        {
            "id": identity,
            "sourceName": title,
            "sourceSha256": sha * 64,
            "completedEligible": identity != "failed",
            "status": "failed" if identity == "failed" else "completed",
            "durationUs": 8_000_000,
        }
        for identity, title, sha in (
            ("first", "甲游戏PV", "a"),
            ("duplicate", "甲游戏PV", "a"),
            ("failed", "甲游戏PV", "a"),
            ("second", "乙游戏实机", "b"),
        )
    ]

    async def list_runs(project):
        return {"runs": runs}

    monkeypatch.setattr(implementation, "project_runs_payload", list_runs)
    server = create_server("127.0.0.1", 0, service.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    posted = []

    def answer(route):
        url = urlsplit(route.request.url)
        if url.path == "/api/media":
            value = route.request.headers.get("range", "")
            start = int(value.split("=", 1)[1].split("-", 1)[0] or "0") if value else 0
            headers = {"Accept-Ranges": "bytes", "Content-Length": str(len(media) - start)}
            if value:
                headers["Content-Range"] = f"bytes {start}-{len(media) - 1}/{len(media)}"
            return route.fulfill(
                status=206 if value else 200,
                body=media[start:],
                content_type="video/mp4",
                headers=headers,
            )
        if url.path == "/api/inspect":
            run = parse_qs(url.query)["run"][0]
            event = {
                "eventId": f"{run}:m:event:0",
                "startUs": 2_000_000,
                "endUs": 2_000_000,
                "startTimecode": "00:00:02.000",
                "endTimecode": "00:00:02.000",
                "displayFacts": ["跳跃"],
                "evidenceIds": [],
                "mechanicTags": [],
            }
            return route.fulfill(
                json={
                    "runId": run,
                    "timeline": [event],
                    "evidence": [],
                    "media": {
                        "videoUrl": f"/api/media?project=x&run={run}",
                        "durationUs": 8_000_000,
                    },
                }
            )
        if url.path == "/api/creation/plans":
            posted.append(json.loads(route.request.post_data))
            return route.fulfill(status=202, json={"jobId": "c" * 32})
        if url.path == "/api/creation/jobs/" + "c" * 32:
            return route.fulfill(
                json={"jobId": "c" * 32, "status": "completed", "kind": "plan", "plans": []}
            )
        return route.continue_()

    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            page.route("**/api/**", answer)
            page.goto(f"http://127.0.0.1:{server.server_port}/studio")
            yield page, posted
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_recordings_deduplicate_search_scope_and_keep_selected_ranges(assets_page):
    page, posted = assets_page
    expect = pytest.importorskip("playwright.sync_api").expect
    expect(page.locator(".recording")).to_have_count(2)
    expect(page.get_by_text("分析记录（3）", exact=True)).to_be_visible()
    page.get_by_label("搜索片段").fill("跳跃")
    expect(page.locator(".clip-search .hit")).to_have_count(1)
    page.get_by_label("搜索范围").select_option("all")
    expect(page.locator(".clip-search .hit")).to_have_count(2)
    page.locator(".clip-search .hit").first.get_by_role("button", name="加入片段篮").click()
    expect(page.locator(".basket .section-label")).to_contain_text("3.0 秒")
    page.locator(".basket .hit-main").click()
    expect(page.get_by_label("选段入点")).to_have_value("0.5")
    page.get_by_label("选段入点").fill("0")
    page.get_by_label("选段入点").press("Tab")
    page.get_by_label("选段出点").fill("4")
    page.get_by_label("选段出点").press("Tab")
    expect(page.locator(".basket .section-label")).to_contain_text("4.0 秒")
    page.get_by_role("button", name="用片段篮生成方案").click()
    expect(page.locator(".basket-option input")).to_be_checked()
    expect(page.locator(".brief .runs input")).to_have_count(2)
    page.locator(".brief input.input").first.fill("甲游戏")
    with page.expect_response("**/api/creation/plans"):
        page.get_by_role("button", name="生成方案").click()
    expect(page.get_by_role("button", name="生成方案")).to_be_enabled()
    assert posted[0]["clipRanges"] == [
        {"runId": "first", "eventId": "first:m:event:0", "startUs": 0, "endUs": 4_000_000}
    ]


def test_source_clip_stops_at_end_replays_and_full_source_can_continue(assets_page):
    page, _ = assets_page
    page.locator(".timeline .clip").click()
    pytest.importorskip("playwright.sync_api").expect(page.get_by_label("选段入点")).to_have_value(
        "0.5"
    )
    video = page.locator(".viewer video")
    page.wait_for_function("() => document.querySelector('.viewer video').readyState >= 2")
    video.evaluate("v => { v.currentTime = 3.4; return v.play(); }")
    page.wait_for_function("() => document.querySelector('.viewer video').paused")
    assert abs(video.evaluate("v => v.currentTime") - 3.5) < 0.12
    page.get_by_role("button", name="播放", exact=True).click()
    page.wait_for_function(
        "() => !document.querySelector('.viewer video').paused && document.querySelector('.viewer video').currentTime < 1.2"
    )
    assert video.evaluate("v => v.currentTime") < 1.2
    page.get_by_role("button", name="查看整段录像").click()
    video.evaluate("v => { v.currentTime = 4; return v.play(); }")
    page.wait_for_function("() => document.querySelector('.viewer video').currentTime > 4.2")
    assert not video.evaluate("v => v.paused")
