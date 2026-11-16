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
            path = route.request.url.split("http://workspace.test", 1)[1].split("?", 1)[0]
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
            elif path == "/api/creation/platform-profiles":
                route.fulfill(json={"profiles": []})
            elif path == "/api/creation/music":
                route.fulfill(json={"tracks": [], "issues": []})
            elif path == "/api/creation/voices":
                route.fulfill(json={"voices": [], "licenseStatus": "unknown"})
            elif path == "/api/entitlement":
                route.fulfill(status=404, json={"message": "未模拟"})
            elif path == "/api/enterprise/team":
                route.fulfill(json={"team": None})
            elif path == "/api/enterprise/audit":
                route.fulfill(body="{}", content_type="application/json")
            elif path == "/api/projects":
                route.fulfill(json={"projects": [{"path": "project-one", "name": "游戏项目"}]})
            elif path == "/api/runs" or path.startswith("/api/runs?"):
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
            elif path == "/api/creation/jobs" or path.startswith("/api/creation/jobs?"):
                route.fulfill(json={"jobs": list(jobs.values())})
            elif path.endswith("/edit") or "/edit?" in path:
                route.fulfill(
                    json={
                        "parentJobId": plan["jobId"],
                        "planId": "0",
                        "expectedParentReceiptSha256": "c" * 64,
                        "rootReceiptSha256": "c" * 64,
                        "fps": 30,
                        "ancestry": [],
                        "clips": [{**plan["plans"][0]["segments"][0], "clipId": "clip-one"}],
                    }
                )
            elif path.endswith("/publication"):
                route.fulfill(
                    json={
                        "renderJobId": "b" * 32,
                        "expectedRenderReceiptSha256": "c" * 64,
                        "coverFrame": 0,
                        "title": "模板",
                        "description": "",
                        "tags": [],
                        "frames": 30,
                        "fps": 30,
                        "width": 1280,
                        "height": 720,
                        "videoUrl": f"/api/creation/jobs/{'b' * 32}/video",
                        "draftStatus": "editable-template-not-ai",
                    }
                )
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
            # A grey button says why; cards stay short however many segments a plan has.
            playwright.expect(page.locator("#render-hint")).to_contain_text("选择此方案")
            assert page.locator(".plan-card").first.evaluate("e => e.offsetHeight") < 900
            assert page.locator(".plan-card img").count() == 0
            page.locator(".plan-card").first.get_by_role("button").click()
            page.locator("#subtitles").select_option("burn")
            page.locator("#render").click()
            playwright.expect(page.locator("#artifact video")).to_have_attribute(
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
            playwright.expect(page.locator("#artifact video")).to_be_visible()
            # The draft survives a reload; saved work is grouped by kind, videos first.
            assert page.locator("[name=game]").input_value() == "游戏"
            assert page.locator("[name=contentType]").input_value() == "guide"
            playwright.expect(page.locator("#runs input")).to_be_checked()
            playwright.expect(page.locator("#history h3").first).to_have_text("视频（1）")
            page.locator("#clear-draft").click()
            assert page.locator("[name=game]").input_value() == ""
            playwright.expect(page.locator("#runs input")).not_to_be_checked()
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
            path = route.request.url.split("http://workspace.test", 1)[1].split("?", 1)[0]
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
            elif path == "/api/creation/platform-profiles":
                route.fulfill(json={"profiles": []})
            elif path == "/api/creation/music":
                route.fulfill(json={"tracks": [], "issues": []})
            elif path == "/api/creation/voices":
                route.fulfill(json={"voices": [], "licenseStatus": "unknown"})
            elif path == "/api/entitlement":
                route.fulfill(status=404, json={"message": "未模拟"})
            elif path == "/api/enterprise/team":
                route.fulfill(json={"team": None})
            elif path == "/api/enterprise/audit":
                route.fulfill(body="{}", content_type="application/json")
            elif path == "/api/projects":
                route.fulfill(json={"projects": [{"path": "one"}, {"path": "two"}]})
            elif path == "/api/runs" or path.startswith("/api/runs?"):
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
            elif path == "/api/creation/jobs" or path.startswith("/api/creation/jobs?"):
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


def test_compare_clears_when_switching_jobs_and_keeps_edits_on_close():
    playwright = pytest.importorskip("playwright.sync_api")
    job_a = "a" * 32
    job_b = "b" * 32
    shared = [
        {"startUs": 0, "endUs": 2000000, "outputFrames": 60, "scriptDraft": "开场"},
        {"startUs": 2000000, "endUs": 4000000, "outputFrames": 60, "scriptDraft": "过程"},
    ]

    def plan_job(job_id, left_name, right_name, created_at):
        return {
            "jobId": job_id,
            "kind": "plan",
            "status": "completed",
            "projectId": "project-one",
            "createdAt": created_at,
            "error": None,
            "fps": 30,
            "plans": [
                {
                    "id": "guide-steps",
                    "structure": left_name,
                    "scriptStatus": "saved-descriptions-draft-human-review-required",
                    "ready": True,
                    "gaps": [],
                    "segments": shared,
                },
                {
                    "id": "hook-first",
                    "structure": right_name,
                    "scriptStatus": "saved-descriptions-draft-human-review-required",
                    "ready": True,
                    "gaps": [],
                    "segments": list(reversed(shared)),
                },
            ],
        }

    jobs = {
        job_a: plan_job(job_a, "甲作品左侧方案", "甲作品右侧方案", "2026-10-30T10:00:00"),
        job_b: plan_job(job_b, "乙作品左侧方案", "乙作品右侧方案", "2026-10-31T10:00:00"),
    }
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_request(route):
            path = route.request.url.split("http://workspace.test", 1)[1].split("?", 1)[0]
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
            elif path == "/api/creation/platform-profiles":
                route.fulfill(json={"profiles": []})
            elif path == "/api/creation/music":
                route.fulfill(json={"tracks": [], "issues": []})
            elif path == "/api/creation/voices":
                route.fulfill(json={"voices": [], "licenseStatus": "unknown"})
            elif path == "/api/entitlement":
                route.fulfill(status=404, json={"message": "未模拟"})
            elif path == "/api/enterprise/team":
                route.fulfill(json={"team": None})
            elif path == "/api/enterprise/audit":
                route.fulfill(body="{}", content_type="application/json")
            elif path == "/api/projects":
                route.fulfill(json={"projects": [{"path": "project-one", "name": "游戏项目"}]})
            elif path == "/api/runs" or path.startswith("/api/runs?"):
                route.fulfill(
                    json={
                        "runs": [
                            {"id": "completed", "sourceName": "录像", "completedEligible": True}
                        ]
                    }
                )
            elif path == "/api/creation/jobs" or path.startswith("/api/creation/jobs?"):
                route.fulfill(json={"jobs": [jobs[job_b], jobs[job_a]]})
            elif path.endswith("/edit") or "/edit?" in path:
                plan_id = "guide-steps"
                if "planId=" in route.request.url:
                    plan_id = route.request.url.split("planId=", 1)[1].split("&", 1)[0]
                parent = path.split("/jobs/", 1)[1].split("/edit", 1)[0]
                route.fulfill(
                    json={
                        "parentJobId": parent,
                        "planId": plan_id,
                        "expectedParentReceiptSha256": "c" * 64,
                        "rootReceiptSha256": "c" * 64,
                        "fps": 30,
                        "ancestry": [],
                        "clips": [
                            {
                                "clipId": "clip-one",
                                "startUs": 0,
                                "endUs": 2000000,
                                "outputFrames": 60,
                                "scriptDraft": "开场",
                            }
                        ],
                    }
                )
            elif route.request.method == "POST":
                route.fulfill(status=500, json={"error": {"message": "本测试不应提交新任务"}})
            else:
                job_id = path.rsplit("/", 1)[1]
                route.fulfill(json=jobs[job_id])

        page.route("**/*", route_request)
        try:
            page.goto("http://workspace.test/creation")
            playwright.expect(page.locator("#history button")).to_have_count(2)
            page.locator("#history button").nth(1).click()
            playwright.expect(page.locator(".plan-card")).to_have_count(2)
            playwright.expect(page.locator("#plan-compare")).to_have_attribute(
                "data-compare-job", job_a
            )
            playwright.expect(page.locator("#plans")).to_contain_text("甲作品左侧方案")
            page.locator("#plan-compare-left").select_option("guide-steps")
            page.locator("#plan-compare-right").select_option("hook-first")
            page.locator("#plan-compare-open").click()
            playwright.expect(page.locator("#plan-compare-view")).to_be_visible()
            playwright.expect(page.locator("#plan-compare-view")).to_contain_text("甲作品左侧方案")
            playwright.expect(page.locator("#plan-compare-view")).to_contain_text("甲作品右侧方案")
            page.locator(".plan-card").first.get_by_role("button", name="选择此方案").click()
            playwright.expect(page.locator("#source-gain")).to_be_visible()
            page.locator("#source-gain").fill("-3")
            playwright.expect(page.locator("#editor-summary")).to_contain_text("配乐或音量已修改")
            playwright.expect(page.locator(".plan-card").first).to_have_class("plan-card selected")
            page.locator("#plan-compare-close").click()
            playwright.expect(page.locator("#plan-compare-view")).to_be_hidden()
            assert page.locator("#plan-compare-view").inner_text() == ""
            assert page.locator("#source-gain").input_value() == "-3"
            playwright.expect(page.locator("#editor-summary")).to_contain_text("配乐或音量已修改")
            playwright.expect(page.locator(".plan-card").first).to_have_class("plan-card selected")
            playwright.expect(page.locator("#render-hint")).to_contain_text("镜头有未保存的修改")
            page.locator("#history button").nth(0).click()
            playwright.expect(page.locator("#plan-compare")).to_have_attribute(
                "data-compare-job", job_b
            )
            playwright.expect(page.locator("#plans")).to_contain_text("乙作品左侧方案")
            playwright.expect(page.locator("#plans")).not_to_contain_text("甲作品左侧方案")
            assert page.locator("#plan-compare-view").count() == 1
            playwright.expect(page.locator("#plan-compare-view")).to_be_hidden()
            assert page.locator("#plan-compare-left").input_value() == ""
            assert page.locator("#plan-compare-right").input_value() == ""
            assert "甲作品" not in page.locator("#plan-compare").inner_text()
            playwright.expect(page.locator("#editor-summary")).to_have_text(
                "选择方案或剪辑版本后可编辑镜头。"
            )
            assert not errors
        finally:
            browser.close()


def test_compare_json_download_from_classic_workbench_keeps_edits():
    playwright = pytest.importorskip("playwright.sync_api")
    job_id = "c" * 32
    job = {
        "jobId": job_id,
        "kind": "plan",
        "status": "completed",
        "projectId": "project-one",
        "createdAt": "2026-11-01T10:00:00",
        "error": None,
        "fps": 30,
        "plans": [
            {
                "id": "guide-steps",
                "structure": "甲方案",
                "ready": True,
                "gaps": [],
                "segments": [
                    {
                        "runId": "run-1",
                        "sourceSha256": "aa",
                        "startUs": 0,
                        "endUs": 2000000,
                        "outputFrames": 60,
                        "scriptDraft": "开场",
                    },
                    {
                        "runId": "run-1",
                        "sourceSha256": "bb",
                        "startUs": 0,
                        "endUs": 2000000,
                        "outputFrames": 60,
                        "scriptDraft": "过程",
                    },
                ],
            },
            {
                "id": "hook-first",
                "structure": "乙方案",
                "ready": True,
                "gaps": [],
                "segments": [
                    {
                        "runId": "run-1",
                        "sourceSha256": "bb",
                        "startUs": 0,
                        "endUs": 2000000,
                        "outputFrames": 60,
                        "scriptDraft": "过程",
                    },
                    {
                        "runId": "run-1",
                        "sourceSha256": "aa",
                        "startUs": 0,
                        "endUs": 2000000,
                        "outputFrames": 60,
                        "scriptDraft": "开场",
                    },
                ],
            },
        ],
    }
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        posts = []

        def route_request(route):
            path = route.request.url.split("http://workspace.test", 1)[1].split("?", 1)[0]
            if route.request.method == "POST":
                posts.append(path)
                route.fulfill(status=500, json={"error": {"message": "本测试不应提交新任务"}})
                return
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
            elif path == "/api/creation/platform-profiles":
                route.fulfill(json={"profiles": []})
            elif path == "/api/creation/music":
                route.fulfill(json={"tracks": [], "issues": []})
            elif path == "/api/creation/voices":
                route.fulfill(json={"voices": [], "licenseStatus": "unknown"})
            elif path == "/api/entitlement":
                route.fulfill(status=404, json={"message": "未模拟"})
            elif path == "/api/enterprise/team":
                route.fulfill(json={"team": None})
            elif path == "/api/enterprise/audit":
                route.fulfill(body="{}", content_type="application/json")
            elif path == "/api/projects":
                route.fulfill(json={"projects": [{"path": "project-one", "name": "游戏项目"}]})
            elif path == "/api/runs" or path.startswith("/api/runs?"):
                route.fulfill(
                    json={
                        "runs": [
                            {"id": "completed", "sourceName": "录像", "completedEligible": True}
                        ]
                    }
                )
            elif path == "/api/creation/jobs" or path.startswith("/api/creation/jobs?"):
                route.fulfill(json={"jobs": [job]})
            elif path.endswith("/edit") or "/edit?" in path:
                route.fulfill(
                    json={
                        "parentJobId": job_id,
                        "planId": "guide-steps",
                        "expectedParentReceiptSha256": "c" * 64,
                        "rootReceiptSha256": "c" * 64,
                        "fps": 30,
                        "ancestry": [],
                        "clips": [
                            {
                                "clipId": "clip-one",
                                "startUs": 0,
                                "endUs": 2000000,
                                "outputFrames": 60,
                                "scriptDraft": "开场",
                            }
                        ],
                    }
                )
            else:
                route.fulfill(json=job)

        page.route("**/*", route_request)
        try:
            page.goto("http://workspace.test/creation")
            page.locator("#history button").first.click()
            playwright.expect(page.locator(".plan-card")).to_have_count(2)
            page.locator(".plan-card").first.get_by_role("button", name="选择此方案").click()
            playwright.expect(page.locator("#source-gain")).to_be_visible()
            page.locator("#source-gain").fill("-3")
            playwright.expect(page.locator("#editor-summary")).to_contain_text("配乐或音量已修改")
            page.locator("#plan-compare-left").select_option("guide-steps")
            page.locator("#plan-compare-right").select_option("hook-first")
            page.locator("#plan-compare-open").click()
            playwright.expect(page.locator("#plan-compare-download")).to_be_visible()
            with page.expect_download() as pending:
                page.locator("#plan-compare-download").click()
            download = pending.value
            assert download.suggested_filename == "plan-comparison-guide-steps-hook-first.json"
            payload = json.loads(Path(download.path()).read_text(encoding="utf-8"))
            assert payload["schemaVersion"] == "plan-comparison-export-v1"
            assert payload["left"]["planId"] == "guide-steps"
            assert payload["right"]["planId"] == "hook-first"
            assert {row["sourceSha256"] for row in payload["sources"]} == {"aa", "bb"}
            assert "scriptDraft" not in json.dumps(payload, ensure_ascii=False)
            assert page.locator("#source-gain").input_value() == "-3"
            playwright.expect(page.locator("#editor-summary")).to_contain_text("配乐或音量已修改")
            playwright.expect(page.locator(".plan-card").first).to_have_class("plan-card selected")
            assert posts == []
            assert not errors
        finally:
            browser.close()


def test_compare_preview_then_save_and_render_uses_adopted_plan():
    playwright = pytest.importorskip("playwright.sync_api")
    job_id = "c" * 32
    revision_id = "d" * 32
    job = {
        "jobId": job_id,
        "kind": "plan",
        "status": "completed",
        "projectId": "project-one",
        "createdAt": "2026-11-01T10:00:00",
        "error": None,
        "fps": 30,
        "plans": [
            {
                "id": "guide-steps",
                "structure": "甲方案",
                "ready": True,
                "gaps": [],
                "segments": [
                    {
                        "runId": "run-1",
                        "sourceSha256": "aa",
                        "startUs": 0,
                        "endUs": 2000000,
                        "outputFrames": 60,
                        "scriptDraft": "开场",
                    },
                    {
                        "runId": "run-1",
                        "sourceSha256": "bb",
                        "startUs": 0,
                        "endUs": 2000000,
                        "outputFrames": 60,
                        "scriptDraft": "过程",
                    },
                ],
            },
            {
                "id": "hook-first",
                "structure": "乙方案",
                "ready": True,
                "gaps": [],
                "segments": [
                    {
                        "runId": "run-1",
                        "sourceSha256": "bb",
                        "startUs": 0,
                        "endUs": 2000000,
                        "outputFrames": 60,
                        "scriptDraft": "过程",
                    },
                    {
                        "runId": "run-1",
                        "sourceSha256": "aa",
                        "startUs": 0,
                        "endUs": 2000000,
                        "outputFrames": 60,
                        "scriptDraft": "开场",
                    },
                ],
            },
        ],
    }
    editor = {
        "parentJobId": job_id,
        "planId": "guide-steps",
        "expectedParentReceiptSha256": "c" * 64,
        "rootReceiptSha256": "c" * 64,
        "fps": 30,
        "ancestry": [],
        "clips": [
            {
                "clipId": "clip-one",
                "startUs": 0,
                "endUs": 2000000,
                "outputFrames": 60,
                "scriptDraft": "开场",
            }
        ],
    }
    jobs = {job_id: job}
    editors = {job_id: editor}
    posts = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_request(route):
            path = route.request.url.split("http://workspace.test", 1)[1].split("?", 1)[0]
            if route.request.method == "POST":
                payload = json.loads(route.request.post_data or "{}")
                posts.append((path, payload))
                if path == "/api/creation/revisions":
                    saved = {
                        **editor,
                        "parentJobId": revision_id,
                        "planId": payload.get("planId"),
                        "audioMix": payload.get("audioMix"),
                        "clips": payload.get("clips") or editor["clips"],
                        "ancestry": [dict(jobId=job_id, planId="guide-steps", kind="plan")],
                    }
                    editors[revision_id] = saved
                    jobs[revision_id] = {
                        "jobId": revision_id,
                        "kind": "revision",
                        "status": "completed",
                        "projectId": "project-one",
                        "createdAt": "2026-11-01T10:01:00",
                        "error": None,
                        "editor": saved,
                    }
                    route.fulfill(
                        status=202,
                        json={"jobId": revision_id, "kind": "revision", "status": "pending"},
                    )
                elif path == "/api/creation/renders":
                    route.fulfill(status=400, json={"error": {"message": "停止于渲染请求验证"}})
                else:
                    route.fulfill(status=500, json={"error": {"message": "本测试不应提交其他任务"}})
                return
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
            elif path == "/api/creation/platform-profiles":
                route.fulfill(json={"profiles": []})
            elif path == "/api/creation/music":
                route.fulfill(json={"tracks": [], "issues": []})
            elif path == "/api/creation/voices":
                route.fulfill(json={"voices": [], "licenseStatus": "unknown"})
            elif path == "/api/entitlement":
                route.fulfill(status=404, json={"message": "未模拟"})
            elif path == "/api/enterprise/team":
                route.fulfill(json={"team": None})
            elif path == "/api/enterprise/audit":
                route.fulfill(body="{}", content_type="application/json")
            elif path == "/api/projects":
                route.fulfill(json={"projects": [{"path": "project-one", "name": "游戏项目"}]})
            elif path == "/api/runs" or path.startswith("/api/runs?"):
                route.fulfill(
                    json={
                        "runs": [
                            {"id": "completed", "sourceName": "录像", "completedEligible": True}
                        ]
                    }
                )
            elif path == "/api/creation/jobs" or path.startswith("/api/creation/jobs?"):
                route.fulfill(json={"jobs": list(jobs.values())})
            elif path.endswith("/edit") or "/edit?" in path:
                parent = path.split("/jobs/", 1)[1].split("/edit", 1)[0]
                route.fulfill(json=editors[parent])
            else:
                job_key = path.rsplit("/", 1)[1]
                route.fulfill(json=jobs[job_key])

        page.route("**/*", route_request)
        try:
            page.goto("http://workspace.test/creation")
            page.locator("#history button").first.click()
            playwright.expect(page.locator(".plan-card")).to_have_count(2)
            page.locator(".plan-card").first.get_by_role("button", name="选择此方案").click()
            playwright.expect(page.locator("#source-gain")).to_be_visible()
            page.locator("#source-gain").fill("-3")
            playwright.expect(page.locator("#editor-summary")).to_contain_text("配乐或音量已修改")
            page.locator("#plan-compare-left").select_option("guide-steps")
            page.locator("#plan-compare-right").select_option("hook-first")
            page.locator("#plan-compare-open").click()
            playwright.expect(page.locator("#plan-compare-view")).to_be_visible()
            page.locator(
                "#plan-compare-alignment button.plan-compare-locate[data-side='right']"
            ).first.click()
            playwright.expect(page.locator(".plan-card").first).to_have_class("plan-card selected")
            assert page.locator("#source-gain").input_value() == "-3"
            page.locator("#save-revision").click()
            playwright.expect(page.locator("#notice")).to_contain_text("任务已保存")
            assert posts, "保存应对已采用方案发出修订请求"
            save_path, save_payload = posts[0]
            assert save_path == "/api/creation/revisions"
            assert save_payload["planId"] == "guide-steps"
            assert save_payload["parentJobId"] == job_id
            assert save_payload["audioMix"]["sourceGainDb"] == -3
            assert all(clip.get("scriptDraft") != "过程" for clip in save_payload["clips"])
            playwright.expect(page.locator("#render")).to_be_enabled()
            page.locator("#render").click()
            playwright.expect(page.locator("#notice")).to_contain_text("停止于渲染")
            assert posts[-1][0] == "/api/creation/renders"
            render_payload = posts[-1][1]
            assert render_payload.get("revisionJobId") == revision_id
            assert render_payload.get("planId") in (None, "guide-steps")
            assert render_payload.get("planJobId") in (None, job_id)
            if "planId" in render_payload:
                assert render_payload["planId"] != "hook-first"
            assert not errors
        finally:
            browser.close()
