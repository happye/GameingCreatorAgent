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
            # Re-running a finished step 2 warns first: the saved record would not import into
            # a new page. Dismissing keeps the current page and starts nothing.
            attempts = page.locator("#history .record").count()
            dialogs = []
            page.once("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
            reference.locator("button[type=submit]").click()
            page.wait_for_timeout(500)
            assert dialogs and "旧页面包" in dialogs[0]
            assert page.locator("#history .record").count() == attempts
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
            overall = page.locator("#overall").inner_text()
            assert " · 检索质量尚未验证 · " in overall
            assert overall.endswith("验收就绪只是资格汇总，不等于已验收或 F006 通过。")
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


@pytest.mark.parametrize("width", [1366, 390])
def test_freeze_step_shows_inventory_coverage_upload_and_legacy_notice(
    tmp_path, request, monkeypatch, width
):
    from test_benchmark_inventory_binding import FIXED_TIME, encode, report_for
    from test_benchmark_workflow import freeze_row, references_imported

    import gamingcreator.ui.benchmark_workflow as workflow_module
    from gamingcreator.application.benchmark_preparation import freeze_document, loads_plan
    from gamingcreator.infrastructure.benchmark_preparation_files import write_freeze

    playwright = pytest.importorskip("playwright.sync_api")
    manager, covered, assets = references_imported(tmp_path, request, monkeypatch)
    report = report_for(assets, extra=["e" * 64], pairs=[(1, 2)])
    freeze_row(manager, covered, {"inputText": encode(report).decode()})
    uploaded = references_imported(tmp_path, request, monkeypatch)[1]
    missing = references_imported(tmp_path, request, monkeypatch)[1]
    freeze_row(manager, missing, {})
    legacy = references_imported(tmp_path, request, monkeypatch)[1]

    async def legacy_freeze(input_path, output, repository, inventory_path=None):
        data = input_path.read_bytes()
        frozen = freeze_document(loads_plan(data.decode()), assets, FIXED_TIME)
        write_freeze(input_path, data, frozen, output)
        return {}

    with monkeypatch.context() as patch:
        patch.setattr(workflow_module, "execute_freeze_benchmark", legacy_freeze)
        freeze_row(manager, legacy, {})

    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
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
            freeze = page.locator("[data-step=freeze]")

            def open_workflow(identifier):
                page.goto(base + "/acceptance#" + identifier)
                page.reload()
                playwright.expect(page.locator("#current-name")).to_have_text("冻结盘点")

            open_workflow(covered)
            playwright.expect(freeze.locator(".inventory table")).to_be_visible(timeout=15000)
            assert "已比较" in freeze.locator(".inventory table").inner_text()
            text = freeze.locator(".inventory").inner_text()
            assert "盘点报告来源：上传的盘点报告" in text
            assert "另有 1 处证据涉及未登记的来源" in text
            assert "未匹配不证明独立" in text
            # Blockers read as plain guidance, with the code kept only for diagnosis.
            assert "独立录制组不足10个" in text
            assert "（representative_recordings_below_ten）" in text
            playwright.expect(
                freeze.get_by_role("link", name="查看素材盘点报告", exact=True)
            ).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

            open_workflow(missing)
            playwright.expect(freeze.locator(".inventory .failed")).to_contain_text(
                "没有报告不等于素材独立", timeout=15000
            )
            assert freeze.locator(".inventory table").count() == 0
            assert "盘点报告来源：未提供" in freeze.locator(".inventory").inner_text()

            open_workflow(legacy)
            playwright.expect(freeze.locator(".inventory")).to_contain_text(
                "旧版冻结：未核对素材盘点", timeout=15000
            )

            open_workflow(uploaded)
            freeze.locator("input[type=file]").set_input_files(
                {
                    "name": "盘点.json",
                    "mimeType": "application/json",
                    "buffer": encode(report_for(assets)),
                }
            )
            freeze.locator("button[type=submit]").click()
            playwright.expect(freeze.locator(".inventory table")).to_be_visible(timeout=20000)
            assert (
                "未发现共用画面证据（无证据，不等于独立）"
                in freeze.locator(".inventory").inner_text()
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors and not foreign
        finally:
            browser.close()


@pytest.mark.parametrize("width", [1366, 390])
def test_freeze_step_auto_inventory_checkbox_defaults_on_excludes_upload_and_shows_origin(
    tmp_path, request, monkeypatch, width
):
    from test_benchmark_inventory_binding import encode, report_for
    from test_benchmark_workflow import fake_auto_inventory, references_imported

    playwright = pytest.importorskip("playwright.sync_api")
    manager, identifier, assets = references_imported(tmp_path, request, monkeypatch)
    calls = fake_auto_inventory(monkeypatch, assets)
    del manager
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors, foreign, posted = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: (
                    foreign.append(item.url)
                    if not item.url.startswith((base, "blob:", "data:"))
                    else (
                        posted.append(json.loads(item.post_data))
                        if item.url.endswith("/api/benchmark-step")
                        else None
                    )
                ),
            )
            page.goto(base + "/acceptance#" + identifier)
            page.reload()
            playwright.expect(page.locator("#current-name")).to_have_text("冻结盘点")
            freeze = page.locator("[data-step=freeze]")
            box = freeze.locator("#auto-inventory")
            playwright.expect(box).to_be_checked()
            playwright.expect(freeze).to_contain_text("冻结时自动盘点登记的录像")
            report = {
                "name": "盘点.json",
                "mimeType": "application/json",
                "buffer": encode(report_for(assets)),
            }
            file_input = freeze.locator("input[type=file]")
            file_input.set_input_files(report)  # choosing a report switches automatic off
            playwright.expect(box).not_to_be_checked()
            box.check()  # and checking automatic again drops the chosen report
            assert file_input.evaluate("node=>node.files.length") == 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            freeze.locator("button[type=submit]").click()
            playwright.expect(freeze.locator(".inventory table")).to_be_visible(timeout=20000)
            playwright.expect(freeze.locator(".inventory")).to_contain_text(
                "盘点报告来源：自动盘点", timeout=15000
            )
            assert [item["fields"] for item in posted] == [
                {"inputText": "", "autoInventory": "true"}
            ]
            assert len(calls) == 1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors and not foreign
        finally:
            browser.close()
