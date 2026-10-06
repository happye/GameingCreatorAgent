"""Temporary context playback never expands the selected source interval."""

import json

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_inspection_http import workspace

# Deterministic player controls verify UI clock behavior, not media decoding.
# Actual registered MP4 playback is checked separately in the local smoke.
PLAYER = """
Object.defineProperty(HTMLMediaElement.prototype, 'readyState', {get() {return 1;}});
Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
    get() {return this.testTime || 0;}, set(value) {this.testTime = value;}
});
HTMLMediaElement.prototype.play = function() {this.testPaused = false; return Promise.resolve();};
HTMLMediaElement.prototype.pause = function() {this.testPaused = true;};
"""


@pytest.mark.parametrize("width,height", [(1366, 768), (390, 844)])
@pytest.mark.parametrize(
    "start,end,context_start,context_end",
    [(0, 2, 0, 3), (3, 4, 2, 5), (6, 8, 5, 8)],
)
def test_context_clamps_source_ends_and_preserves_export(
    tmp_path, monkeypatch, width, height, start, end, context_start, context_end
):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_project(tmp_path)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.add_init_script(PLAYER)
            calls, errors = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: calls.append(request.url))
            rows = []

            def clock_fixture(route):
                response = route.fetch()
                payload = response.json()
                payload["media"]["durationUs"] = 8_000_000
                row = payload["timeline"][0]
                row.update(startUs=start * 1_000_000, endUs=end * 1_000_000)
                row.pop("startTimecode", None)
                row.pop("endTimecode", None)
                rows.append(dict(row))
                route.fulfill(response=response, json=payload)

            page.route("**/api/inspect?**", clock_fixture)
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            playwright.expect(page.locator("#play-context")).to_be_disabled()
            page.locator("#timeline-list .clip-preview").click()
            playwright.expect(page.locator("#play-context")).to_be_enabled()
            row = rows[-1]
            selected_range = page.locator("#active-range").inner_text()
            page.locator("#add-active").click()
            storage = page.evaluate("JSON.stringify(localStorage)")
            source_calls = len([url for url in calls if "/api/inspect?" in url])

            page.locator("#play-context").click()
            assert page.locator("#source-video").evaluate("v => v.currentTime") == context_start
            playwright.expect(page.locator("#playback-range")).to_contain_text("前后文")
            playwright.expect(page.locator("#playback-range")).to_contain_text(
                f"00:00:{context_end:02}.000"
            )
            assert page.locator("#active-range").inner_text() == selected_range
            assert page.evaluate("JSON.stringify(localStorage)") == storage
            page.locator("#source-video").evaluate(
                "(v, time) => {v.currentTime=time; v.dispatchEvent(new Event('timeupdate'));}",
                context_end + 0.1,
            )
            assert page.locator("#source-video").evaluate("v => v.currentTime") == context_end
            assert page.locator("#source-video").evaluate("v => v.testPaused")

            # Repeated context playback always expands the original row, once.
            page.locator("#play-context").click()
            assert page.locator("#source-video").evaluate("v => v.currentTime") == context_start
            with page.expect_download() as downloaded:
                page.locator("#export-json").click()
            exported = json.loads(downloaded.value.path().read_text(encoding="utf-8"))
            clip = exported["selectedClips"][0]
            assert (clip["startUs"], clip["endUs"]) == (row["startUs"], row["endUs"])
            assert clip["evidenceIds"] == row["evidenceIds"]
            assert clip["eventId"] == row["eventId"]

            page.locator("#play-selection").click()
            assert page.locator("#source-video").evaluate("v => v.currentTime") == start
            playwright.expect(page.locator("#playback-range")).to_contain_text("原区间")
            page.locator("#source-video").evaluate(
                "(v, time) => {v.currentTime=time; v.dispatchEvent(new Event('timeupdate'));}",
                end + 0.1,
            )
            assert page.locator("#source-video").evaluate("v => v.currentTime") == end
            assert len([url for url in calls if "/api/inspect?" in url]) == source_calls
            assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize("invalid", ["interval", "source"])
def test_context_refuses_invalid_interval_or_unregistered_source(tmp_path, monkeypatch, invalid):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_project(tmp_path)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.add_init_script(PLAYER)

            def invalid_fixture(route):
                response = route.fetch()
                payload = response.json()
                if invalid == "interval":
                    payload["timeline"][0]["endUs"] = payload["media"]["durationUs"] + 1
                else:
                    payload["media"]["videoUrl"] = "https://example.invalid/foreign.mp4"
                route.fulfill(response=response, json=payload)

            page.route("**/api/inspect?**", invalid_fixture)
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").dispatch_event("click")
            playwright.expect(page.locator("#play-context")).to_be_disabled()
            assert page.locator("#playback-range").inner_text() == ""
        finally:
            browser.close()


def test_candidate_context_clears_on_refresh_and_scrubbing_releases_stop(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_project(tmp_path)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.add_init_script(PLAYER)
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("白色")
            page.locator("#search-button").click()
            playwright.expect(page.locator("#candidate-count")).to_have_text("1")
            page.locator("#candidate-list .clip-preview").click()
            page.locator("#play-context").click()
            playwright.expect(page.locator("#active-title")).to_have_text("候选 #1")
            page.locator("#video-scrubber").evaluate(
                "node => {node.value='1.9'; node.dispatchEvent(new Event('input', {bubbles:true}));}"
            )
            page.locator("#source-video").dispatch_event("timeupdate")
            assert page.locator("#source-video").evaluate("v => v.currentTime") == 1.9
            playwright.expect(page.locator("#playback-range")).to_have_text("自由回看")
            page.locator("#refresh-view").click()
            playwright.expect(page.locator("#play-context")).to_be_disabled()
            playwright.expect(page.locator("#playback-range")).to_have_text("")
        finally:
            browser.close()
