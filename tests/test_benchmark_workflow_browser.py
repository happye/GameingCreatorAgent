"""The HTTP entry opens existing forms, plays registered footage and recovers progress."""

import json
from pathlib import Path

import pytest
from test_benchmark_reference_browser import (
    reference_page,  # noqa: F401 - shared actual MP4 fixture
)
from test_inspection_http import workspace

from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.infrastructure.benchmark_review_files import publish_review_bundle
from gamingcreator.ui.benchmark_review import render_benchmark_review
from gamingcreator.ui.benchmark_workflow import BenchmarkWorkflows


@pytest.mark.parametrize("width", [1366, 390])
def test_workspace_flow_forms_playback_download_import_and_reload(tmp_path, request, width):
    playwright = pytest.importorskip("playwright.sync_api")
    _, context, _, _ = request.getfixturevalue("reference_page")
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900}, accept_downloads=True)
            errors, foreign = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: (
                    foreign.append(item.url)
                    if not item.url.startswith((base, "blob:", "data:"))
                    else None
                ),
            )
            page.goto(base + "/acceptance")
            page.locator("#workflow-name").fill("程序流程 <script>不执行</script>")
            page.locator("#create-workflow").click()
            playwright.expect(page.locator("#current-name")).to_contain_text(
                "<script>不执行</script>"
            )
            identifier = page.url.split("#")[1]
            register = page.locator("[data-step=register]")
            register.locator("button[type=submit]").click()
            link = register.get_by_role("link", name="打开登记表单", exact=True)
            playwright.expect(link).to_be_visible(timeout=15000)
            with page.expect_popup() as pending:
                link.click()
            editor = pending.value
            playwright.expect(editor.locator("#dataset-id")).to_be_visible()
            assert editor.locator(".source-row").count() == 0
            editor.close()
            reference = page.locator("[data-step=references]")
            reference.locator("input[type=file]").set_input_files(
                {
                    "name": "计划.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(context["plan"]).encode(),
                }
            )
            reference.locator("button[type=submit]").click()
            link = reference.get_by_role("link", name="打开原片标注页", exact=True)
            playwright.expect(link).to_be_visible(timeout=15000)
            with page.expect_popup() as pending:
                link.click()
            editor = pending.value
            editor.on("pageerror", lambda error: errors.append(str(error)))
            editor.wait_for_function("() => document.querySelector('video').readyState >= 2")
            editor.locator("video").evaluate("video => {video.currentTime=.1;return video.play();}")
            editor.wait_for_function("() => document.querySelector('video').currentTime > .2")
            editor.locator("video").evaluate("video => video.pause()")
            assert (
                editor.locator("video")
                .evaluate("video => video.currentSrc")
                .startswith(base + "/api/benchmark-source?")
            )
            with editor.expect_download() as pending:
                editor.locator("#download-record").click()
            data = Path(pending.value.path()).read_bytes()
            assert json.loads(data)["plan"]["humanReferences"]["confirmed"] is False
            editor.close()
            imported = page.locator("[data-step=references-import]")
            imported.locator("input[type=file]").set_input_files(
                {"name": "标注.json", "mimeType": "application/json", "buffer": data}
            )
            imported.locator("button[type=submit]").click()
            playwright.expect(imported.get_by_role("link", name="下载待冻结计划")).to_be_visible(
                timeout=15000
            )
            playwright.expect(register.locator("button[type=submit]")).to_be_disabled()
            page.reload()
            playwright.expect(page.locator("#current-name")).to_contain_text("程序流程")
            assert page.locator("#workflow-select").input_value() == identifier
            playwright.expect(
                page.locator("[data-step=freeze] button[type=submit]")
            ).to_be_enabled()
            assert page.locator("#overall").inner_text().endswith("检索质量尚未验证")
            page.locator("[data-step=freeze] button[type=submit]").click()
            # tmp repository has no toolchain: failure is retained, with an explicit retry button.
            playwright.expect(page.locator("[data-step=freeze] .failed")).to_be_visible(
                timeout=15000
            )
            playwright.expect(
                page.locator("[data-step=freeze] button[type=submit]")
            ).to_be_enabled()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors and not foreign
            other = page.request.post(
                base + "/api/benchmark-workflows", data={"name": "另一个独立流程"}
            ).json()
            page.locator("#refresh").click()
            playwright.expect(page.locator("#workflow-select option")).to_have_count(3)
            page.locator("#workflow-select").select_option(other["id"])
            playwright.expect(page.locator("#current-name")).to_have_text("另一个独立流程")
            assert page.locator("[data-step=references-import] button[type=submit]").is_disabled()
            assert page.locator("#history .record").count() == 0
        finally:
            browser.close()


def test_http_candidate_relative_url_seeks_plays_and_pauses_at_original_end(
    tmp_path, request, monkeypatch
):
    from test_benchmark_review import build, review_fixture
    from test_benchmark_workflow import submit

    playwright = pytest.importorskip("playwright.sync_api")
    _, _, _, assets = request.getfixturevalue("reference_page")
    asset = assets["source-0"]
    fixture_directory = tmp_path / "candidate-fixture"
    fixture_directory.mkdir()
    candidate, template = build(review_fixture(fixture_directory, 2))
    media = candidate["media"][0]
    media.update(
        {
            "path": str(asset.source_path),
            "durationUs": asset.duration_us,
            "originSeconds": str(asset.origin_seconds),
            "automaticPlaybackSupported": asset.origin_seconds == 0,
        }
    )
    source = next(row for row in candidate["manifest"]["media"] if row["runId"] == media["runId"])
    source["sha256"] = asset.sha256
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "程序播放夹具，无人评"})["id"]

    def prepared(identifier, row, fields, rows):
        publish_review_bundle(
            manager._output(identifier, row),
            {
                "context.json": canonical_json(candidate),
                "record-template.json": canonical_json(template),
                "review.html": render_benchmark_review(candidate, template).encode(),
            },
            [],
        )
        return 0, None

    monkeypatch.setattr(manager, "_execute", prepared)
    value = submit(manager, identifier, "register", {"inputText": ""})
    row = value["attempts"][-1]
    from urllib.parse import urlencode

    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(
                base
                + "/api/benchmark-file?"
                + urlencode(
                    {"workflow": identifier, "attempt": row["attemptId"], "file": "review.html"}
                )
            )
            page.get_by_role("button", name="播放此区间", exact=True).first.click()
            page.wait_for_function("()=>document.querySelector('video').readyState>=2")
            page.wait_for_function(
                "()=>document.querySelector('#play-state').textContent.includes('第1位')"
            )
            slot = candidate["queries"][0]["slots"][0]
            end = slot["endUs"] / 1_000_000
            page.wait_for_function(
                "end=>document.querySelector('video').paused && document.querySelector('video').currentTime>=end",
                arg=end,
                timeout=10000,
            )
            assert page.locator("video").evaluate("video=>video.currentTime") < end + 0.6
            assert page.locator("[data-field=grade]").first.input_value() == ""
        finally:
            browser.close()
