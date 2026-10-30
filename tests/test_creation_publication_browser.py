"""Publication editor browser contracts; offline mocked APIs, no render dispatch."""

import json
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
RENDER, ASSET = "a" * 32, "b" * 32


@pytest.mark.parametrize("width", [1366, 390])
def test_publication_save_reopen_refresh_and_stale(width):
    pw = pytest.importorskip("playwright.sync_api")
    snapshot = dict(
        renderJobId=RENDER,
        expectedRenderReceiptSha256="c" * 64,
        coverFrame=0,
        title="模板标题",
        description="模板简介",
        tags=["游戏"],
        frames=35,
        fps={"numerator": 30, "denominator": 1},
        width=1280,
        height=720,
        videoUrl=f"/api/creation/jobs/{RENDER}/video",
        draftStatus="editable-template-not-ai",
    )
    jobs = {
        RENDER: dict(
            jobId=RENDER,
            kind="render",
            status="completed",
            projectId="one",
            createdAt="2026-10-31",
            artifact={
                "previewUrl": snapshot["videoUrl"],
                "downloadUrl": snapshot["videoUrl"],
                "sizeBytes": 123,
            },
        )
    }
    snapshots = {RENDER: snapshot}
    posts, held, errors = [], [], []
    hold = False
    fail = True
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900})
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
                r.fulfill(json={"tracks": [], "issues": []})
            elif path.startswith("/api/runs"):
                r.fulfill(json={"runs": []})
            elif r.request.method == "POST":
                assert path == "/api/creation/publications"
                body = json.loads(r.request.post_data)
                posts.append(body)
                if fail:
                    fail = False
                    r.fulfill(status=503, json={"error": "稍后重试"})
                else:
                    identity = ASSET if len(posts) == 2 else "d" * 32
                    snapshots[identity] = {
                        **snapshot,
                        **{k: body[k] for k in ("title", "description", "tags", "coverFrame")},
                    }
                    jobs[identity] = dict(
                        jobId=identity,
                        kind="publication",
                        status="completed",
                        projectId="one",
                        createdAt="2026-10-31",
                    )
                    r.fulfill(
                        status=202,
                        json={"jobId": identity, "kind": "publication", "status": "pending"},
                    )
            elif path.startswith("/api/creation/jobs?"):
                r.fulfill(json={"jobs": list(jobs.values()) if "one" in path else []})
            elif path.endswith("/publication"):
                if hold:
                    held.append(r)
                else:
                    r.fulfill(json=snapshots[path.split("/jobs/")[1].split("/")[0]])
            elif "/video" in path or "/publication-files/" in path:
                r.fulfill(status=204)
            else:
                r.fulfill(json=jobs[path.rsplit("/", 1)[1]])

        page.route("**/*", route)
        try:
            page.goto("http://workspace.test/creation")
            page.locator("#history button").click()
            pw.expect(page.locator("#publication-title")).to_have_value("模板标题")
            assert not posts
            page.locator("video").evaluate("video => { video.currentTime = 0.2; }")
            page.locator("#use-cover-frame").click()
            pw.expect(page.locator("#cover-frame")).to_have_value("6")
            page.locator("#cover-frame").fill("6")
            title = '中文标题<img src=x onerror="window.injected=true">'
            page.locator("#publication-title").fill(title)
            page.locator("#publication-description").fill("我的简介")
            page.locator("#publication-tags").fill("攻略，中文\n精彩")
            page.locator("#save-publication").click()
            pw.expect(page.locator("#notice")).to_contain_text("稍后重试")
            page.locator("#save-publication").click()
            pw.expect(page.locator("#publication-cover")).to_be_visible()
            assert posts[0] == posts[1]
            assert set(posts[1]) == {
                "requestId",
                "renderJobId",
                "expectedRenderReceiptSha256",
                "coverFrame",
                "title",
                "description",
                "tags",
            }
            assert posts[1]["coverFrame"] == 6
            assert posts[1]["tags"] == ["攻略", "中文", "精彩"]
            for file in [
                "cover.png",
                "title.txt",
                "description.txt",
                "tags.json",
                "publication.json",
            ]:
                pw.expect(
                    page.locator(f'#publication-downloads [data-file="{file}"]')
                ).to_have_attribute("href", f"/api/creation/jobs/{ASSET}/publication-files/{file}")
            assert page.evaluate("window.injected") is None
            assert page.locator("#publication-form img").count() == 1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.reload()
            pw.expect(page.locator("#publication-title")).to_have_value(title)
            assert len(posts) == 2
            snapshots[ASSET]["tags"] = ["PvP, PvE"]
            page.reload()
            pw.expect(page.locator("#publication-tags")).to_have_value("PvP, PvE")
            page.locator("#publication-title").fill("第二版")
            page.locator("#save-publication").click()
            pw.expect(page.locator("#publication-title")).to_have_value("第二版")
            assert posts[-1]["tags"] == ["PvP, PvE"]
            pw.expect(page.locator("#publication-cover")).to_have_attribute(
                "src", f"/api/creation/jobs/{'d' * 32}/publication-files/cover.png"
            )
            page.locator("#history button").nth(1).click()
            pw.expect(page.locator("#publication-title")).to_have_value(title)
            assert len(posts) == 3
            hold = True
            page.locator("#refresh").click()
            page.wait_for_timeout(100)
            assert held
            page.locator("#project").select_option("two")
            held[0].fulfill(json=snapshots[ASSET])
            pw.expect(page.locator("#publication-form")).to_be_hidden()
            assert len(posts) == 3
            assert not errors
        finally:
            browser.close()
