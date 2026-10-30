"""Offline platform package browser contracts."""

import copy
import json
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
PUB, RENDER = "b" * 32, "a" * 32


@pytest.mark.parametrize("width", [1366, 390])
def test_package_versions_downloads_refresh_retry_and_stale(width):
    pw = pytest.importorskip("playwright.sync_api")
    profiles = [
        dict(
            Platform=name,
            RuleVersion="local-v1",
            UpdatedAt="2026-10-31",
            Source=dict(kind="local_preset", label="本地设置"),
            Fields=dict(
                video=dict(width=720, height=1280, fit="pad", codec="h264", pixelFormat="yuv420p"),
                cover=dict(width=720, height=1280, fit="pad"),
                limits=dict(
                    maxBytes=None,
                    minDurationMs=None,
                    maxDurationMs=None,
                    titleMaxChars=None,
                    descriptionMaxChars=None,
                    tagMaxCount=None,
                    requiredTags=[],
                ),
            ),
        )
        for name in ["bilibili", "douyin", "kuaishou", "xiaohongshu"]
    ]
    snapshot = dict(
        publicationJobId=PUB,
        publicationReceiptSha256="e" * 64,
        renderJobId=RENDER,
        expectedRenderReceiptSha256="c" * 64,
        fps=30,
        frames=35,
        coverFrame=0,
        title="标题",
        description="简介",
        tags=[],
        videoUrl=f"/api/creation/jobs/{RENDER}/video",
    )
    jobs = {
        PUB: dict(
            jobId=PUB,
            kind="publication",
            status="completed",
            projectId="one",
            createdAt="2026-10-31",
        )
    }
    posts, errors, held = [], [], []
    hold = False
    fail = True
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))

        def route(r):
            nonlocal fail
            path = r.request.url.split("http://workspace.test")[1]
            if path == "/creation":
                r.fulfill(
                    body=(STATIC / "creation.html").read_text("utf-8"), content_type="text/html"
                )
            elif path.startswith("/assets/"):
                r.fulfill(
                    body=(STATIC / path.rsplit("/", 1)[1]).read_text("utf-8"),
                    content_type="text/css" if path.endswith("css") else "text/javascript",
                )
            elif path == "/api/projects":
                r.fulfill(json={"projects": [{"path": "one"}, {"path": "two"}]})
            elif path == "/api/creation/music":
                r.fulfill(json={"tracks": []})
            elif path == "/api/creation/platform-profiles":
                r.fulfill(json={"profiles": profiles})
            elif path.startswith("/api/runs"):
                r.fulfill(json={"runs": []})
            elif r.request.method == "POST":
                assert path == "/api/creation/packages"
                body = json.loads(r.request.post_data)
                posts.append(body)
                if fail:
                    fail = False
                    r.fulfill(status=503, json={"error": "稍后重试"})
                    return
                identity = str(len(posts)) * 32
                data = dict(
                    profile=copy.deepcopy(body["profile"]),
                    publicationJobId=PUB,
                    generationStatus="completed",
                    localChecks="fail",
                    publicationEligibility="blocked",
                    validation={
                        "officialRules": "unknown",
                        "limits": "not_configured",
                        "detail": "<img src=x onerror=window.injected=true>",
                    },
                    artifacts={},
                )
                jobs[identity] = dict(
                    jobId=identity,
                    kind="package",
                    status="completed",
                    projectId="one",
                    createdAt="2026-10-31",
                    package=data,
                )
                r.fulfill(status=202, json={"jobId": identity})
            elif path.startswith("/api/creation/jobs?"):
                r.fulfill(json={"jobs": list(jobs.values()) if "one" in path else []})
            elif path.endswith("/publication"):
                r.fulfill(json=snapshot)
            elif (
                "/package-files/" in path
                or "/publication-files/" in path
                or path.endswith("/video")
            ):
                r.fulfill(status=204)
            elif hold:
                held.append(r)
            else:
                r.fulfill(json=jobs[path.rsplit("/", 1)[1]])

        page.route("**/*", route)
        try:
            page.goto("http://workspace.test/creation")
            page.locator("#history button").click()
            pw.expect(page.locator("#package-form")).to_be_visible()
            page.locator("#video-width").fill("480")
            page.locator("#max-bytes").fill("1")
            page.locator("#required-tags").fill("中文")
            page.locator("#generate-package").click()
            pw.expect(page.locator("#notice")).to_contain_text("稍后重试")
            page.locator("#generate-package").click()
            pw.expect(page.locator("#package-result")).to_be_visible()
            assert posts[0] == posts[1]
            assert set(posts[1]) == {
                "requestId",
                "publicationJobId",
                "expectedPublicationReceiptSha256",
                "profile",
            }
            assert posts[1]["profile"]["RuleVersion"] != "local-v1"
            pw.expect(page.locator("#package-status")).to_contain_text("未通过")
            pw.expect(page.locator("#package-status")).to_contain_text("仅供测试")
            pw.expect(page.locator("#package-validation")).to_contain_text("未知")
            assert page.locator("#package-downloads a").count() == 8
            assert page.evaluate("window.injected") is None
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.reload()
            pw.expect(page.locator("#video-width")).to_have_value("480")
            assert len(posts) == 2
            page.locator("#package-platform").select_option("douyin")
            pw.expect(page.locator("#video-width")).to_have_value("720")
            page.locator("#generate-package").click()
            pw.expect(
                page.locator("#package-downloads [data-file='package.zip']")
            ).to_have_attribute("href", f"/api/creation/jobs/{'3' * 32}/package-files/package.zip")
            assert jobs["2" * 32]["package"]["profile"]["Fields"]["video"]["width"] == 480
            for name in ["kuaishou", "xiaohongshu"]:
                page.locator("#package-platform").select_option(name)
                page.locator("#generate-package").click()
                pw.expect(
                    page.locator("#package-downloads [data-file='package.zip']")
                ).to_have_attribute(
                    "href", f"/api/creation/jobs/{str(len(posts)) * 32}/package-files/package.zip"
                )
            assert [p["profile"]["Platform"] for p in posts[1:]] == [
                "bilibili",
                "douyin",
                "kuaishou",
                "xiaohongshu",
            ]
            jobs["5" * 32]["package"]["publicationEligibility"] = "unverified"
            page.reload()
            pw.expect(page.locator("#package-status")).to_contain_text("发布资格：未核实")
            assert len(posts) == 5
            page.locator("#history button").nth(1).click()
            pw.expect(page.locator("#video-width")).to_have_value("480")
            assert len(posts) == 5
            hold = True
            page.locator("#refresh").click()
            page.wait_for_timeout(100)
            assert held
            page.locator("#project").select_option("two")
            held[0].fulfill(json=jobs["3" * 32])
            pw.expect(page.locator("#package-result")).to_be_hidden()
            assert len(posts) == 5
            assert not errors
        finally:
            browser.close()
