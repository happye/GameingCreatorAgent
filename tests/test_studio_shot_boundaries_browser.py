"""Studio shows real local cut/black results on the original source timeline."""

import pytest
from shot_hard_case_fixtures import FFMPEG, ROOT, load_catalog, render_case
from test_detail_query import snapshot
from test_inspection_http import workspace
from test_preview_clock_align_browser import _seed_from_file

from gamingcreator.infrastructure.ffmpeg_shots import FfmpegShotDetector

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = [pytest.mark.browser, pytest.mark.skipif(not FFMPEG.is_file(), reason="local FFmpeg")]


def test_studio_scans_shots_and_restores_the_original_clock_markers(tmp_path, monkeypatch):
    fixture = load_catalog()
    case = next(item for item in fixture["cases"] if item["id"] == "hard-cut-plus-black")
    video = render_case(
        case,
        tmp_path / "hard-cut.mp4",
        width=fixture["width"],
        height=fixture["height"],
        fps=fixture["fps"],
    )
    assert video.stat().st_size <= fixture["maxVideoBytes"]
    project, _bundle, _event = _seed_from_file(tmp_path, video)
    reference = project.relative_to(tmp_path).as_posix()
    before = snapshot(project)
    monkeypatch.setattr(
        "gamingcreator.ui.server.FfmpegShotDetector", lambda _repo: FfmpegShotDetector(ROOT)
    )

    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            posts, errors = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def scoped_only(route):
                if route.request.method == "POST":
                    posts.append(route.request.post_data_json)
                    if route.request.url != f"{base}/api/detect-shots":
                        route.abort()
                        return
                route.continue_()

            page.route("**/api/**", scoped_only)
            page.goto(f"{base}/studio")
            viewer = page.get_by_label("预览窗")
            playwright.expect(viewer).to_have_attribute("data-source-clock", "ready", timeout=20000)
            timeline = page.get_by_label("时间轴", exact=True)
            trigger = timeline.get_by_role("button", name="检测镜头切换", exact=True)
            playwright.expect(trigger).to_be_enabled()
            assert not posts
            with page.expect_response("**/api/detect-shots") as accepted:
                trigger.click()
            assert accepted.value.ok, accepted.value.text()
            evidence = accepted.value.json()
            assert evidence["humanReviewed"] is False and evidence["paidRequests"] == 0
            lane = timeline.get_by_label("镜头切换与黑场")
            cut = lane.locator("[data-cut-us]")
            black = lane.locator("[data-black-start-us]")
            playwright.expect(cut).to_have_count(case["expect"]["cuts"])
            playwright.expect(black).to_have_count(case["expect"]["black"])

            timeline.locator(".track .clip").first.click()
            playwright.expect(viewer).to_contain_text("仅播放选中片段")
            black.first.click()
            target = evidence["blackIntervals"][0]["startUs"] / 1e6
            page.wait_for_function(
                "seconds => Math.abs(document.querySelector('.viewer video').currentTime - seconds) < .12",
                arg=target,
            )
            page.reload()
            playwright.expect(cut).to_have_count(case["expect"]["cuts"])
            playwright.expect(black).to_have_count(case["expect"]["black"])
            assert posts == [{"project": reference, "run": "run-1"}]
            assert not errors, errors
        finally:
            browser.close()
    assert before == snapshot(project)
