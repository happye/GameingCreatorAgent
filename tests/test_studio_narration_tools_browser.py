"""Studio narration tools: handwritten draft, copy/TXT, citations, restore; no paid voice."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_narration_jobs import choice, done, engine  # noqa: F401
from test_studio_audio_graph_browser import saved_plan  # noqa: F401

from gamingcreator.application.browser_source_clock import runtime_clock_document
from gamingcreator.ui import server

EVIDENCE = Path(".cache/scratch/grok-studio-tools-20261108")


@pytest.fixture
def studio_plan(service, engine, monkeypatch):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    root, track, asset = saved_plan(service, monkeypatch)
    job = service.get(root)
    plan_id = next(p["id"] for p in job["plans"] if p.get("ready"))

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "sourceName": "tone.mp4",
                    "status": "completed",
                    "sourceClock": runtime_clock_document(asset),
                }
            ]
        }

    monkeypatch.setattr(server, "project_runs_payload", runs)
    http = server.create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps(
                {"artifacts/project": {"id": root, "kind": "plan", "planId": plan_id}}
            )
            page.add_init_script(
                f"localStorage.setItem('studio-v1', {prefs!r});"
                f"localStorage.setItem('studio-last-job-v1', {last!r});"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            posts = []

            def track(route):
                if route.request.method == "POST":
                    posts.append(route.request.url.split("?")[0])
                route.continue_()

            page.route("**/api/**", track)
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            pw.expect(page.locator(".timeline .clip").first).to_be_visible(timeout=60000)
            pw.expect(page.get_by_role("status", name="版本保存状态")).to_be_visible(timeout=60000)
            page.get_by_role("tab", name="声音", exact=True).click()
            pw.expect(page.get_by_role("button", name="起草旁白稿", exact=True)).to_be_visible()
            yield SimpleNamespace(
                page=page,
                expect=pw.expect,
                posts=posts,
                root=root,
                plan_id=plan_id,
                port=http.server_port,
                service=service,
                asset=asset,
            )
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def test_handwrite_count_copy_download_and_no_tasks(studio_plan):
    page, expect = studio_plan.page, studio_plan.expect
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    posts_before = list(studio_plan.posts)

    page.get_by_role("button", name="手写旁白稿", exact=True).click()
    expect(page.get_by_role("textbox", name="旁白稿")).to_be_visible()
    expect(page.locator(".audio-panel .hint").first).to_contain_text("手写")

    page.get_by_role("textbox", name="旁白稿").fill("中A😀")
    expect(page.get_by_label("旁白字符数")).to_have_text("3 字")

    page.evaluate(
        """() => {
        window.__copied = null;
        navigator.clipboard.writeText = async (text) => { window.__copied = text; };
    }"""
    )
    page.get_by_role("button", name="草稿复制旁白稿").click()
    expect(page.locator('p.note[role="status"]').filter(has_text="已复制")).to_be_visible()
    assert page.evaluate("window.__copied") == "中A😀"

    with page.expect_download() as download_info:
        page.get_by_role("button", name="草稿下载旁白TXT").click()
    download = download_info.value
    assert download.suggested_filename == "narration-draft.txt"
    target = EVIDENCE / "narration-draft.txt"
    download.save_as(target)
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8") == "中A😀"

    page.get_by_role("textbox", name="旁白稿").fill("")
    expect(page.get_by_role("button", name="草稿复制旁白稿")).to_be_disabled()
    expect(page.get_by_role("button", name="草稿下载旁白TXT")).to_be_disabled()

    new_posts = [u for u in studio_plan.posts if u not in posts_before]
    assert not any(u.endswith("/api/creation/narrations") for u in new_posts)
    assert not any(u.endswith("/api/creation/plans") for u in new_posts)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.screenshot(path=str(EVIDENCE / "narration-handwrite-1440x900.png"))


def test_clipboard_failure_keeps_text(studio_plan):
    page, expect = studio_plan.page, studio_plan.expect
    page.get_by_role("button", name="手写旁白稿", exact=True).click()
    page.get_by_role("textbox", name="旁白稿").fill("保持原文")
    page.evaluate(
        """() => {
        navigator.clipboard.writeText = async () => { throw new Error('denied'); };
    }"""
    )
    page.get_by_role("button", name="草稿复制旁白稿").click()
    expect(page.locator('p.note[role="status"]').filter(has_text="无法自动复制")).to_be_visible()
    expect(page.get_by_role("textbox", name="旁白稿")).to_have_value("保持原文")


def test_draft_citations_edit_restore_and_late_isolation(studio_plan):
    page, expect = studio_plan.page, studio_plan.expect
    draft_body = {
        "schemaVersion": "creation-narration-script-v1",
        "text": "原始旁白一句。",
        "charactersPerSecond": 3.5,
        "citations": [
            {
                "entryId": "e" * 64,
                "text": "引用句",
                "citation": "（来源：官方说明·官网，2026-11-01）",
            }
        ],
    }
    page.evaluate(
        """() => {
        const original = window.fetch;
        window.pendingDrafts = [];
        window.fetch = (url, options) => String(url).includes('/narration-script')
            ? new Promise((resolve, reject) => pendingDrafts.push({resolve, reject}))
            : original(url, options);
    }"""
    )
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    page.evaluate(
        """(payload) => {
        pendingDrafts[0].resolve(new Response(JSON.stringify(payload), {
            status: 200, headers: {'Content-Type': 'application/json'}
        }));
    }""",
        draft_body,
    )
    expect(page.get_by_role("textbox", name="旁白稿")).to_have_value("原始旁白一句。")
    expect(page.get_by_label("旁白知识引用")).to_contain_text("引用句")
    expect(page.get_by_label("旁白知识引用")).to_contain_text("官方说明")
    assert "官方说明" not in page.get_by_role("textbox", name="旁白稿").input_value()

    page.get_by_role("textbox", name="旁白稿").fill("原始旁白一句。已编辑")
    expect(page.get_by_text("起草时参考资料，正文已编辑，请核对", exact=True)).to_be_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="恢复起草原文").click()
    expect(page.get_by_role("textbox", name="旁白稿")).to_have_value("原始旁白一句。")
    expect(page.get_by_text("起草时参考资料，正文已编辑，请核对", exact=True)).to_have_count(0)

    page.reload()
    page.get_by_role("tab", name="声音", exact=True).click()
    expect(page.get_by_role("textbox", name="旁白稿", exact=True)).to_have_value("原始旁白一句。")
    # Explicitly clear this restored draft before the independent late-response scenario.
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="清除本机草稿", exact=True).click()
    page.reload()
    page.get_by_role("tab", name="声音", exact=True).click()
    expect(page.get_by_role("button", name="起草旁白稿", exact=True)).to_be_visible()
    page.evaluate(
        """() => {
        const original = window.fetch;
        window.pendingDrafts = [];
        window.fetch = (url, options) => String(url).includes('/narration-script')
            ? new Promise((resolve, reject) => pendingDrafts.push({resolve, reject}))
            : original(url, options);
    }"""
    )
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    page.get_by_role("tab", name="素材", exact=True).click()
    page.evaluate(
        """(payload) => {
        pendingDrafts[0].resolve(new Response(JSON.stringify(payload), {
            status: 200, headers: {'Content-Type': 'application/json'}
        }));
    }""",
        draft_body,
    )
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    page.get_by_role("tab", name="剪辑", exact=True).click()
    page.get_by_role("tab", name="声音", exact=True).click()
    expect(page.get_by_role("button", name="起草旁白稿", exact=True)).to_be_visible()
    expect(page.get_by_role("textbox", name="旁白稿")).to_have_count(0)


def test_attached_narration_copy_download(service, engine, monkeypatch):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    root, track, asset = saved_plan(service, monkeypatch)
    narration = done(service, text="已挂接旁白正文")
    edit = service.edit(root, "hook-first")
    rows = [
        {
            **{k: row[k] for k in ("clipId", "startUs", "endUs")},
            "speed": {"numerator": 1, "denominator": 1},
        }
        for row in edit["clips"][:2]
    ]
    rows[0]["transitionIn"] = {"type": "cut", "frames": 0}
    rows[1]["transitionIn"] = {"type": "crossfade", "frames": 30}
    request_body = dict(
        requestId="d" * 32,
        parentJobId=root,
        planId="hook-first",
        expectedParentReceiptSha256=edit["expectedParentReceiptSha256"],
        clips=rows,
        audioMix=dict(sourceGainDb=-60, bgm=None, ducking="off"),
        narration=choice(narration, start=15, gain=-60),
    )
    revision = service.submit("revision", request_body)["jobId"]
    completed = finish(service, revision)
    assert completed["status"] == "completed", completed

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "sourceName": "tone.mp4",
                    "status": "completed",
                    "sourceClock": runtime_clock_document(asset),
                }
            ]
        }

    monkeypatch.setattr(server, "project_runs_payload", runs)
    http = server.create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps({"artifacts/project": {"id": revision, "kind": "revision"}})
            page.add_init_script(
                f"localStorage.setItem('studio-v1', {prefs!r});"
                f"localStorage.setItem('studio-last-job-v1', {last!r});"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            pw.expect(page.locator(".timeline .clip").first).to_be_visible(timeout=60000)
            page.get_by_role("tab", name="声音", exact=True).click()
            pw.expect(page.get_by_text("已挂接旁白正文", exact=False)).to_be_visible()
            page.evaluate(
                """() => {
                window.__copied = null;
                navigator.clipboard.writeText = async (text) => { window.__copied = text; };
            }"""
            )
            page.get_by_role("button", name="已挂接复制旁白稿").click()
            assert page.evaluate("window.__copied") == "已挂接旁白正文"
            with page.expect_download() as download_info:
                page.get_by_role("button", name="已挂接下载旁白TXT").click()
            download = download_info.value
            assert download.suggested_filename == "narration-draft.txt"
            target = EVIDENCE / "attached-narration-draft.txt"
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            download.save_as(target)
            assert target.read_text(encoding="utf-8") == "已挂接旁白正文"
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(EVIDENCE / "narration-attached-1280x720.png"))
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


EVIDENCE_R2 = Path(".cache/scratch/grok-studio-round2-20261108")


def test_r04_whitespace_only_disables_copy_download(studio_plan):
    """R04: trim-empty disables buttons; spaced text keeps raw bytes on copy/download."""
    page = studio_plan.page
    EVIDENCE_R2.mkdir(parents=True, exist_ok=True)
    page.get_by_role("button", name="手写旁白稿", exact=True).click()
    box = page.get_by_role("textbox", name="旁白稿")
    box.fill(" \n\t")
    copy_btn = page.get_by_role("button", name="草稿复制旁白稿")
    dl_btn = page.get_by_role("button", name="草稿下载旁白TXT")
    assert copy_btn.is_disabled()
    assert dl_btn.is_disabled()
    box.fill(" 前后有空格的正文 ")
    assert not copy_btn.is_disabled()
    assert not dl_btn.is_disabled()
    page.evaluate(
        """() => {
        window.__copied = null;
        navigator.clipboard.writeText = async (text) => { window.__copied = text; };
    }"""
    )
    copy_btn.click()
    assert page.evaluate("window.__copied") == " 前后有空格的正文 "
    with page.expect_download() as info:
        dl_btn.click()
    download = info.value
    target = EVIDENCE_R2 / "r04-narration-draft.txt"
    download.save_as(str(target))
    assert target.read_text(encoding="utf-8") == " 前后有空格的正文 "


def test_r08_draft_identity_switch_protection(studio_plan):
    """R08: workspace unmount A→B late fail must not clear newer draft busy/text."""
    page, expect = studio_plan.page, studio_plan.expect
    page.evaluate(
        """() => {
        const original = window.fetch;
        window.__draftGate = [];
        window.fetch = (url, options) => {
            if (String(url).includes('/narration-script')) {
                return new Promise((resolve, reject) => window.__draftGate.push({resolve, reject, url: String(url)}));
            }
            return original(url, options);
        };
    }"""
    )
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    expect(page.get_by_role("button", name="正在起草…", exact=True)).to_be_visible()
    # Unmount EditWorkspace (bumps draftEpoch), then reopen sound and start B.
    page.get_by_role("tab", name="素材", exact=True).click()
    page.get_by_role("tab", name="剪辑", exact=True).click()
    page.get_by_role("tab", name="声音", exact=True).click()
    expect(page.get_by_role("button", name="起草旁白稿", exact=True)).to_be_visible()
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    expect(page.get_by_role("button", name="正在起草…", exact=True)).to_be_visible()
    page.evaluate("() => __draftGate[0].reject(new TypeError('late draft fail A'))")
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    expect(page.get_by_role("button", name="正在起草…", exact=True)).to_be_visible()
    page.evaluate(
        """() => __draftGate[1].resolve(new Response(JSON.stringify({
            schemaVersion: 'creation-narration-script-v1',
            text: '当前草稿B',
            charactersPerSecond: 3.5,
            citations: []
        }), {status: 200, headers: {'Content-Type': 'application/json'}}))"""
    )
    expect(page.get_by_role("textbox", name="旁白稿")).to_have_value("当前草稿B")
