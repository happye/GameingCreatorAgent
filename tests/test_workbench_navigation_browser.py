"""Workbench keyboard navigation over local shot cuts, on-screen text and events."""

from urllib.parse import parse_qs, urlparse

import pytest
from test_context_playback import PLAYER
from test_detail_inspection import refuse_sends, seed_project
from test_inspection_http import workspace

DURATION_US = 8_000_000


def shots_report(project, run):
    return {
        "available": True,
        "schemaVersion": "shot-boundaries-v1",
        "runId": run,
        "project": project,
        "durationUs": DURATION_US,
        "readOnly": True,
        "paidRequests": 0,
        "humanReviewed": False,
        "cuts": [{"timeUs": 2_000_000}, {"timeUs": 5_000_000}],
        "blackIntervals": [],
        "summary": {"events": 1, "eventsCrossingCut": 0, "windows": None},
    }


def text_report(project, run):
    line = lambda text, likely=True: {"text": text, "likelyText": likely}  # noqa: E731
    return {
        "available": True,
        "schemaVersion": "frame-text-v1",
        "runId": run,
        "project": project,
        "durationUs": DURATION_US,
        "density": "quick",
        "every": 1,
        "readOnly": True,
        "paidRequests": 0,
        "humanReviewed": False,
        "engine": {"unavailableLanguages": []},
        "summary": {"frames": 4, "framesWithText": 3, "framesWithLikelyText": 2},
        "recurringTexts": [
            {"text": "大蚌真君", "firstUs": 1_000_000, "lastUs": 1_000_000, "frames": 1}
        ],
        "frames": [
            {"timeUs": 1_000_000, "lines": [line("大蚌真君")]},
            {"timeUs": 4_000_000, "lines": [line("•ooo", False)]},
            {"timeUs": 6_000_000, "lines": [line("游戏科学")]},
        ],
    }


@pytest.mark.parametrize("width,height", [(1366, 768), (390, 844)])
def test_keys_walk_cuts_text_and_events_but_never_while_typing(
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
                payload["media"]["durationUs"] = DURATION_US
                row = payload["timeline"][0]
                row.update(startUs=3_000_000, endUs=4_000_000)
                row.pop("startTimecode", None)
                row.pop("endTimecode", None)
                # Real timelines share start times and nest events inside longer ones.
                shared = {**row, "eventId": row["eventId"] + "-shared", "endUs": 3_500_000}
                nested = {**row, "eventId": row["eventId"] + "-nested"}
                nested.update(startUs=3_200_000, endUs=3_800_000)
                payload["timeline"] = [row, nested, shared]
                route.fulfill(response=response, json=payload)

            def health(route):
                response = route.fetch()
                payload = response.json()
                payload["capabilities"] = sorted(
                    {*payload["capabilities"], "shot-boundaries-v1", "frame-text-v1"}
                )
                route.fulfill(response=response, json=payload)

            def report(builder):
                def handler(route):
                    query = parse_qs(urlparse(route.request.url).query)
                    route.fulfill(json=builder(query["project"][0], query["run"][0]))

                return handler

            page.route("**/api/inspect?**", inspect)
            page.route("**/api/health", health)
            page.route("**/api/shot-boundaries?**", report(shots_report))
            page.route("**/api/frame-text?**", report(text_report))
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("3")
            playwright.expect(page.locator("#shot-summary")).to_contain_text("镜头切换 2 处")
            playwright.expect(page.locator("#frame-text-summary")).to_contain_text("识别 4 帧")
            time = lambda: page.locator("#source-video").evaluate("v => v.currentTime")  # noqa: E731

            def press(key):
                page.locator("body").press(key)

            press("]")
            assert time() == 2
            press("]")
            assert time() == 5
            press("[")
            assert time() == 2
            # Text stops are likely-text frames only: the icon misread at 4 s is skipped.
            press(".")
            assert time() == 6
            press(",")
            assert time() == 1
            # The text lane is drawn on the timeline map.
            painted = page.locator("#timeline-map").evaluate(
                """canvas => {
                    const context = canvas.getContext('2d');
                    const data = context.getImageData(0, Math.floor(canvas.height * 37 / 40), canvas.width, 1).data;
                    // Only the text lane uses the warm warning colour; tick marks share this row.
                    let count = 0;
                    for (let index = 0; index < data.length; index += 4) {
                        if (data[index + 3] && data[index] > 200 && data[index + 1] > 150 && data[index + 2] < 170) count += 1;
                    }
                    return count;
                }"""
            )
            assert painted > 0
            # Typing in a search box never moves the player.
            page.locator("#frame-text-query").fill("游戏")
            page.locator("#frame-text-query").press("]")
            page.locator("#frame-text-query").press("k")
            assert time() == 1
            assert page.locator("#frame-text-query").input_value() == "游戏]k"
            page.locator("#frame-text-query").fill("游戏")
            page.evaluate("() => document.activeElement.blur()")
            press(".")
            assert time() == 6
            # J/K walk every event in list order, including shared and nested starts.
            press("k")
            assert time() == 6  # no event after 6 s
            walked = []
            for _ in range(4):
                press("j")
                walked.append(page.locator("#active-range").inner_text())
            assert [item.split("–")[0].strip()[-12:] for item in walked] == [
                "00:00:03.200",
                "00:00:03.000",
                "00:00:03.000",
                "00:00:03.000",
            ]
            assert "03.500" in walked[2] and "04.000" in walked[1] and walked[3] == walked[2]
            press("k")
            playwright.expect(page.locator("#active-range")).to_contain_text("00:00:04.000")
            # B only adds; pressing it again never removes the clip.
            playwright.expect(page.locator("#selection-count")).to_have_text("0")
            press("b")
            playwright.expect(page.locator("#selection-count")).to_have_text("1")
            press("b")
            playwright.expect(page.locator("#selection-count")).to_have_text("1")
            playwright.expect(page.locator("#notice")).to_contain_text("已在片段篮")
            # The switch turns every shortcut off.
            page.locator("#navigation-keys").uncheck()
            before = time()
            press("]")
            assert time() == before
            assert not errors
        finally:
            browser.close()
