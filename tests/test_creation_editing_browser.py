"""Editing UI contracts against local mocked APIs; no media or paid calls."""

import copy
import json
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
ROOT, REV = "a" * 32, "b" * 32


@pytest.mark.parametrize("scenario", ["edit", "restart", "stale", "captions"])
def test_editing_version_flows(scenario):
    pw = pytest.importorskip("playwright.sync_api")
    clips = [
        dict(
            clipId=str(i),
            startUs=i * 2000000,
            endUs=(i + 1) * 2000000,
            outputFrames=60,
            scriptDraft="<img src=x>",
        )
        for i in range(3)
    ]
    editor = dict(
        parentJobId=ROOT,
        planId="chronological",
        expectedParentReceiptSha256="c" * 64,
        rootReceiptSha256="c" * 64,
        fps=30,
        clips=clips,
        ancestry=[],
    )
    revision = {
        **editor,
        "parentJobId": REV,
        "ancestry": [dict(jobId=ROOT, planId="chronological", kind="plan")],
    }
    plan = dict(
        jobId=ROOT,
        kind="plan",
        status="completed",
        projectId="one",
        createdAt="2026-10-30",
        fps=30,
        plans=[dict(id="chronological", structure="顺序", ready=True, segments=clips)],
    )
    jobs = {
        ROOT: plan,
        REV: dict(
            jobId=REV,
            kind="revision",
            status="completed",
            projectId="one",
            createdAt="2026-10-30",
            editor=revision,
        ),
    }
    editors = {ROOT: editor, REV: revision}
    posts, held = [], []
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page()

        def route(r):
            path = r.request.url.split("http://workspace.test")[1]
            if path == "/creation":
                r.fulfill(
                    body=(STATIC / "creation.html").read_text(encoding="utf-8"),
                    content_type="text/html",
                )
            elif path.startswith("/assets/"):
                r.fulfill(
                    body=(STATIC / path.split("/")[-1]).read_text(encoding="utf-8"),
                    content_type="text/css" if path.endswith("css") else "text/javascript",
                )
            elif path == "/api/creation/platform-profiles":
                r.fulfill(json={"profiles": []})
            elif path == "/api/creation/music":
                r.fulfill(json={"tracks": [], "issues": []})
            elif path == "/api/projects":
                r.fulfill(json={"projects": [{"path": "one"}, {"path": "two"}]})
            elif path.startswith("/api/runs"):
                r.fulfill(json={"runs": []})
            elif r.request.method == "POST":
                posts.append((path, json.loads(r.request.post_data)))
                if path.endswith("revisions"):
                    revision["clips"] = [
                        {
                            **clips[int(c["clipId"])],
                            **c,
                            "endUs": c["startUs"] + (c["outputFrames"] * 1000000 + 29) // 30,
                        }
                        for c in posts[-1][1]["clips"]
                    ]
                    identity = REV if len(posts) == 1 else "d" * 32
                    saved = copy.deepcopy(revision)
                    saved["parentJobId"] = identity
                    saved["subtitleOverrides"] = posts[-1][1].get("subtitleOverrides", [])
                    if identity != REV:
                        saved["ancestry"].append(
                            dict(jobId=REV, planId="chronological", kind="revision")
                        )
                    editors[identity] = saved
                    jobs[identity] = dict(
                        jobId=identity,
                        kind="revision",
                        status="completed",
                        projectId="one",
                        createdAt="2026-10-30",
                        editor=saved,
                    )
                    r.fulfill(
                        status=202,
                        json={"jobId": identity, "kind": "revision", "status": "pending"},
                    )
                else:
                    r.fulfill(status=400, json={"error": "停止于渲染请求验证"})
            elif path.startswith("/api/creation/jobs?"):
                r.fulfill(json={"jobs": [] if "two" in path else list(jobs.values())})
            elif "/edit?" in path:
                if scenario == "stale":
                    held.append(r)
                else:
                    r.fulfill(json=editors[path.split("/jobs/")[1].split("/")[0]])
            else:
                r.fulfill(json=jobs[path.rsplit("/", 1)[-1]])

        page.route("**/*", route)
        try:
            page.goto("http://workspace.test/creation")
            pw.expect(page.locator("#history button")).to_have_count(2)
            if scenario == "restart":
                page.locator("#history button").filter(has_text="剪辑版本").click()
                pw.expect(page.locator("[data-clip-id]")).to_have_count(3)
                page.reload()
                pw.expect(page.locator("[data-clip-id]")).to_have_count(3)
                assert not posts
                page.locator("#render").click()
                pw.expect(page.locator("#notice")).to_contain_text("停止于渲染")
                assert posts[-1][1]["revisionJobId"] == REV
                assert "planJobId" not in posts[-1][1]
            else:
                page.locator("#history button").filter(has_text="方案").click()
                page.get_by_role("button", name="选择此方案", exact=True).click()
                if scenario == "captions":
                    pw.expect(page.locator("[data-clip-id]")).to_have_count(3)
                    row = page.locator('[data-clip-id="0"]')
                    toggle = row.locator('[data-field="subtitle-override"]')
                    text = row.locator('[data-field="subtitle-text"]')
                    pw.expect(toggle).not_to_be_checked()
                    pw.expect(text).to_have_value("")
                    pw.expect(text).to_be_disabled()
                    toggle.check()
                    text.fill("第一次中文字幕")
                    pw.expect(page.locator("#render")).to_be_disabled()
                    page.locator("#save-revision").click()
                    pw.expect(page.locator("#render")).to_be_enabled()
                    assert posts[-1][1]["subtitleOverrides"] == [
                        dict(clipId="0", text="第一次中文字幕")
                    ]
                    text.fill("第二次中文字幕")
                    page.locator("#save-revision").click()
                    pw.expect(page.locator("#render")).to_be_enabled()
                    assert posts[-1][1]["parentJobId"] == REV
                    assert posts[-1][1]["subtitleOverrides"] == [
                        dict(clipId="0", text="第二次中文字幕")
                    ]
                    page.locator(f'[data-job-id="{REV}"]').click()
                    pw.expect(text).to_have_value("第一次中文字幕")
                    toggle.uncheck()
                    page.locator("#save-revision").click()
                    pw.expect(page.locator("#render")).to_be_enabled()
                    assert posts[-1][1]["subtitleOverrides"] == []
                    toggle.check()
                    text.fill("")
                    row.locator('[data-action="down"]').click()
                    page.locator('[data-clip-id="2"] [data-field="subtitle-override"]').check()
                    page.locator('[data-clip-id="2"] [data-field="subtitle-text"]').fill(
                        "待删除字幕"
                    )
                    page.locator('[data-clip-id="2"] [data-action="delete"]').click()
                    page.locator("#save-revision").click()
                    pw.expect(page.locator("#render")).to_be_enabled()
                    assert posts[-1][1]["subtitleOverrides"] == [dict(clipId="0", text="")]
                    assert [c["clipId"] for c in posts[-1][1]["clips"]] == ["1", "0"]
                    page.locator(f'[data-job-id="{ROOT}"]').click()
                    pw.expect(toggle).not_to_be_checked()
                    pw.expect(text).to_have_value("")
                elif scenario == "stale":
                    page.locator("#project").select_option("two")
                    for r in held:
                        r.fulfill(json=editor)
                    page.wait_for_timeout(100)
                    assert page.locator("[data-clip-id]").count() == 0
                    pw.expect(page.locator("#save-revision")).to_be_disabled()
                    assert not posts
                else:
                    pw.expect(page.locator("[data-clip-id]")).to_have_count(3)
                    row = page.locator('[data-clip-id="0"]')
                    row.locator('[data-field="end"]').fill("1.5")
                    row.locator('[data-field="end"]').dispatch_event("change")
                    row.locator('[data-action="down"]').click()
                    page.locator('[data-clip-id="2"] [data-action="delete"]').click()
                    pw.expect(page.locator("#render")).to_be_disabled()
                    page.locator("#save-revision").click()
                    pw.expect(page.locator("#editor-summary")).to_contain_text("3.500 秒")
                    assert posts[0][1]["clips"] == [
                        dict(clipId="1", startUs=2000000, outputFrames=60),
                        dict(clipId="0", startUs=0, outputFrames=45),
                    ]
                    assert page.locator("#editor img").count() == 0
                    page.locator(f'[data-job-id="{ROOT}"]').click()
                    pw.expect(page.locator("[data-clip-id]")).to_have_count(3)
                    assert len(posts) == 1
        finally:
            browser.close()
