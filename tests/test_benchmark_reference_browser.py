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
