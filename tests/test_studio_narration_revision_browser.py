"""Round2: editable attached narration, localStorage drafts, local resynth (paid=false)."""

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

EVIDENCE = Path(".cache/scratch/grok-studio-round2-20261108")


def _attached_studio(service, engine, monkeypatch, text="旧旁白音轨正文", start=30, gain=-6):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    root, track, asset = saved_plan(service, monkeypatch)
    narration = done(service, text=text)
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
    # Attach registered BGM if music catalog has the saved track.
    bgm = dict(trackId=track.track_id, trackReceiptSha256=track.receipt_sha256, gainDb=-12)
    request_body = dict(
        requestId="e" * 32,
        parentJobId=root,
        planId="hook-first",
        expectedParentReceiptSha256=edit["expectedParentReceiptSha256"],
        clips=rows,
        audioMix=dict(sourceGainDb=-60, bgm=bgm, ducking="off"),
        narration=choice(narration, start=start, gain=gain, duck="off"),
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
    browser = None
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps({"artifacts/project": {"id": revision, "kind": "revision"}})
            page.add_init_script(
                f"localStorage.setItem('studio-v1', {prefs!r});"
                f"localStorage.setItem('studio-last-job-v1', {last!r});"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            posts = []

            def track_route(route):
                if route.request.method == "POST":
                    posts.append(route.request.url.split("?")[0])
                route.continue_()

            page.route("**/api/**", track_route)
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            pw.expect(page.locator(".timeline .clip").first).to_be_visible(timeout=60000)
            page.get_by_role("tab", name="声音", exact=True).click()
            pw.expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(text)
            asset_resp = page.request.get(
                f"http://127.0.0.1:{http.server_port}/assets/studio/narration_drafts.js"
            )
            assert asset_resp.status == 200
            yield SimpleNamespace(
                page=page,
                expect=pw.expect,
                posts=posts,
                revision=revision,
                narration=narration,
                root=root,
                track=track,
                port=http.server_port,
                service=service,
                errors=errors,
                text=text,
                start=start,
                gain=gain,
            )
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


@pytest.fixture
def attached(service, engine, monkeypatch):  # noqa: F811
    gen = _attached_studio(service, engine, monkeypatch)
    value = next(gen)
    try:
        yield value
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_r21_r23_r24_r29_edit_draft_restore_clear(attached):
    page, expect = attached.page, attached.expect
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    posts_before = list(attached.posts)
    page.get_by_role("button", name="编辑旁白文字", exact=True).click()
    box = page.get_by_role("textbox", name="旁白待合成稿")
    expect(box).to_have_value(attached.text)
    expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(attached.text)
    # Opening editor must not create voice/create tasks.
    assert not any(
        u.endswith("/api/creation/narrations") for u in attached.posts[len(posts_before) :]
    )

    box.fill("本机未合成修订稿")
    # Draft key uses project/job/plan/asset identity.
    stored = page.evaluate(
        """() => {
        const keys = Object.keys(localStorage).filter(k => k.startsWith('studio-narration-draft-v1:'));
        return keys.map(k => ({key: k, value: localStorage.getItem(k)}));
    }"""
    )
    assert stored, "expected localStorage draft"
    envelope = json.loads(stored[0]["value"])
    assert envelope["schemaVersion"] == "studio-narration-draft-v1"
    assert envelope["text"] == "本机未合成修订稿"
    assert "fee" not in envelope and "receipt" not in envelope and "media" not in envelope

    page.get_by_role("button", name="取消文字编辑", exact=True).click()
    expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(attached.text)
    page.get_by_role("button", name="编辑旁白文字", exact=True).click()
    expect(page.get_by_role("textbox", name="旁白待合成稿")).to_have_value("本机未合成修订稿")
    expect(page.get_by_label("旁白修订状态")).to_contain_text("来源需重新核对")

    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="清除本机草稿", exact=True).click()
    expect(page.get_by_role("textbox", name="旁白待合成稿")).to_have_value("本机未合成修订稿")

    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="清除本机草稿", exact=True).click()
    expect(page.get_by_label("旁白修订状态")).to_contain_text("已清除本机草稿")
    expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(attached.text)
    page.screenshot(path=str(EVIDENCE / "narration-revision-editor-1440x900.png"))


