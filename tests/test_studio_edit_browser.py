"""Studio Edit workspace against the real HTTP server and job system (planner/renderer faked).

Protects the user flow, not the DOM: brief → plans → choose → export → downloadable video,
plus the draft surviving a reload.
"""

import json
import re
import threading

import pytest
from test_creation_jobs import service  # noqa: F401

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
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
