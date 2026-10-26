"""Synthetic raw-video editing; no actual human reference or quality claims."""

import asyncio
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from test_benchmark_preparation import plan_fixture

from gamingcreator.application.benchmark_preparation import canonical_json, loads_plan
from gamingcreator.application.benchmark_reference_review import (
    build_reference_context,
    validate_reference_record,
)
from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.ui.benchmark_reference_review import render_reference_review

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"


@pytest.fixture
def reference_page(tmp_path):
    if not FFMPEG.is_file():
        pytest.skip("Project-local FFmpeg not prepared")
    source = tmp_path / "原片 中文 空格.mp4"
    subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x96:rate=30:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    asset = asyncio.run(FfmpegMediaProcessor(ROOT).probe(source, CancellationContext("test", 15)))
    raw, _ = plan_fixture(tmp_path)
    raw["sources"][0]["path"] = str(source)
    second = {
        **deepcopy(raw["queries"][0]),
        "id": "query-second",
        "text": "寻找射击片段",
        "family": "second-family",
    }
    raw["queries"].append(second)
    assets = {"source-0": asset}
    context, template = build_reference_context(
        loads_plan(json.dumps(raw)), assets, "2026-10-07T10:00:00+08:00"
    )
    assert context["media"][0]["automaticTimeCapture"] is True
    page_path = tmp_path / "原片 标注.html"
    page_path.write_text(render_reference_review(context, template), encoding="utf-8")
    return page_path, context, template, assets


