"""Transition editing contracts; local mocked APIs only."""

import copy
import json

import pytest
from test_creation_editing_browser import REV, ROOT, STATIC


@pytest.mark.parametrize("stale", [False, True])
def test_replacement_versions(stale):
    legacy = "v2"
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
    editor["subtitleOverrides"] = [
        dict(clipId="0", text="旧字幕"),
        dict(clipId="3", text="保留字幕"),
    ]
    editor["audioMix"] = dict(sourceGainDb=-6, ducking="off", bgm=None)
    for c in clips[1:]:
        c["transitionIn"] = dict(type="crossfade", frames=6)
    candidate = dict(
        candidateId="candidate-b",
        runId="run-b",
        eventId="event-b",
        startUs=10000000,
        endUs=11000000,
        scriptDraft="<img src=x>候选",
        uncertainty="待人评",
        sourceClock=None,
        previewUrl=f"/api/creation/jobs/{ROOT}/candidate-video?planId=chronological&candidateManifestSha256={'f' * 64}&candidateId=candidate-b",
    )
    held_candidates = []
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
            elif "/candidates?" in path:
                if stale:
                    held_candidates.append(r)
                else:
                    r.fulfill(json=dict(candidateManifestSha256="f" * 64, candidates=[candidate]))
            elif r.request.method == "POST":
                payload = json.loads(r.request.post_data)
                posts.append(payload)
                saved = {
                    **copy.deepcopy(editor),
                    "parentJobId": REV,
                    "clips": copy.deepcopy(payload["clips"]),
                    "ancestry": [dict(jobId=ROOT, planId="chronological", kind="plan")],
                }
                saved["candidateManifestSha256"] = payload["candidateManifestSha256"]
                saved["subtitleOverrides"] = payload["subtitleOverrides"]
                saved["audioMix"] = payload["audioMix"]
                for item in payload["replacements"]:
                    for clip in saved["clips"]:
                        if clip["clipId"] == item["targetClipId"]:
                            clip["clipId"] = "new-id"
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

            row(0).locator('[data-action="replace"]').click()
            if stale:
                page.locator("#history button").click()
                page.get_by_role("button", name="选择此方案", exact=True).click()
                for r in held_candidates:
                    r.fulfill(json=dict(candidateManifestSha256="f" * 64, candidates=[candidate]))
                page.wait_for_timeout(100)
                pw.expect(page.locator("#replacement-panel")).to_be_hidden()
                assert not posts
                return
            pw.expect(page.locator("#replacement-candidates")).to_contain_text("<img src=x>候选")
            assert page.locator("#replacement-panel img").count() == 0
            pw.expect(page.locator("#replacement-status")).to_contain_text("原片预览不可用")
            page.locator("#confirm-replacement").click()
            pw.expect(page.locator("#render")).to_be_disabled()
            pw.expect(row(0).locator('[data-field="subtitle-text"]')).to_have_value("")
            pw.expect(row(1).locator('[data-field="transition"]')).to_have_value("cut")
            pw.expect(row(2).locator('[data-field="transition"]')).to_have_value("crossfade")
            page.locator("#save-revision").click()
            pw.expect(row("new-id")).to_be_visible()
            pw.expect(page.locator("#render")).to_be_enabled()
            assert posts[0]["replacements"] == [dict(targetClipId="0", candidateId="candidate-b")]
            assert posts[0]["candidateManifestSha256"] == "f" * 64
            assert posts[0]["clips"][0]["startUs"] == 10000000
            assert posts[0]["clips"][0]["endUs"] == 11000000
            assert posts[0]["subtitleOverrides"] == [dict(clipId="3", text="保留字幕")]
            assert posts[0]["audioMix"] == editor["audioMix"]
            page.reload()
            pw.expect(row("new-id")).to_be_visible()
            assert len(posts) == 1
            page.locator("#save-revision").click()
            pw.expect(page.locator("#render")).to_be_enabled()
            assert posts[1]["replacements"] == []
            assert posts[1]["candidateManifestSha256"] == "f" * 64
            page.locator(f'[data-job-id="{ROOT}"]').click()
            pw.expect(row(0).locator('[data-field="subtitle-text"]')).to_have_value("旧字幕")
        finally:
            browser.close()
