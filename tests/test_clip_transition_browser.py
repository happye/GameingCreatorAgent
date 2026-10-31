"""Transition editing contracts; local mocked APIs only."""

import copy
import json

import pytest
from test_creation_editing_browser import REV, ROOT, STATIC


@pytest.mark.parametrize("legacy", ["v1", "v2"])
def test_transition_versions(legacy, history_hangs=False):
    pw = pytest.importorskip("playwright.sync_api")
    clips = [
        dict(
            clipId=str(i),
            startUs=i * 2000000,
            endUs=(i + 1) * 2000000,
            outputFrames=60,
            speed=dict(numerator=1, denominator=1),
        )
        for i in range(5)
    ]
    if legacy == "v1":
        for clip in clips:
            del clip["speed"]
    editor = dict(
        parentJobId=ROOT,
        planId="chronological",
        fps=30,
        clips=clips,
        expectedParentReceiptSha256="c" * 64,
        ancestry=[],
    )
    saved = None
    posts = []
    hold_history = False
    held_history = []
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page()

        def route(r):
            nonlocal saved
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
            elif path == "/api/projects":
                r.fulfill(json={"projects": [{"path": "one"}]})
            elif path.startswith("/api/runs"):
                r.fulfill(json={"runs": []})
            elif path.endswith("/music"):
                r.fulfill(json={"tracks": [], "issues": []})
            elif path.endswith("/platform-profiles"):
                r.fulfill(json={"profiles": []})
            elif r.request.method == "POST":
                payload = json.loads(r.request.post_data)
                posts.append(payload)
                saved = {
                    **copy.deepcopy(editor),
                    "parentJobId": REV,
                    "clips": copy.deepcopy(payload["clips"]),
                    "ancestry": [dict(jobId=ROOT, planId="chronological", kind="plan")],
                }
                for clip in saved["clips"]:
                    clip["outputFrames"] = 60
                r.fulfill(status=202, json=dict(jobId=REV, kind="revision", status="pending"))
            elif path.startswith("/api/creation/jobs?") and hold_history:
                held_history.append(r)
            elif path.startswith("/api/creation/jobs?"):
                r.fulfill(
                    json={
                        "jobs": [
                            dict(
                                jobId=ROOT,
                                kind="plan",
                                status="completed",
                                projectId="one",
                                plans=[dict(id="chronological", ready=True, structure="顺序")],
                            )
                        ]
                    }
                )
            elif path.endswith("/" + ROOT):
                r.fulfill(
                    json=dict(
                        jobId=ROOT,
                        kind="plan",
                        status="completed",
                        projectId="one",
                        plans=[dict(id="chronological", ready=True, structure="顺序")],
                    )
                )
            elif "/edit?" in path:
                r.fulfill(json=saved if REV in path else editor)
            else:
                r.fulfill(
                    json=dict(
                        jobId=REV,
                        kind="revision",
                        status="completed",
                        projectId="one",
                        editor=saved,
                    )
                )

        page.route("**/*", route)
        try:
            page.goto("http://workspace.test/creation")
            page.locator("#history button").click()
            page.get_by_role("button", name="选择此方案", exact=True).click()

            def row(i):
                return page.locator(f'[data-clip-id="{i}"]')

            def fade(i, n):
                row(i).locator('[data-field="transition"]').select_option("crossfade")
                field = row(i).locator('[data-field="transition-frames"]')
                field.fill(str(n))
                field.dispatch_event("change")

            pw.expect(row(0).locator('[data-field="transition"]')).to_be_disabled()
            for i in range(5):
                pw.expect(row(i).locator('[data-field="transition"]')).to_have_value("cut")
            fade(1, 6)
            fade(2, 55)
            pw.expect(page.locator("#save-revision")).to_be_disabled()
            pw.expect(page.locator("#render")).to_be_disabled()
            pw.expect(page.locator("#editor-summary")).to_contain_text("不能三重重叠")
            field = row(2).locator('[data-field="transition-frames"]')
            for invalid in ["0", "-1", "1.5", ""]:
                field.fill(invalid)
                field.dispatch_event("change")
                pw.expect(page.locator("#save-revision")).to_be_disabled()
            field.fill("6")
            field.dispatch_event("change")
            fade(4, 8)
            pw.expect(page.locator("#editor-summary")).to_contain_text("280 帧")
            pw.expect(row(1)).to_contain_text("输出起点 54 帧")
            page.locator("#save-revision").click()
            pw.expect(page.locator("#render")).to_be_enabled()
            assert posts[0]["clips"][1]["transitionIn"] == dict(type="crossfade", frames=6)
            assert all(
                set(c) == {"clipId", "startUs", "endUs", "speed", "transitionIn"}
                for c in posts[0]["clips"]
            )
            hold_history = history_hangs
            page.reload()
            pw.expect(row(4).locator('[data-field="transition-frames"]')).to_have_value("8")
            assert len(posts) == 1
            if history_hangs:
                assert held_history
                pw.expect(page.locator("#history button")).to_have_count(0)
                pw.expect(page.locator("#render")).to_be_enabled()
            row(1).locator('[data-action="delete"]').click()
            pw.expect(row(2).locator('[data-field="transition"]')).to_have_value("cut")
            pw.expect(row(4).locator('[data-field="transition-frames"]')).to_have_value("8")
            row(0).locator('[data-action="down"]').click()
            pw.expect(row(0).locator('[data-field="transition"]')).to_have_value("cut")
            pw.expect(row(3).locator('[data-field="transition"]')).to_have_value("cut")
            pw.expect(row(4).locator('[data-field="transition-frames"]')).to_have_value("8")
            page.locator(f'[data-job-id="{ROOT}"]').click()
            pw.expect(page.locator("[data-clip-id]")).to_have_count(5)
            pw.expect(page.locator("#editor-summary")).to_contain_text("300 帧")
            assert len(posts) == 1
        finally:
            browser.close()


def test_revision_restores_while_history_hangs():
    test_transition_versions("v2", history_hangs=True)
