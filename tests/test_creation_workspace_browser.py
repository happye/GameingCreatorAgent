"""Browser contract tests with mocked HTTP; real integration is checked separately."""

import json
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"


@pytest.mark.parametrize("width", [1366, 390])
def test_creation_form_plans_render_and_refresh(width):
    playwright = pytest.importorskip("playwright.sync_api")
    jobs = {}
    posts = []
    plan = {
        "jobId": "a" * 32,
        "kind": "plan",
        "status": "completed",
        "projectId": "project-one",
        "createdAt": "2026-10-30",
        "error": None,
        "fps": 30,
        "plans": [
            {
                "id": str(index),
                "structure": f"模板 {index}",
                "scriptStatus": "saved-descriptions-draft-human-review-required",
                "ready": index != 2,
                "gaps": ["缺少主题"] if index == 2 else [],
                "segments": [
                    {
                        "startUs": 0,
                        "endUs": 1000000,
                        "outputFrames": 30,
                        "scriptDraft": '<img src=x onerror="window.injected=true">',
                    }
                ],
            }
            for index in range(3)
        ],
    }
    render = {
        "jobId": "b" * 32,
        "kind": "render",
        "status": "completed",
        "projectId": "project-one",
        "createdAt": "2026-10-30",
        "error": None,
        "artifact": {
            "mediaType": "video/mp4",
            "sizeBytes": 123,
            "subtitleMode": "burn",
            "subtitleCueCount": 0,
            "subtitleUrl": f"/api/creation/jobs/{'b' * 32}/subtitles",
            "sha256": "c" * 64,
            "previewUrl": f"/api/creation/jobs/{'b' * 32}/video",
            "downloadUrl": f"/api/creation/jobs/{'b' * 32}/video?download=1",
        },
    }
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_request(route):
            path = route.request.url.split("http://workspace.test", 1)[1]
            if path == "/creation":
                route.fulfill(
                    body=(STATIC / "creation.html").read_text("utf-8-sig"), content_type="text/html"
                )
            elif path.startswith("/assets/"):
                name = path.rsplit("/", 1)[1]
                route.fulfill(
                    body=(STATIC / name).read_text("utf-8-sig"),
                    content_type="text/css" if name.endswith("css") else "text/javascript",
                )
            elif path == "/api/projects":
                route.fulfill(json={"projects": [{"path": "project-one", "name": "游戏项目"}]})
            elif path.startswith("/api/runs?"):
                route.fulfill(
                    json={
                        "runs": [
                            {"id": "completed", "sourceName": "录像", "completedEligible": True},
                            {"id": "pending", "completedEligible": False},
                        ]
                    }
                )
            elif route.request.method == "POST":
                body = json.loads(route.request.post_data)
                posts.append(body)
                job = plan if path.endswith("plans") else render
                jobs[job["jobId"]] = job
                route.fulfill(
                    status=202, json={key: job[key] for key in ("jobId", "kind", "status")}
                )
            elif path.startswith("/api/creation/jobs?"):
                route.fulfill(json={"jobs": list(jobs.values())})
            elif path.endswith("/video"):
                route.fulfill(status=204)
            else:
                route.fulfill(json=jobs[path.rsplit("/", 1)[1]])

        page.route("**/*", route_request)
        try:
            page.goto("http://workspace.test/creation")
            playwright.expect(page.locator("#runs input")).to_have_count(1)
            assert not posts
            page.locator("#runs input").check()
            page.locator("[name=game]").fill("游戏")
            page.locator("[name=contentType]").select_option(label="攻略")
            page.locator("[name=platforms]").select_option(label="抖音")
            page.locator("#plan").click()
            playwright.expect(page.locator(".plan-card")).to_have_count(3)
            playwright.expect(
                page.locator(".plan-card").nth(2).get_by_role("button")
            ).to_be_disabled()
            playwright.expect(page.locator("#render")).to_be_disabled()
            assert page.locator(".plan-card img").count() == 0
            page.locator(".plan-card").first.get_by_role("button").click()
            page.locator("#subtitles").select_option("burn")
            page.locator("#render").click()
            playwright.expect(page.locator("video")).to_have_attribute(
                "src", render["artifact"]["previewUrl"]
            )
            assert set(posts[0]) == {"requestId", "projectId", "runIds", "brief", "fps"}
            assert set(posts[1]) == {
                "requestId",
                "planJobId",
                "planId",
                "width",
                "height",
                "subtitleMode",
            }
            assert posts[1]["subtitleMode"] == "burn"
            assert len(posts[0]["requestId"]) == 32
            assert posts[0]["brief"]["contentType"] == "guide"
            assert posts[0]["brief"]["platforms"] == ["douyin"]
            page.reload()
            playwright.expect(page.locator("video")).to_be_visible()
            assert len(posts) == 2
            assert page.locator("#artifact a").first.get_attribute("href").endswith("?download=1")
            playwright.expect(page.locator("#artifact")).to_contain_text("字幕 0 条")
            playwright.expect(page.locator("#download-subtitles")).to_have_attribute(
                "href", render["artifact"]["subtitleUrl"]
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors
        finally:
            browser.close()


def test_creation_retry_reuses_id_and_late_job_cannot_replace_project():
    playwright = pytest.importorskip("playwright.sync_api")
    posts = []
    held = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page()

        def route_request(route):
            path = route.request.url.split("http://workspace.test", 1)[1]
            if path == "/creation":
                route.fulfill(
                    body=(STATIC / "creation.html").read_text("utf-8-sig"), content_type="text/html"
                )
            elif path.startswith("/assets/"):
                name = path.rsplit("/", 1)[1]
                route.fulfill(
                    body=(STATIC / name).read_text("utf-8-sig"),
                    content_type="text/css" if name.endswith("css") else "text/javascript",
                )
            elif path == "/api/projects":
                route.fulfill(json={"projects": [{"path": "one"}, {"path": "two"}]})
            elif path.startswith("/api/runs?"):
                route.fulfill(
                    json={"runs": [{"id": "r", "sourceName": "录像", "completedEligible": True}]}
                )
            elif route.request.method == "POST":
                posts.append(json.loads(route.request.post_data))
                if len(posts) == 1:
                    route.fulfill(status=503, json={"error": {"message": "暂时无法提交"}})
                else:
                    route.fulfill(
                        status=202, json={"jobId": "d" * 32, "kind": "plan", "status": "running"}
                    )
            elif path.startswith("/api/creation/jobs?"):
                route.fulfill(json={"jobs": []})
            else:
                held.append(route)

        page.route("**/*", route_request)
        try:
            page.goto("http://workspace.test/creation")
            page.locator("#runs input").check()
            page.locator("[name=game]").fill("游戏")
            page.locator("[name=contentType]").select_option(label="攻略")
            page.locator("[name=platforms]").select_option(label="抖音")
            page.locator("#plan").click()
            playwright.expect(page.locator("#notice")).to_contain_text("暂时无法提交")
            page.locator("#plan").click()
            playwright.expect(page.locator("#notice")).to_contain_text("任务已保存")
            assert posts[0] == posts[1]
            page.wait_for_timeout(100)
            assert held
            page.locator("#project").select_option("two")
            playwright.expect(page.locator("#notice")).to_contain_text("请选择素材")
            held.pop().fulfill(
                json={
                    "jobId": "d" * 32,
                    "projectId": "one",
                    "kind": "plan",
                    "status": "failed",
                    "error": {"code": "old", "message": "旧项目失败"},
                }
            )
            page.wait_for_timeout(100)
            playwright.expect(page.locator("#job-status")).to_have_text("尚未选择任务")
            assert "旧项目" not in page.locator("#notice").inner_text()
        finally:
            browser.close()