def test_r25_r26_r27_local_resynth_success_and_fail(attached):
    page, expect = attached.page, attached.expect
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    page.get_by_role("button", name="编辑旁白文字", exact=True).click()
    page.get_by_role("textbox", name="旁白待合成稿").fill("新旁白重合成正文")
    # Failure path: force settle failure once.
    page.evaluate(
        """() => {
        const original = window.fetch;
        window.__failOnce = true;
        window.fetch = async (url, options) => {
            const u = String(url);
            const method = (options && options.method) || 'GET';
            if (window.__failOnce && method === 'POST' && u.includes('/api/creation/narrations')) {
                window.__failOnce = false;
                return new Response(JSON.stringify({error: {message: 'forced narrations fail'}}), {
                    status: 500, headers: {'Content-Type': 'application/json'}
                });
            }
            return original(url, options);
        };
    }"""
    )
    page.get_by_role("button", name="本机重新合成", exact=True).click()
    expect(page.get_by_label("旁白修订状态")).to_contain_text("保留旧音轨", timeout=60000)
    expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(attached.text)
    expect(page.get_by_role("textbox", name="旁白待合成稿")).to_have_value("新旁白重合成正文")

    # Success path with real fake local engine.
    page.get_by_role("button", name="本机重新合成", exact=True).click()
    # On success the pending editor closes; assert via attached track text + preserved params.
    expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(
        "新旁白重合成正文", timeout=120000
    )
    expect(page.get_by_role("textbox", name="旁白待合成稿")).to_have_count(0)
    start_input = page.locator("label:has-text('起点') input")
    expect(start_input).to_have_value("1.0")
    expect(page.locator("label:has-text('旁白音量') select")).to_have_value("-6")
    page.screenshot(path=str(EVIDENCE / "narration-resynth-success-1440x900.png"))

    def read_edit(job_id):
        response = page.request.get(
            f"http://127.0.0.1:{attached.port}/api/creation/jobs/{job_id}/edit?planId=hook-first"
        )
        assert response.ok, response.text()
        return response.json()

    old = read_edit(attached.revision)
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(page.get_by_role("button", name="保存版本", exact=True)).to_be_disabled()
    expect(page.get_by_label("版本保存状态")).to_have_text("修改镜头、声音或叠加后可保存新版本")
    saved = json.loads(page.evaluate("localStorage.getItem('studio-last-job-v1')"))
    new_id = saved["artifacts/project"]["id"]
    assert new_id != attached.revision
    new = read_edit(new_id)
    assert new["narration"]["assetJobId"] != old["narration"]["assetJobId"]
    assert new["narrationAsset"]["text"] == "新旁白重合成正文"
    assert new["narration"]["startFrame"] == 30
    assert new["narration"]["gainDb"] == -6
    assert new["audioMix"] == old["audioMix"]
    assert read_edit(attached.revision) == old


def test_resynth_late_result_preserves_undone_audio(attached):
    page, expect = attached.page, attached.expect
    start = page.locator("label:has-text('起点') input")
    start.fill("2.0")
    start.press("Tab")
    page.get_by_role("button", name="编辑旁白文字", exact=True).click()
    page.get_by_role("textbox", name="旁白待合成稿").fill("迟到的新旁白")
    page.evaluate("""() => {
        const original = window.fetch;
        window.fetch = async (...args) => {
            const response = await original(...args);
            if (String(args[0]).includes('/api/creation/narrations') && args[1]?.method === 'POST') {
                await new Promise(resolve => { window.releaseNarration = resolve; });
            }
            return response;
        };
    }""")
    page.get_by_role("button", name="本机重新合成", exact=True).click()
    page.wait_for_function("() => !!window.releaseNarration")
    page.get_by_role("button", name="撤销修改", exact=True).click()
    expect(start).to_have_value("1.0")
    page.evaluate("() => window.releaseNarration()")
    expect(page.get_by_label("旁白修订状态")).to_contain_text("已保留当前音轨", timeout=60000)
    expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(attached.text)
    expect(start).to_have_value("1.0")


def test_undo_new_asset_preserves_each_assets_draft(attached):
    page, expect = attached.page, attached.expect
    page.get_by_role("button", name="编辑旁白文字", exact=True).click()
    box = page.get_by_role("textbox", name="旁白待合成稿")
    box.fill("旧音轨自己的待合成草稿")
    page.get_by_role("button", name="本机重新合成", exact=True).click()
    expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(
        "旧音轨自己的待合成草稿", timeout=60000
    )
    expect(box).to_have_count(0)
    page.get_by_role("button", name="编辑旁白文字", exact=True).click()
    box.fill("新音轨自己的待合成草稿")
    page.get_by_role("button", name="撤销修改", exact=True).click()
    expect(page.get_by_label("正在使用的旁白文字")).to_contain_text(attached.text)
    expect(box).to_have_count(0)
    page.get_by_role("button", name="编辑旁白文字", exact=True).click()
    expect(box).to_have_value("旧音轨自己的待合成草稿")
