"""Timeline OCR filtering uses sampled source instants, never merged spans."""

from urllib.parse import parse_qs, urlparse

import pytest
from test_context_playback import PLAYER
from test_detail_inspection import refuse_sends, seed_project
from test_inspection_http import workspace
from test_workbench_navigation_browser import text_report


@pytest.mark.parametrize("width,height", [(1366, 768), (390, 844)])
def test_text_filter_instants_labels_persistence_and_missing_report(
    tmp_path, monkeypatch, width, height
):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_project(tmp_path)
    refuse_sends(monkeypatch)
    available = [True]
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
                original = payload["timeline"][0]
                rows = []
                for index, (start, end, fact) in enumerate(
                    [(0, 1, "普通事件"), (3, 4, "战斗"), (6, 7, "文字词")]
                ):
                    row = {**original, "eventId": f"event-{index}"}
                    row.update(startUs=start * 1_000_000, endUs=end * 1_000_000)
                    row["observableFacts"] = [fact]
                    row["displayFacts"] = [fact]
                    row["mechanicTags"] = ["combat" if index == 1 else "other"]
                    row.pop("startTimecode", None)
                    row.pop("endTimecode", None)
                    rows.append(row)
                payload["timeline"] = rows
                route.fulfill(response=response, json=payload)

            def health(route):
                response = route.fetch()
                payload = response.json()
                payload["capabilities"] = [*payload["capabilities"], "frame-text-v1"]
                route.fulfill(response=response, json=payload)

            def report(route):
                if not available[0]:
                    route.fulfill(json={"available": False})
                    return
                query = parse_qs(urlparse(route.request.url).query)
                payload = text_report(query["project"][0], query["run"][0])
                # Merged OCR span 0..4.9 must not make an event in its gap match.
                payload["frames"] = [
                    {"timeUs": 0, "lines": [{"text": "gap", "likelyText": True}]},
                    {"timeUs": 4_900_000, "lines": [{"text": "文字词 gap", "likelyText": True}]},
                ]
                route.fulfill(json=payload)

            page.route("**/api/inspect?**", inspect)
            page.route("**/api/health", health)
            page.route("**/api/frame-text?**", report)
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("3")
            playwright.expect(page.locator("#frame-text-summary")).to_contain_text("识别 4 帧")
            toggle = page.locator("#timeline-include-text")
            playwright.expect(toggle).not_to_be_checked()
            search = page.locator("#timeline-filter")
            search.fill("文字词")
            playwright.expect(page.locator(".timeline-row")).to_have_count(1)
            toggle.check()
            playwright.expect(page.locator(".timeline-row")).to_have_count(2)
            playwright.expect(page.locator("#filter-summary")).to_contain_text(
                "1 个只因画面文字匹配"
            )
            playwright.expect(page.locator("#timeline-list")).to_contain_text(
                "画面文字匹配 · 未核对"
            )
            page.locator("#tag-filter").select_option("combat")
            playwright.expect(page.locator(".timeline-row")).to_have_count(1)
            playwright.expect(page.locator("#timeline-list")).to_contain_text("03.000")
            # Matching the exact frame tolerance must not reach the earlier 0..1 event.
            playwright.expect(page.locator("#timeline-list")).not_to_contain_text("01.000")
            page.locator("#tag-filter").select_option("")
            search.fill("")
            playwright.expect(page.locator(".timeline-row")).to_have_count(3)
            playwright.expect(page.locator("#filter-summary")).to_contain_text("0 个只因")
            search.fill("not-present")
            playwright.expect(page.locator(".timeline-row")).to_have_count(0)
            page.reload()
            playwright.expect(page.locator("#timeline-count")).to_have_text("3")
            playwright.expect(toggle).to_be_checked()
            search.fill("文字词")
            playwright.expect(page.locator(".timeline-row")).to_have_count(2)
            available[0] = False
            page.reload()
            playwright.expect(page.locator("#timeline-count")).to_have_text("3")
            playwright.expect(page.locator("#filter-summary")).to_contain_text("尚无画面文字")
            search.fill("文字词")
            playwright.expect(page.locator(".timeline-row")).to_have_count(1)
            assert not errors
        finally:
            browser.close()