@pytest.mark.parametrize("width", [1366, 390])
def test_real_file_player_manual_ranges_download_load_and_late_edit_guard(reference_page, width):
    playwright = pytest.importorskip("playwright.sync_api")
    page_path, context, template, assets = reference_page
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            requests, errors = [], []
            page.on(
                "request",
                lambda request: (
                    requests.append(request.url)
                    if not request.url.startswith(("file:", "data:", "blob:"))
                    else None
                ),
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(page_path.as_uri())
            page.wait_for_function("() => document.getElementById('source-video').readyState >= 1")
            assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
            assert not page.locator("#confirmed").is_checked()
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            assert json.loads(Path(pending.value.path()).read_bytes()) == template
            page.locator("#source-video").evaluate("video => { video.currentTime = 0.25; }")
            page.wait_for_function(
                "() => Math.abs(document.getElementById('source-video').currentTime - 0.25) < 0.01"
            )
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.250000")
            page.locator("#end-seconds").fill("1.000000")
            page.locator("#event-id").fill("fixture-action")
            page.locator("#event-group").fill("fixture-same-action")
            page.locator("#reason").fill("Synthetic browser fixture, not human acceptance.")
            page.locator("#add-reference").click()
            playwright.expect(page.locator(".slot")).to_have_count(1)
            page.locator("#start-seconds").fill("1.250000")
            page.locator("#end-seconds").fill("1.500000")
            page.locator("#add-reference").click()
            playwright.expect(page.locator(".slot p").first).to_contain_text("1.250000–1.500000")
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            data = Path(pending.value.path()).read_bytes()
            validated = validate_reference_record(data, context, assets)
            assert len(validated["plan"]["queries"][0]["referenceEvents"][0]["usableRanges"]) == 2
            page.locator("#query-select").select_option("1")
            playwright.expect(page.locator(".slot")).to_have_count(0)
            page.locator("#query-select").select_option("0")
            playwright.expect(page.locator(".slot")).to_have_count(1)
            invalid = deepcopy(validated)
            invalid["plan"]["sources"][0]["modelResultsViewed"] = True
            page.locator("#load-record").set_input_files(
                {
                    "name": "wrong.json",
                    "mimeType": "application/json",
                    "buffer": canonical_json(invalid),
                }
            )
            playwright.expect(page.locator("#status")).to_contain_text("当前标注保持")
            playwright.expect(page.locator(".slot")).to_have_count(1)
            page.locator("#load-record").set_input_files(
                {"name": "saved.json", "mimeType": "application/json", "buffer": data}
            )
            playwright.expect(page.locator("#status")).to_contain_text("已有标注已载入")
            page.evaluate("""() => {
                const original = File.prototype.text;
                File.prototype.text = function() {
                    if (this.name !== 'delayed.json') return original.call(this);
                    return new Promise(resolve => { window.finishReferenceLoad = () => original.call(this).then(resolve); });
                };
            }""")
            page.locator("#load-record").set_input_files(
                {"name": "delayed.json", "mimeType": "application/json", "buffer": data}
            )
            page.locator("#reason").fill("Preserve this new edit")
            page.evaluate("() => window.finishReferenceLoad()")
            playwright.expect(page.locator("#status")).to_contain_text("保留当前内容")
            playwright.expect(page.locator("#reason")).to_have_value("Preserve this new edit")
            assert not requests and not errors
        finally:
            browser.close()


def test_two_event_names_cannot_share_one_action_group(reference_page):
    playwright = pytest.importorskip("playwright.sync_api")
    page_path, _, _, _ = reference_page
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.goto(page_path.as_uri())
            for name, start, end in (
                ("first-name", "0.100000", "0.500000"),
                ("second-name", "1.000000", "1.500000"),
            ):
                page.locator("#start-seconds").fill(start)
                page.locator("#end-seconds").fill(end)
                page.locator("#event-id").fill(name)
                page.locator("#event-group").fill("one-action")
                page.locator("#reason").fill("Synthetic browser fixture, not human acceptance.")
                page.locator("#add-reference").click()
            # Freezing rejects a shared group, so the page refuses it with the reason.
            playwright.expect(page.locator(".slot")).to_have_count(1)
            playwright.expect(page.locator("#status")).to_contain_text("已由另一个事件名称使用")
        finally:
            browser.close()


def test_progress_coverage_overlap_warning_and_keyboard_keep_the_record_format(reference_page):
    playwright = pytest.importorskip("playwright.sync_api")
    page_path, context, _, assets = reference_page
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(page_path.as_uri())
            playwright.expect(page.locator("#reference-summary")).to_contain_text("0/10")
            playwright.expect(page.locator("#coverage-note")).to_contain_text("还没有登记")
            page.wait_for_function("() => !document.getElementById('capture-start').disabled")
            # Keyboard marking reuses the guarded capture buttons.
            page.locator("#source-video").evaluate("video => { video.currentTime = 0.25; }")
            page.wait_for_function(
                "() => Math.abs(document.getElementById('source-video').currentTime - 0.25) < 0.01"
            )
            page.locator("body").press("i")
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.250000")
            page.locator("body").press("]")
            playwright.expect(page.locator("#playback-rate")).to_have_text("1.5")
            assert page.locator("#source-video").evaluate("video => video.playbackRate") == 1.5
            # Typing in a field never triggers the shortcuts.
            page.locator("#event-id").fill("")
            page.locator("#event-id").press("i")
            playwright.expect(page.locator("#event-id")).to_have_value("i")

            def add(name, group, start, end):
                page.locator("#start-seconds").fill(start)
                page.locator("#end-seconds").fill(end)
                page.locator("#event-id").fill(name)
                page.locator("#event-group").fill(group)
                page.locator("#reason").fill("Synthetic browser fixture, not human acceptance.")
                page.locator("#add-reference").click()

            add("first-action", "group-a", "0.250000", "1.000000")
            playwright.expect(page.locator("#reference-summary")).to_contain_text("1/10")
            playwright.expect(page.locator("#reference-summary")).to_contain_text("还差 9 个")
            playwright.expect(page.locator(".coverage-block.current")).to_have_count(1)
            # A different event overlapping the first is warned once, then accepted.
            add("second-action", "group-b", "0.800000", "1.500000")
            playwright.expect(page.locator("#status")).to_contain_text("重叠")
            playwright.expect(page.locator(".slot")).to_have_count(1)
            page.locator("#add-reference").click()
            playwright.expect(page.locator(".slot")).to_have_count(2)
            # More ranges of the same event never warn.
            add("first-action", "group-a", "1.600000", "1.900000")
            playwright.expect(page.locator(".coverage-block")).to_have_count(3)
            # Clicking a block seeks the player to that interval's source start.
            page.locator(".coverage-block[aria-label*='second-action']").click()
            page.wait_for_function(
                "() => Math.abs(document.getElementById('source-video').currentTime - 0.8) < 0.01"
            )
            # Another query on the same recording shows these ranges in grey.
            page.locator("#query-select").select_option("1")
            playwright.expect(page.locator(".coverage-block")).to_have_count(3)
            playwright.expect(page.locator(".coverage-block.current")).to_have_count(0)
            # The reloaded player keeps the chosen speed and the label follows the player.
            page.wait_for_function("() => document.getElementById('source-video').readyState >= 1")
            rate = page.locator("#source-video").evaluate("video => video.playbackRate")
            assert rate == 1.5
            playwright.expect(page.locator("#playback-rate")).to_have_text("1.5")
            page.locator("#query-select").select_option("0")
            # A ticked checkbox keeps focus but does not swallow the shortcuts.
            page.wait_for_function("() => !document.getElementById('capture-start').disabled")
            page.locator("#start-seconds").fill("")
            page.locator("#reviewed").click()
            page.locator("#reviewed").press("i")
            assert page.locator("#start-seconds").input_value() != ""
            page.locator("#reviewed").click()
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            validated = validate_reference_record(
                Path(pending.value.path()).read_bytes(), context, assets
            )
            events = validated["plan"]["queries"][0]["referenceEvents"]
            assert [len(row["usableRanges"]) for row in events] == [2, 1]
            assert not errors
        finally:
            browser.close()
