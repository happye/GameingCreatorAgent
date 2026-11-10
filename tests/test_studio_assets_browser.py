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
def assets_page(service, monkeypatch, tmp_path, request):  # noqa: F811
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
    kind = getattr(request, "param", None)
    if kind in {"zero", "nonzero", "video_late"}:
        from test_benchmark_source_clock_browser import synthesize

        synthesize(source, kind)
    from test_benchmark_source_clock_browser import probe_source

    from gamingcreator.application.browser_source_clock import build_source_clock, clock_document

    asset = probe_source(source)
    clock = clock_document(build_source_clock(asset))
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
    for port in range(20000, 21000):
        try:
            server = create_server("127.0.0.1", port, service.repository)
            break
        except OSError as error:
            if getattr(error, "winerror", None) != 10048:
                raise
    else:
        raise RuntimeError("No browser-safe local port available")
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
                "startUs": 300_000 if kind else 2_000_000,
                "endUs": 700_000 if kind else 2_000_000,
                "startTimecode": "00:00:02.000",
                "endTimecode": "00:00:02.000",
                "displayFacts": ["跳跃"],
                "evidenceIds": [],
                "mechanicTags": [],
            }
            if kind in {"zero", "nonzero", "video_late"}:
                event.update(
                    analysisStartUs=300_000,
                    analysisEndUs=700_000,
                    sourceDurationUs=clock["durationUs"],
                )
            if kind == "video_late":
                event.update(
                    startUs=0, endUs=1_000_000, analysisStartUs=600_000, analysisEndUs=700_000
                )
            return route.fulfill(
                json={
                    "runId": run,
                    "timeline": [event],
                    "evidence": [],
                    "media": {
                        "videoUrl": f"/api/media?project=x&run={run}",
                        "durationUs": clock["durationUs"],
                        "sourceClock": None if kind == "unknown" else clock,
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
    page.wait_for_function(
        "() => document.querySelector('.viewer .tc').textContent.includes('00:00.000')"
    )
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


@pytest.mark.parametrize("assets_page", ["zero", "nonzero"], indirect=True)
def test_asset_clock_maps_marker_bounds_replay_and_keys(assets_page):
    from test_benchmark_source_clock_browser import read_marker

    page, _ = assets_page
    expect = pytest.importorskip("playwright.sync_api").expect
    expect(page.locator(".viewer")).to_have_attribute("data-source-clock", "ready")
    page.locator(".timeline .clip").click()
    video = page.locator(".viewer video")
    expect(page.locator(".viewer .tc").first).to_contain_text("00:00.300")
    page.wait_for_function("() => !document.querySelector('.viewer video').seeking")
    video.evaluate("v => {v.style.width='320px'; v.style.height='180px';}")
    marker, sync = read_marker(video.screenshot())
    assert sync in range(115, 145)
    assert abs(marker - 9) <= 1
    start = video.evaluate("v => v.currentTime")
    page.get_by_role("button", name="播放", exact=True).click()
    page.wait_for_function("() => document.querySelector('.viewer video').paused")
    assert abs(video.evaluate("v => v.currentTime") - start - 0.4) < 0.05
    expect(page.locator(".viewer .tc").first).to_contain_text("00:00.700")
    page.get_by_role("button", name="播放", exact=True).click()
    page.wait_for_function(
        "start => {const v=document.querySelector('.viewer video'); return !v.paused && !v.seeking && v.currentTime < start + 0.2;}",
        arg=start,
    )
    assert video.evaluate("v => v.currentTime") < start + 0.2
    video.evaluate("v => v.pause()")
    page.get_by_role("button", name="查看整段录像").click()
    video.click()
    page.wait_for_function(
        "() => document.querySelector('.viewer video').currentTime > " + str(start + 0.6)
    )
    video.evaluate("v => v.pause()")
    page.keyboard.press("ArrowLeft")
    expect(page.locator(".viewer .tc").first).to_contain_text("00:00.000")
    page.keyboard.press("ArrowRight")
    expect(page.locator(".viewer .tc").first).to_contain_text("00:01.000")


@pytest.mark.parametrize("assets_page", ["unknown"], indirect=True)
def test_unknown_asset_clock_does_not_claim_precise_addressing(assets_page):
    page, _ = assets_page
    expect = pytest.importorskip("playwright.sync_api").expect
    expect(page.get_by_text("无法精确定位片段，可观看整段录像", exact=True)).to_be_visible()
    page.locator(".timeline .clip").click()
    expect(page.locator(".viewer .tc").first).to_contain_text("源时间未校准")
    expect(page.get_by_text("片段寻址不可用", exact=True)).to_be_visible()


@pytest.mark.parametrize("assets_page", ["video_late"], indirect=True)
def test_pictureless_head_keeps_selected_end_and_replay_boundaries(assets_page):
    from test_benchmark_source_clock_browser import read_marker

    page, _ = assets_page
    expect = pytest.importorskip("playwright.sync_api").expect
    expect(page.locator(".viewer")).to_have_attribute("data-source-clock", "ready")
    page.locator(".timeline .clip").click()
    expect(page.get_by_label("选段入点")).to_have_value("0")
    expect(page.get_by_label("选段出点")).to_have_value("1")
    video = page.locator(".viewer video")
    video.evaluate("v => {v.style.width='320px'; v.style.height='180px';}")
    page.get_by_role("button", name="播放", exact=True).click()
    page.wait_for_function("() => document.querySelector('.viewer video').paused")
    assert abs(video.evaluate("v => v.currentTime") - 1) < 0.06
    expect(page.locator(".viewer .tc").first).to_contain_text("00:01.000")
    expect(
        page.get_by_text("片段开头无画面，从首个可播放画面开始，仍在选段终点暂停", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="播放", exact=True).click()
    page.wait_for_function(
        "() => {const v=document.querySelector('.viewer video'); return !v.paused && !v.seeking && v.currentTime >= 0.5 && v.currentTime < 0.8;}"
    )
    video.evaluate("v => v.pause()")
    marker, sync = read_marker(video.screenshot())
    assert 0 <= marker <= 10 and sync in range(115, 145)
    expect(page.get_by_label("选段入点")).to_have_value("0")
    page.get_by_role("button", name="查看整段录像").click()
    video.evaluate("v => {v.currentTime=1.1; return v.play();}")
    page.wait_for_function("() => document.querySelector('.viewer video').currentTime > 1.3")
    assert not video.evaluate("v => v.paused")


def test_cleared_basket_can_be_restored_until_something_new_is_added(assets_page):
    page, _ = assets_page
    expect = pytest.importorskip("playwright.sync_api").expect
    page.get_by_label("搜索片段").fill("跳跃")
    page.get_by_label("搜索范围").select_option("all")
    hits = page.locator(".clip-search .hit")
    expect(hits).to_have_count(2)
    hits.nth(0).get_by_role("button", name="加入片段篮").click()
    hits.nth(1).get_by_role("button", name="加入片段篮").click()
    expect(page.locator(".basket .section-label")).to_contain_text("2 段")
    page.locator(".basket").get_by_role("button", name="清空").click()
    expect(page.locator(".basket .section-label")).to_contain_text("0 段")
    page.reload()
    page.locator(".basket").get_by_role("button", name="恢复").click()
    expect(page.locator(".basket .section-label")).to_contain_text("2 段")
    page.locator(".basket").get_by_role("button", name="清空").click()
    page.get_by_label("搜索片段").fill("跳跃")
    page.get_by_label("搜索范围").select_option("all")
    hits.nth(0).get_by_role("button", name="加入片段篮").click()
    expect(page.locator(".basket").get_by_role("button", name="恢复")).to_have_count(0)
