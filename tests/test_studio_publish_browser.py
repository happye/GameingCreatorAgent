"""Studio Deliver workspace: video → edit copy → cover frame → save → platform package.

Real static server; the creation APIs are answered by the test so no media is processed.
"""

import hashlib
import io
import json
import threading
import zipfile

import pytest
from test_creation_jobs import service  # noqa: F401

from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.media import MediaResource
from gamingcreator.ui.server import create_server

RENDER, PUB, PKG = "a" * 32, "b" * 32, "c" * 32
DIGEST = "d" * 64


def test_publish_copy_cover_and_package(service, monkeypatch):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as server_module

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    draft = {
        "publicationJobId": None,
        "publicationReceiptSha256": None,
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
    posted = {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("video.mp4", b"fixture-video")
        package.writestr("description.txt", "发布文案")
    package_bytes = buffer.getvalue()
    package_path = service.repository / "fixture-package.zip"
    package_path.write_bytes(package_bytes)

    def package_file(self, job_id, name):
        assert job_id == PKG and name == "package.zip"
        return MediaResource(
            package_path, hashlib.sha256(package_bytes).hexdigest(), "application/zip"
        )

    monkeypatch.setattr(CreationJobs, "package_file", package_file)

    def answer(route):
        request = route.request
        path = request.url.split("://", 1)[1].split("/", 1)[1]
        path = "/" + path.split("?", 1)[0]
        if path == f"/api/creation/jobs/{PKG}/package-files/package.zip":
            return route.continue_()
        if path == "/api/creation/jobs":
            jobs = [
                {
                    "jobId": RENDER,
                    "kind": "render",
                    "status": "completed",
                    "createdAt": "2026-11-03T10:00:00Z",
                }
            ]
            return route.fulfill(json={"jobs": jobs})
        if path == "/api/creation/platform-profiles":
            profile = {
                "Platform": "bilibili",
                "RuleVersion": "v1",
                "UpdatedAt": "x",
                "Fields": {"limits": {"titleMaxChars": 80}},
            }
            return route.fulfill(json={"profiles": [profile]})
        if path == "/api/creation/publications":
            posted["publication"] = json.loads(request.post_data)
            return route.fulfill(
                status=202, json={"jobId": PUB, "kind": "publication", "status": "pending"}
            )
        if path == f"/api/creation/jobs/{PUB}/packages":
            return route.fulfill(json={"jobs": []})
        if path == "/api/creation/packages":
            posted["package"] = json.loads(request.post_data)
            return route.fulfill(
                status=202, json={"jobId": PKG, "kind": "package", "status": "pending"}
            )
        if path in (f"/api/creation/jobs/{PUB}", f"/api/creation/jobs/{PKG}"):
            return route.fulfill(json={"jobId": path[-32:], "status": "completed"})
        if path == f"/api/creation/jobs/{RENDER}/publication":
            return route.fulfill(json=draft)
        if path == f"/api/creation/jobs/{PUB}/publication":
            saved = {
                **draft,
                **posted["publication"],
                "publicationJobId": PUB,
                "publicationReceiptSha256": "e" * 64,
            }
            return route.fulfill(json=saved)
        if path == f"/api/creation/jobs/{PKG}/package":
            package = {
                "publicationJobId": PUB,
                "generationStatus": "completed",
                "localChecks": "pass",
                "profile": {"Platform": "bilibili"},
                "validation": {"checks": {"width": "pass"}},
            }
            return route.fulfill(json=package)
        return route.continue_()

    server = create_server("127.0.0.1", 0, service.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
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
            title = page.locator("[aria-label=发布信息] input").first
            playwright.expect(title).to_have_value("游戏 · 目标")
            # Packaging waits for saved copy.
            playwright.expect(page.get_by_role("button", name="生成平台包")).to_be_disabled()
            title.fill("三分钟看懂玩法")
            # Unsaved copy: leaving Publish asks first; cancelling keeps the edit.
            asked = []
            page.once("dialog", lambda d: (asked.append(d.message), d.dismiss()))
            page.get_by_role("tab", name="剪辑").click()
            playwright.expect(page.get_by_role("tab", name="发布")).to_have_attribute(
                "aria-selected", "true"
            )
            playwright.expect(title).to_have_value("三分钟看懂玩法")
            assert asked
            page.get_by_role("button", name="保存发布信息").click()
            playwright.expect(page.get_by_text("已保存的版本")).to_be_visible()
            assert posted["publication"]["title"] == "三分钟看懂玩法"
            assert posted["publication"]["tags"] == ["游戏", "玩法展示"]
            assert posted["publication"]["expectedRenderReceiptSha256"] == DIGEST
            # J1 2026-11-11: copy buttons were useless and are gone; the cover is part of the
            # publish info (saved cover shown once saved).
            playwright.expect(page.get_by_role("button", name="复制标题")).to_have_count(0)
            playwright.expect(page.get_by_text("封面（保存前可选）")).to_be_visible()
            # With no platform ticked, the reason is shown next to the disabled button.
            boxes = page.locator("[aria-label=平台包] input[type=checkbox]")
            ticked = [i for i in range(boxes.count()) if boxes.nth(i).is_checked()]
            for i in ticked:
                boxes.nth(i).uncheck()
            playwright.expect(page.get_by_role("status", name="平台包状态")).to_have_text(
                "至少勾选一个平台"
            )
            playwright.expect(page.get_by_role("button", name="生成平台包")).to_be_disabled()
            for i in ticked:
                boxes.nth(i).check()
            playwright.expect(page.get_by_role("status", name="平台包状态")).to_have_count(0)
            page.get_by_role("button", name="生成平台包").click()
            playwright.expect(page.get_by_role("link", name="下载平台包（zip）")).to_have_attribute(
                "href", f"/api/creation/jobs/{PKG}/package-files/package.zip?download=1"
            )
            # Click the link and read bytes from the real media HTTP handler.
            link = page.get_by_role("link", name="下载平台包（zip）")
            playwright.expect(link).to_have_attribute("download", "package.zip")
            with page.expect_download() as downloaded:
                link.click()
            download = downloaded.value
            assert download.suggested_filename == "package.zip" and download.failure() is None
            assert download.path().read_bytes() == package_bytes
            with zipfile.ZipFile(download.path()) as package:
                assert package.read("video.mp4") == b"fixture-video"
            assert posted["package"]["publicationJobId"] == PUB
            assert posted["package"]["profile"]["Platform"] == "bilibili"
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
