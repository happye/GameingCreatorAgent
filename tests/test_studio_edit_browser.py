"""Studio Edit workspace against the real HTTP server and job system (planner/renderer faked).

Protects the user flow, not the DOM: brief → plans → choose → export → downloadable video,
plus the draft surviving a reload.
"""

import json
import re
import threading

import pytest
from test_clip_replacement_jobs import framed_replacements, replacements  # noqa: F401
from test_creation_jobs import service  # noqa: F401
from test_creation_revision_jobs import revisions  # noqa: F401
from test_narration_jobs import engine, narrated  # noqa: F401

from gamingcreator.ui.server import create_server


def test_brief_to_exported_video(service, monkeypatch):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.creation_jobs as implementation
    import gamingcreator.ui.server as server_module
    from gamingcreator.infrastructure.creation_files import write_creation

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "status": "completed",
                    "sourceName": "测试录像",
                    "completedEligible": True,
                    "durationUs": 9_000_000,
                }
            ]
        }

    async def planner(
        project, runs_, brief, output, events, fps, selection, preferences=None, edit_kinds=None
    ):
        segment = {
            "runId": "run",
            "eventId": "e",
            "outputFrames": 60,
            "evidenceIds": [],
            "scriptDraft": "测试镜头",
            "sourcePath": "private",
        }
        plans = [
            {
                "id": "showcase",
                "structure": "推荐模板",
                "mode": "feature_showcase",
                "ready": True,
                "gaps": [],
                "scriptStatus": "draft",
                "segments": [
                    {**segment, "startUs": 0, "endUs": 2_000_000},
                    {**segment, "startUs": 4_000_000, "endUs": 6_000_000},
                ],
            },
            {
                "id": "reverse",
                "structure": "倒序",
                "ready": False,
                "gaps": ["主题缺少已保存文字证据：Boss战"],
                "scriptStatus": "draft",
                "segments": [{**segment, "startUs": 0, "endUs": 2_000_000}],
            },
        ]
        write_creation(
            output,
            {
                "plans.json": {
                    "schemaVersion": "creation-plan-v1",
                    "fps": fps,
                    "brief": json.loads(brief.read_text()),
                    "plans": plans,
                }
            },
            (),
        )

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    monkeypatch.setattr(implementation, "execute_plan_creation", planner)
    server = create_server("127.0.0.1", 0, service.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/studio")
            # Render wait estimate: median seconds-per-output-second of recent renders.
            rates = page.evaluate(
                """async () => {
                    const {renderRate} = await import("/assets/studio/edit.js");
                    const job = (start, end, length, kind = "render") => ({kind, status: "completed",
                        createdAt: start, updatedAt: end, video: {durationSeconds: length}});
                    const t = (s) => new Date(Date.UTC(2026, 0, 1, 0, 0, s)).toISOString();
                    return [
                        renderRate([]),
                        renderRate([job(t(0), t(20), 10), job(t(0), t(30), 10), job(t(0), t(900), 10),
                            job(t(0), t(10), 10), job(t(0), "bad", 10), job(t(0), t(50), 10, "plan")]),
                    ];
                }"""
            )
            assert rates == [None, 2]
            page.get_by_role("tab", name="剪辑").click()
            # P019: one sentence fills only the fields it states, after an explicit click.
            page.get_by_label("一句话需求", exact=True).fill(
                "给新玩家做《句子游戏》30秒高光，发抖音"
            )
            page.get_by_role("button", name="解析", exact=True).click()
            playwright.expect(page.get_by_role("status", name="一句话需求状态")).to_contain_text(
                "时长：30 秒"
            )
            page.get_by_role("button", name="填入需求").click()
            playwright.expect(page.locator(".brief input.input").first).to_have_value("句子游戏")
            playwright.expect(page.get_by_label("秒数")).to_have_value("30")
            playwright.expect(page.locator(".brief select").first).to_have_value("highlight")
            page.locator(".brief .runs input[type=checkbox]").check()
            page.locator(".brief input.input").first.fill("测试游戏")
            page.get_by_role("button", name="生成方案").click()
            playwright.expect(page.locator(".plan")).to_have_count(2)
            # A plan with gaps cannot be chosen; the ready one is selected and previewable.
            playwright.expect(page.locator(".plan").nth(1)).to_be_disabled()
            playwright.expect(page.locator(".plan").first).to_have_attribute("aria-current", "true")
            playwright.expect(page.locator(".timeline .clip")).to_have_count(2)
            # Subtitle style is offered only for burned subtitles and travels with the export.
            page.get_by_role("tab", name="导出").click()
            style = page.locator("select:has(option[value=boxed])")
            playwright.expect(style).to_have_count(0)
            page.locator("select:has(option[value=burn])").select_option("burn")
            style.select_option("boxed")
            with page.expect_request(
                lambda r: r.method == "POST" and r.url.endswith("/api/creation/renders")
            ) as submitted:
                page.get_by_role("button", name="导出成片").click()
            body = json.loads(submitted.value.post_data)
            assert body["subtitleMode"] == "burn" and body["subtitleStyle"] == "boxed"
            playwright.expect(page.locator("a[download]")).to_have_attribute(
                "href", re.compile(r"^/api/creation/jobs/[0-9a-f]{32}/video\?download=1$")
            )
            # J1 fourth trial: a bare `download` attribute became download="true" in htm,
            # so the browser saved the file as "true". The real click must save an MP4.
            with page.expect_download() as pending:
                page.locator("a[download]").click()
            assert pending.value.suggested_filename.endswith(".mp4")
            assert page.locator("a[download]").get_attribute("download").endswith(".mp4")
            assert pending.value.failure() is None
            # The page never scrolls; panels do.
            assert page.evaluate("document.documentElement.scrollHeight <= innerHeight")
            # A render still running when the page reloads stays visible and blocks re-export.
            running_id = re.search(
                r"jobs/([0-9a-f]{32})/video", page.locator("a[download]").get_attribute("href")
            ).group(1)

            def still_running(route):
                body = route.fetch().json()
                body.update(status="running")
                body.pop("artifact", None)
                route.fulfill(json=body)

            page.route(f"**/api/creation/jobs/{running_id}", still_running)
            page.reload()
            playwright.expect(page.get_by_text("正在生成成片（已用")).to_be_visible()
            playwright.expect(page.get_by_role("button", name="正在生成…")).to_be_disabled()
            page.unroute(f"**/api/creation/jobs/{running_id}")
            playwright.expect(page.locator("a[download]")).to_be_visible()
            # The brief survives a reload, and the last result reopens.
            page.reload()
            playwright.expect(page.locator(".brief input.input").first).to_have_value("测试游戏")
            playwright.expect(page.locator("a[download]")).to_be_visible()
            # Reopening a video brings back its plans, and export stays on screen.
            playwright.expect(page.locator(".plan")).to_have_count(2)
            export = page.get_by_role("button", name="导出成片")
            playwright.expect(export).to_be_enabled()
            assert export.evaluate("e => e.getBoundingClientRect().bottom <= innerHeight")
            # After export, "去发布" opens exactly this render in Publish.
            render_id = re.search(
                r"jobs/([0-9a-f]{32})/video", page.locator("a[download]").get_attribute("href")
            ).group(1)
            with page.expect_request(lambda r: f"/jobs/{render_id}/publication" in r.url):
                page.get_by_role("button", name="去发布：写标题和封面").click()
            playwright.expect(page.get_by_role("tab", name="发布")).to_have_attribute(
                "aria-selected", "true"
            )
            page.get_by_role("tab", name="剪辑").click()
            # P024: a missing topic offers a one-click search in the Assets workspace.
            page.get_by_role("button", name="在素材里找「Boss战」").click()
            playwright.expect(page.get_by_role("tab", name="素材")).to_have_attribute(
                "aria-selected", "true"
            )
            playwright.expect(page.get_by_label("搜索片段")).to_have_value("Boss战")
            # Work lists use Chinese states and mark the newest finished item.
            playwright.expect(
                page.locator(".row .meta", has_text="最新 · 打开").first
            ).to_be_visible()
            # Finished renders show their frame size so attempts can be told apart.
            playwright.expect(page.locator(".video-facts").first).to_contain_text("横屏 1280×720")
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_edit_clip_save_version_and_command(revisions, monkeypatch):  # noqa: F811
    """Clip edits save as a version that reopens after a reload; commands preview first."""
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as server_module

    jobs, root, _ = revisions

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "status": "completed",
                    "sourceName": "录像",
                    "completedEligible": True,
                }
            ]
        }

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    server = create_server("127.0.0.1", 0, jobs.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
    last = json.dumps({"artifacts/project": {"id": root, "kind": "plan"}})
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(
                f"if (!sessionStorage.seeded) {{ sessionStorage.seeded = 1;"
                f" localStorage.setItem('studio-v1', {prefs!r}); localStorage.setItem('studio-last-job-v1', {last!r}); }}"
            )
            page.goto(base + "/studio")
            clips = page.locator(".timeline .clip")
            playwright.expect(page.get_by_text("方案原样")).to_be_visible()
            playwright.expect(page.get_by_label("版本保存状态")).to_have_text(
                "修改镜头、声音或叠加后可保存新版本"
            )
            playwright.expect(page.get_by_role("button", name="保存版本")).to_be_disabled()
            # Step undo/redo: Delete a shot, Ctrl+Z brings it back clean, Ctrl+Shift+Z redoes.
            count = clips.count()
            clips.nth(1).click()
            # Delete acts on the selection; wait until the click has selected the clip.
            playwright.expect(clips.nth(1)).to_have_attribute("aria-current", "true")
            page.keyboard.press("Delete")
            playwright.expect(clips).to_have_count(count - 1)
            page.keyboard.press("Control+z")
            playwright.expect(clips).to_have_count(count)
            playwright.expect(page.get_by_text("方案原样")).to_be_visible()
            page.keyboard.press("Control+Shift+z")
            playwright.expect(clips).to_have_count(count - 1)
            page.get_by_role("button", name="撤销一步").click()
            playwright.expect(clips).to_have_count(count)
            playwright.expect(page.get_by_role("button", name="撤销一步")).to_be_disabled()
            playwright.expect(page.get_by_role("button", name="重做")).to_be_enabled()
            # J1 2026-11-11: drag the selected shot's edge to trim it; one drag = one undo step.
            clips.nth(1).click()
            out_point = page.get_by_label("出点", exact=True)
            before_text = out_point.input_value()
            before = float(before_text)
            handle = page.get_by_label("拖动裁剪出点").bounding_box()
            x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x - 30, y, steps=3)
            page.mouse.move(x - 60, y, steps=3)
            page.mouse.up()
            playwright.expect(out_point).not_to_have_value(before_text)
            assert 3.0 < float(out_point.input_value()) < before
            page.get_by_role("button", name="撤销一步").click()
            playwright.expect(out_point).to_have_value(before_text)
            # Stage C: click the volume line to add a keyframe, drag it down; each is one step.
            line = page.get_by_label("原声音量线")
            box = line.bounding_box()
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + 4)
            point = line.get_by_role("slider")
            playwright.expect(point).to_have_count(1)
            assert point.get_attribute("aria-valuenow") == "0"
            dot = point.bounding_box()
            cx, cy = dot["x"] + dot["width"] / 2, dot["y"] + dot["height"] / 2
            page.mouse.move(cx, cy)
            page.mouse.down()
            page.mouse.move(cx, cy + 8, steps=3)
            page.mouse.move(cx, cy + 14, steps=3)
            page.mouse.up()
            playwright.expect(point).to_have_count(1)  # releasing the drag adds nothing
            assert float(point.get_attribute("aria-valuenow")) < -10
            page.get_by_role("button", name="撤销一步").click()
            playwright.expect(point).to_have_attribute("aria-valuenow", "0")
            page.get_by_role("button", name="撤销一步").click()
            playwright.expect(point).to_have_count(0)
            page.get_by_role("tab", name="导出", exact=True).click()
            for label, suffix in [
                ("下载 FCPXML", ".fcpxml"),
                ("下载 OTIO", ".otio"),
                ("下载 Premiere XML", "-premiere.xml"),
            ]:
                with page.expect_download() as pending:
                    page.get_by_role("button", name=label, exact=True).click()
                download = pending.value
                assert download.suggested_filename.endswith(suffix)
                assert download.failure() is None
            page.route(
                "**/timeline?**",
                lambda route: route.fulfill(
                    status=403,
                    content_type="application/json",
                    body='{"error":{"message":"套餐不允许时间线导出"}}',
                ),
            )
            page.get_by_role("button", name="下载 Premiere XML", exact=True).click()
            playwright.expect(page.get_by_label("时间线下载状态")).to_have_text(
                "套餐不允许时间线导出"
            )
            page.unroute("**/timeline?**")
            pending_routes, downloads = [], []
            page.on("download", lambda download: downloads.append(download))
            page.route("**/timeline?**", lambda route: pending_routes.append(route))
            page.get_by_role("button", name="下载 Premiere XML", exact=True).click()
            page.wait_for_timeout(100)
            assert pending_routes
            page.get_by_role("tab", name="镜头", exact=True).click()

            clips.nth(1).click()
            page.get_by_label("速度").select_option("2/1")
            playwright.expect(page.locator(".clip-speed")).to_have_text("2×")
            # Changing the draft while a response waits must never download an old base.
            pending_routes[0].fulfill(status=200, content_type="application/xml", body="<xmeml/>")
            page.wait_for_timeout(100)
            assert not downloads
            page.unroute("**/timeline?**")
            page.get_by_role("tab", name="导出", exact=True).click()
            playwright.expect(
                page.get_by_role("button", name="下载 Premiere XML", exact=True)
            ).to_be_disabled()
            playwright.expect(page.get_by_label("时间线下载状态")).to_have_text("请先保存版本")
            # With a clip selected, sound and export stay one tab away.
            page.get_by_role("tab", name="声音").click()
            playwright.expect(page.get_by_role("button", name="起草旁白稿")).to_be_visible()
            page.get_by_role("tab", name="镜头").click()
            page.get_by_role("button", name="保存版本").click()
            playwright.expect(page.get_by_text("已保存的版本")).to_be_visible()
            page.reload()
            playwright.expect(page.get_by_text("已保存的版本")).to_be_visible()
            playwright.expect(page.locator(".clip-speed")).to_have_text("2×")
            # A one-line command previews first; only the clip it changes is highlighted.
            page.get_by_label("一句话修改镜头").fill("第1个镜头慢放")
            page.get_by_role("button", name="预览改动").click()
            playwright.expect(page.locator(".timeline .clip.changed")).to_have_count(1)
            playwright.expect(page.get_by_label("版本保存状态")).to_have_text(
                "请先应用或取消创作助手的改动"
            )
            playwright.expect(page.get_by_role("button", name="保存版本")).to_be_disabled()
            # Export says why it is unavailable, visibly, not only in a tooltip.
            playwright.expect(page.get_by_role("status", name="导出状态")).to_have_text(
                "先应用或取消一句话修改"
            )
            playwright.expect(page.get_by_role("button", name="导出成片")).to_be_disabled()
            page.get_by_role("button", name="应用").click()
            playwright.expect(page.get_by_role("status", name="导出状态")).to_have_count(0)
            playwright.expect(page.get_by_text("有未保存的修改")).to_be_visible()
            # Leaving with unsaved edits asks first; cancelling keeps the work (J1 data loss).
            dialogs = []
            page.once("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
            page.get_by_role("tab", name="素材").click()
            playwright.expect(page.get_by_role("tab", name="剪辑")).to_have_attribute(
                "aria-selected", "true"
            )
            playwright.expect(page.get_by_text("有未保存的修改")).to_be_visible()
            assert dialogs and "未保存" in dialogs[0]
            page.once("dialog", lambda d: d.accept())
            page.get_by_role("tab", name="素材").click()
            playwright.expect(page.get_by_role("tab", name="素材")).to_have_attribute(
                "aria-selected", "true"
            )
            # Nothing unsaved now: switching back and forth never asks.
            page.on("dialog", lambda d: (dialogs.append("unexpected"), d.dismiss()))
            page.get_by_role("tab", name="剪辑").click()
            page.get_by_role("tab", name="发布").click()
            assert "unexpected" not in dialogs
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_narration_draft_synthesize_and_save(narrated, monkeypatch):  # noqa: F811
    """Narration: draft → edit → local voice → placed in the version and back after a reload."""
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as server_module

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "status": "completed",
                    "sourceName": "录像",
                    "completedEligible": True,
                }
            ]
        }

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    server = create_server("127.0.0.1", 0, narrated.jobs.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
    last = json.dumps({"artifacts/project": {"id": narrated.root, "kind": "plan"}})
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(
                "if (!sessionStorage.seeded) { sessionStorage.seeded = 1;"
                f" localStorage.setItem('studio-v1', {prefs!r});"
                f" localStorage.setItem('studio-last-job-v1', {last!r}); }}"
            )
            page.goto(base + "/studio")
            # Sound is reached from the empty narration lane under the timeline.
            page.get_by_role("button", name=re.compile("旁白轨：未添加")).click()
            playwright.expect(page.get_by_role("tab", name="声音")).to_have_attribute(
                "aria-selected", "true"
            )
            page.get_by_role("button", name="起草旁白稿").click()
            page.get_by_role("textbox", name="旁白稿", exact=True).fill("测试旁白")
            page.get_by_role("button", name="合成旁白").click()
            playwright.expect(page.locator(".lane.voice")).to_contain_text("秒")
            playwright.expect(page.get_by_text("有未保存的修改")).to_be_visible()
            page.get_by_role("button", name="保存版本").click()
            playwright.expect(page.get_by_text("已保存的版本")).to_be_visible()
            page.reload()
            playwright.expect(page.locator(".lane.voice")).to_contain_text("秒")
            page.locator(".lane.voice").click()
            playwright.expect(page.get_by_role("button", name="移除旁白")).to_be_visible()
            assert narrated.engine.synthesized == 1
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_cloud_voice_confirms_cost_before_paying(narrated, monkeypatch):  # noqa: F811
    """Free local voice stays default; explicitly choosing cloud requires cost confirmation."""
    playwright = pytest.importorskip("playwright.sync_api")
    import io
    import wave

    import gamingcreator.infrastructure.cosyvoice_tts as tts
    import gamingcreator.ui.server as server_module

    calls = []

    def fake(text, name, timeout=60.0, transport=None):
        calls.append(name)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            wav.writeframes(bytes([16, 0]) * 2400)
        return tts.CloudSpeech(buffer.getvalue(), 8, "provider")

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "status": "completed",
                    "sourceName": "录像",
                    "completedEligible": True,
                }
            ]
        }

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only")
    monkeypatch.setattr(tts, "synthesize", fake)
    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    server = create_server("127.0.0.1", 0, narrated.jobs.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
    last = json.dumps({"artifacts/project": {"id": narrated.root, "kind": "plan"}})
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(
                f"localStorage.setItem('studio-v1', {prefs!r});"
                f" localStorage.setItem('studio-last-job-v1', {last!r});"
            )
            page.goto(base + "/studio")
            # Sound is reached from the empty narration lane under the timeline.
            page.get_by_role("button", name=re.compile("旁白轨：未添加")).click()
            playwright.expect(page.get_by_role("tab", name="声音")).to_have_attribute(
                "aria-selected", "true"
            )
            page.get_by_role("button", name="起草旁白稿").click()
            page.get_by_role("textbox", name="旁白稿", exact=True).fill("测试旁白")
            voices = page.get_by_label("声音", exact=False).first
            playwright.expect(voices).to_have_value("v1")
            playwright.expect(
                page.get_by_role("button", name="合成旁白", exact=True)
            ).to_be_visible()
            assert calls == []
            voices.select_option("cosyvoice:longanyang")
            pay = page.get_by_role("button", name=re.compile(r"确认付费合成（约 [¥￥]0\.0008）"))
            pay.click()
            playwright.expect(page.locator(".lane.voice")).to_contain_text("秒")
            assert calls == ["longanyang"]
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_clip_basket_search_add_and_plan_uses_only_basket(service, monkeypatch):  # noqa: F811
    """Search → add to basket (button and B key) → 用片段篮生成方案 → planner gets those events."""
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.creation_jobs as implementation
    import gamingcreator.ui.server as server_module
    from gamingcreator.infrastructure.creation_files import write_creation

    seen = []

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "status": "completed",
                    "sourceName": "录像",
                    "completedEligible": True,
                    "durationUs": 9_000_000,
                }
            ]
        }

    async def planner(
        project,
        runs_,
        brief,
        output,
        events,
        fps,
        selection,
        preferences=None,
        edit_kinds=None,
        clip_ranges=None,
    ):
        seen.append(list(events))
        assert clip_ranges and len(clip_ranges) == len(events)
        segment = {
            "runId": "run",
            "eventId": events[0],
            "outputFrames": 60,
            "evidenceIds": [],
            "scriptDraft": "x",
            "sourcePath": "p",
            "startUs": 0,
            "endUs": 2_000_000,
        }
        plans = [
            {
                "id": "a",
                "structure": "推荐模板",
                "mode": "feature_showcase",
                "ready": True,
                "gaps": [],
                "scriptStatus": "draft",
                "segments": [segment],
            }
        ]
        write_creation(
            output,
            {
                "plans.json": {
                    "schemaVersion": "creation-plan-v1",
                    "fps": fps,
                    "brief": json.loads(brief.read_text()),
                    "plans": plans,
                }
            },
            (),
        )

    facts = ["角色跳跃躲开陷阱", "角色跳跃收集金币", "菜单界面"]
    timeline = [
        {
            "eventId": f"run:m:event:{i}",
            "startUs": i * 2_000_000,
            "endUs": (i + 1) * 2_000_000,
            "startTimecode": f"00:00:0{2 * i}.000",
            "endTimecode": f"00:00:0{2 * i + 2}.000",
            "displayFacts": [fact],
            "evidenceIds": [],
            "mechanicTags": [],
        }
        for i, fact in enumerate(facts)
    ]
    inspect = {
        "runId": "run",
        "timeline": timeline,
        "evidence": [],
        "media": {"videoUrl": "/api/media?project=x&run=run", "durationUs": 6_000_000},
    }
    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    monkeypatch.setattr(implementation, "execute_plan_creation", planner)
    server = create_server("127.0.0.1", 0, service.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route(
                lambda url: "/api/inspect?" in url, lambda route: route.fulfill(json=inspect)
            )
            # Stage B: after "生成方案" the AI plans once within the budget (model mocked here).
            actions = []
            page.route(
                "**/api/creation/reasoning/config",
                lambda route: route.fulfill(json={"available": True}),
            )

            def reasoning(route):
                action = json.loads(route.request.post_data)["action"]
                actions.append(action)
                if action == "prepare_plan":
                    budget = {"eligible": True, "monthSpentCny": "0", "monthCapCny": "30"}
                    budget |= {"videoSpentCny": "0", "videoCapCny": "1", "ceilingCny": "0.03"}
                    quote = {"preparedHash": "a" * 64, "snapshotFingerprint": "b" * 64}
                    return route.fulfill(json={**quote, "maxCostCny": "2", "budget": budget})
                plan = {"title": "AI 新手向", "structure": "先讲跳跃", "actualFrames": 60}
                plan |= {"targetFrames": 60, "durationStatus": "target-met", "segments": []}
                preview = {"fps": 30, "plans": [plan]}
                return route.fulfill(json={"status": "completed", "planPreview": preview})

            page.route("**/api/creation/reasoning", reasoning)
            page.goto(base + "/studio")
            page.get_by_label("搜索片段").fill("跳跃")
            playwright.expect(page.locator(".clip-search .hit")).to_have_count(2)
            page.locator(".clip-search .hit").first.get_by_role("button", name="加入片段篮").click()
            # The second hit: open it on the timeline, then add it with the B key.
            page.locator(".clip-search .hit-main").nth(1).click()
            playwright.expect(page.get_by_role("button", name="加入片段篮").last).to_be_visible()
            page.locator(".viewer").click()
            page.keyboard.press("b")
            playwright.expect(page.locator(".basket .hit")).to_have_count(2)
            page.get_by_role("button", name="用片段篮生成方案").click()
            playwright.expect(page.locator(".basket-option input")).to_be_checked()
            page.locator(".brief input.input").first.fill("测试游戏")
            page.get_by_role("button", name="生成方案").click()
            playwright.expect(page.locator(".plan")).to_have_count(1)
            assert seen == [["run:m:event:0", "run:m:event:1"]]
            playwright.expect(page.get_by_label("动态方案预览")).to_contain_text("AI 新手向")
            assert actions == ["prepare_plan", "execute_budget"]
            # The basket survives a reload.
            page.reload()
            page.get_by_role("tab", name="素材").click()
            playwright.expect(page.locator(".basket .hit")).to_have_count(2)
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("fixture_name", ["replacements", "framed_replacements"])
def test_replace_clip_saves_and_follow_up_edit_keeps_manifest(fixture_name, request, monkeypatch):
    """Replace a clip's footage, save; then edit that version again and save once more."""
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as server_module

    jobs, root, _ = request.getfixturevalue(fixture_name)

    async def runs(project):
        listed = [
            {"id": i, "status": "completed", "sourceName": i, "completedEligible": True}
            for i in ("run", "B")
        ]
        return {"runs": listed}

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    server = create_server("127.0.0.1", 0, jobs.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
    last = json.dumps({"artifacts/project": {"id": root, "kind": "plan"}})
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(
                "if (!sessionStorage.seeded) { sessionStorage.seeded = 1;"
                f" localStorage.setItem('studio-v1', {prefs!r});"
                f" localStorage.setItem('studio-last-job-v1', {last!r}); }}"
            )
            page.goto(base + "/studio")
            playwright.expect(page.get_by_text("方案原样")).to_be_visible()
            # The plan uses one recording; the other's clips are free to swap in.
            page.locator(".timeline .clip").first.click()
            page.get_by_role("button", name="替换这段画面").click()
            choices = page.get_by_role("button", name="换成这段")
            playwright.expect(choices.first).to_be_visible()
            choices.first.click()
            page.get_by_role("button", name="保存版本").click()
            playwright.expect(page.get_by_text("已保存的版本")).to_be_visible()
            page.reload()
            playwright.expect(page.get_by_text("已保存的版本")).to_be_visible()
            page.locator(".timeline .clip").last.click()
            page.get_by_label("速度").select_option("2/1")
            page.get_by_role("button", name="保存版本").click()
            playwright.expect(page.get_by_text("已保存为新版本。")).to_be_visible()
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
