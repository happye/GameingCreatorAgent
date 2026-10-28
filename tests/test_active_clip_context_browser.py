"""Selected clip context stays separate from facts, basket and saved retrieval."""

import pytest
from test_context_playback import PLAYER
from test_detail_inspection import refuse_sends, seed_project
from test_inspection_http import workspace
from test_workbench_navigation_browser import shots_report, text_report


@pytest.mark.parametrize("width,height", [(1366, 768), (390, 844)])
def test_selected_context_updates_after_local_reports_and_clears_on_refresh(
    tmp_path, monkeypatch, width, height
):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_project(tmp_path)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.add_init_script(PLAYER)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def inspect(route):
                response = route.fetch()
                payload = response.json()
                payload["media"]["durationUs"] = 8_000_000
                row = payload["timeline"][0]
                row.update(startUs=3_000_000, endUs=5_000_000)
                row.pop("startTimecode", None)
                row.pop("endTimecode", None)
                payload["transcripts"] = [
                    {"startUs": 2_000_000, "endUs": 3_000_000, "text": "touch-only"},
                    {"startUs": 2_500_000, "endUs": 4_000_000, "text": "overlap speech"},
                    {"startUs": 5_000_000, "endUs": 6_000_000, "text": "after-only"},
                ]
                route.fulfill(response=response, json=payload)

            def health(route):
                response = route.fetch()
                payload = response.json()
                payload["capabilities"] = [
                    *payload["capabilities"],
                    "frame-text-v1",
                    "shot-boundaries-v1",
                ]
                route.fulfill(response=response, json=payload)

            def shots(route):
                payload = route.request.post_data_json
                report = shots_report(payload["project"], payload["run"])
                report["cuts"] = [{"timeUs": t} for t in (2_000_000, 4_000_000, 5_000_000)]
                route.fulfill(json=report)

            def text(route):
                payload = route.request.post_data_json
                report = text_report(payload["project"], payload["run"])
                report["frames"] = [
                    {"timeUs": 3_500_000, "lines": [{"text": "<b>Boss</b>"}]},
                    {"timeUs": 4_000_000, "lines": [{"text": "<b>Boss</b>"}]},
                    {"timeUs": 5_000_000, "lines": [{"text": "outside-only"}]},
                ]
                route.fulfill(json=report)

            page.route("**/api/inspect?**", inspect)
            page.route("**/api/health", health)
            page.route(
                "**/api/frame-text?**", lambda route: route.fulfill(json={"available": False})
            )
            page.route(
                "**/api/shot-boundaries?**", lambda route: route.fulfill(json={"available": False})
            )
            page.route("**/api/ocr-frames", text)
            page.route("**/api/detect-shots", shots)
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            context = page.locator("#active-local-context")
            playwright.expect(context).to_be_hidden()
            page.locator("#timeline-list .clip-preview").click()
            playwright.expect(context).to_contain_text("尚无检测报告")
            playwright.expect(context).to_contain_text("尚无识别报告")
            playwright.expect(context).to_contain_text("重叠语音 1 条")
            playwright.expect(context).not_to_contain_text("touch-only")
            playwright.expect(context).not_to_contain_text("after-only")
            page.locator("#detect-shots").click()
            playwright.expect(context).to_contain_text("镜头 2–3 · 区间内 1 次切换")
            page.locator("#scan-frame-text").click()
            playwright.expect(context).to_contain_text(
                "画面文字（本机识别，未经人工核对）：<b>Boss</b>"
            )
            playwright.expect(context).not_to_contain_text("outside-only")
            assert context.locator("b").count() == 0
            assert context.inner_text().count("<b>Boss</b>") == 1
            original = page.locator("#active-range").inner_text()
            context.locator("button").click()
            assert page.locator(".active-clip").evaluate("el => el.scrollHeight >= el.clientHeight")
            page.locator("#evidence-tab").click()
            assert page.locator("#evidence-tab").evaluate(
                """el => {
                    const bounds = el.getBoundingClientRect();
                    const parent = el.closest('.preview-panel').getBoundingClientRect();
                    return bounds.top >= parent.top && bounds.bottom <= parent.bottom;
                }"""
            )
            assert page.locator("#source-video").evaluate("v => v.currentTime") == 2.5
            assert page.locator("#active-range").inner_text() == original
            playwright.expect(page.locator("#selection-count")).to_have_text("0")
            page.locator("#refresh-view").click()
            playwright.expect(context).to_be_hidden()
            assert not errors
        finally:
            browser.close()
