"""F12 工作台：已完成的平台包被改坏或缺件后，不能再出现下载成功入口。"""

from __future__ import annotations

import threading

import pytest
from test_creation_jobs import service  # noqa: F401

from gamingcreator.ui.server import create_server

RENDER, PUB, PKG = "a" * 32, "b" * 32, "c" * 32
DIGEST = "d" * 64


def test_damaged_package_hides_download_and_names_the_missing_file(service, monkeypatch):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as server_module

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    message = "任务产物已更改，不能预览或下载：缺少平台包文件 title.txt"
    draft = {
        "publicationJobId": PUB,
        "publicationReceiptSha256": "e" * 64,
        "renderJobId": RENDER,
        "expectedRenderReceiptSha256": DIGEST,
        "coverFrame": 0,
        "title": "游戏 · 目标",
        "description": "目标",
        "tags": ["游戏", "玩法展示"],
        "frames": 300,
        "fps": {"numerator": 30, "denominator": 1},
        "width": 1280,
        "height": 720,
        "videoUrl": f"/api/creation/jobs/{RENDER}/video",
    }

    def answer(route):
        path = "/" + route.request.url.split("://", 1)[1].split("/", 1)[1].split("?", 1)[0]
        if path == "/api/creation/jobs":
            return route.fulfill(
                json={
                    "jobs": [
                        {
                            "jobId": RENDER,
                            "kind": "render",
                            "status": "completed",
                            "createdAt": "2026-11-03T10:00:00Z",
                        }
                    ]
                }
            )
        if path == "/api/creation/reasoning/config":
            return route.fulfill(json={"available": False})
        if path == "/api/creation/platform-profiles":
            return route.fulfill(
                json={
                    "profiles": [
                        {
                            "Platform": "bilibili",
                            "RuleVersion": "v1",
                            "UpdatedAt": "x",
                            "Fields": {"limits": {}},
                        }
                    ]
                }
            )
        if path in (
            f"/api/creation/jobs/{RENDER}/publication",
            f"/api/creation/jobs/{PUB}/publication",
        ):
            return route.fulfill(json=draft)
        if path == f"/api/creation/jobs/{PUB}/packages":
            return route.fulfill(
                json={
                    "publicationJobId": PUB,
                    "publicationReceiptSha256": "e" * 64,
                    "jobs": [
                        {
                            "jobId": PKG,
                            "status": "completed",
                            "createdAt": "2026-11-16T02:00:00Z",
                            "updatedAt": "2026-11-16T02:00:00Z",
                            "parentJobId": PUB,
                            "profile": {"Platform": "bilibili"},
                            "platform": "bilibili",
                        }
                    ],
                }
            )
        if path == f"/api/creation/jobs/{PKG}/package" or "/package-files/" in path:
            return route.fulfill(
                status=409,
                json={
                    "code": "creation.artifact_invalid",
                    "message": message,
                    "exitCode": 5,
                },
            )
        return route.continue_()

    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route(lambda url: "/api/creation/" in url, answer)
            page.goto(base + "/studio")
            page.get_by_role("tab", name="发布").click()
            playwright.expect(
                page.get_by_role("status").filter(has_text="缺少平台包文件 title.txt")
            ).to_be_visible()
            playwright.expect(page.get_by_role("link", name="下载平台包（zip）")).to_have_count(0)
            playwright.expect(page.get_by_role("link", name="只下载视频")).to_have_count(0)
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
