"""Studio Edit workspace against the real HTTP server and job system (planner/renderer faked).

Protects the user flow, not the DOM: brief → plans → choose → export → downloadable video,
plus the draft surviving a reload.
"""

import json
import re
import threading

import pytest
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
                "gaps": ["缺少主题"],
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
            page.get_by_role("tab", name="剪辑").click()
            page.locator(".brief input[type=checkbox]").check()
            page.locator(".brief input.input").first.fill("测试游戏")
            page.get_by_role("button", name="生成方案").click()
            playwright.expect(page.locator(".plan")).to_have_count(2)
            # A plan with gaps cannot be chosen; the ready one is selected and previewable.
            playwright.expect(page.locator(".plan").nth(1)).to_be_disabled()
            playwright.expect(page.locator(".plan").first).to_have_attribute("aria-current", "true")
            playwright.expect(page.locator(".timeline .clip")).to_have_count(2)
            page.get_by_role("button", name="导出成片").click()
            playwright.expect(page.locator("a[download]")).to_have_attribute(
                "href", re.compile(r"^/api/creation/jobs/[0-9a-f]{32}/video\?download=1$")
            )
            # The page never scrolls; panels do.
            assert page.evaluate("document.documentElement.scrollHeight <= innerHeight")
            # The brief survives a reload, and the last result reopens.
            page.reload()
            playwright.expect(page.locator(".brief input.input").first).to_have_value("测试游戏")
            playwright.expect(page.locator("a[download]")).to_be_visible()
            # Reopening a video brings back its plans, and export stays on screen.
            playwright.expect(page.locator(".plan")).to_have_count(2)
            export = page.get_by_role("button", name="导出成片")
            playwright.expect(export).to_be_enabled()
            assert export.evaluate("e => e.getBoundingClientRect().bottom <= innerHeight")
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
            clips.nth(1).click()
            page.get_by_label("速度").select_option("2/1")
            playwright.expect(page.locator(".clip-speed")).to_have_text("2×")
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
            page.get_by_role("button", name="应用").click()
            playwright.expect(page.get_by_text("有未保存的修改")).to_be_visible()
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
            page.get_by_label("旁白稿").fill("测试旁白")
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
    """The default cloud voice shows its cost on the button; one click pays once."""
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
            page.get_by_label("旁白稿").fill("测试旁白")
            playwright.expect(page.get_by_label("声音", exact=False).first).to_have_value(
                "cosyvoice:longanyang"
            )
            pay = page.get_by_role("button", name=re.compile(r"确认付费合成（约 ¥0\.0008）"))
            pay.click()
            playwright.expect(page.locator(".lane.voice")).to_contain_text("秒")
            assert calls == ["longanyang"]
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
