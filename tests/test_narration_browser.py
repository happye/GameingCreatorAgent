"""Narration panel UI contracts against mocked local APIs; no SAPI, media or paid calls."""

import json
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
ROOT, NEW, OLD, RENDER = "a" * 32, "d" * 32, "f" * 32, "9" * 32
VOICES = [
    {"voiceId": "v-zira", "description": "Microsoft Zira", "language": "409"},
    {"voiceId": "v-huihui", "description": "Microsoft Huihui", "language": "804"},
]


def narration_asset(job_id, seconds=1):
    prefix = f"/api/creation/jobs/{job_id}/narration-files/"
    return {
        "assetJobId": job_id,
        "receiptSha256": "e" * 64,
        "voice": VOICES[0],
        "sampleRate": 22050,
        "sampleCount": 22050 * seconds,
        "durationSeconds": float(seconds),
        "text": "你好，旁白",
        "audioUrl": prefix + "narration.wav",
        "textUrl": prefix + "narration.txt",
        "licenseStatus": "unknown",
    }


def narration_job(status, **extra):
    base = {"jobId": NEW, "kind": "narration", "status": status, "projectId": "one"}
    return {**base, **extra}


def make_editor(**extra):
    return {
        "parentJobId": ROOT,
        "planId": "p",
        "expectedParentReceiptSha256": "c" * 64,
        "fps": 30,
        "clips": [{"clipId": "c", "startUs": 0, "endUs": 3000000, "outputFrames": 90}],
        "ancestry": [],
        **extra,
    }


@contextmanager
def workspace(
    editor=None,
    voices=VOICES,
    job_states=None,
    revision_error="已捕获保存请求",
    extra_jobs=(),
    extra_routes=None,
    viewport=None,
):
    pw = pytest.importorskip("playwright.sync_api")
    editor = editor or make_editor()
    states = list(job_states or [narration_job("completed", narrationAsset=narration_asset(NEW))])
    posts = []
    jobs = [{"jobId": ROOT, "kind": "revision", "status": "completed", "createdAt": "2026-10-31"}]
    jobs.extend(extra_jobs)
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport or {"width": 1280, "height": 900})

        def route(r):
            path, method = urlsplit(r.request.url).path, r.request.method
            if path == "/creation":
                r.fulfill(
                    body=(STATIC / "creation.html").read_text("utf-8-sig"), content_type="text/html"
                )
            elif path.startswith("/assets/"):
                r.fulfill(
                    body=(STATIC / path.rsplit("/", 1)[1]).read_text("utf-8-sig"),
                    content_type="text/css" if path.endswith("css") else "text/javascript",
                )
            elif path == "/api/creation/platform-profiles":
                r.fulfill(json={"profiles": []})
            elif path == "/api/creation/music":
                r.fulfill(json={"tracks": [], "issues": []})
            elif path == "/api/creation/voices":
                if voices is None:
                    r.fulfill(status=500, json={"error": "SAPI 不可用"})
                else:
                    r.fulfill(json={"voices": voices, "licenseStatus": "unknown"})
            elif path == "/api/projects":
                r.fulfill(json={"projects": [{"path": "one"}]})
            elif path.startswith("/api/runs"):
                r.fulfill(json={"runs": []})
            elif method == "POST":
                body = json.loads(r.request.post_data)
                posts.append((path, body))
                if path == "/api/creation/narrations":
                    r.fulfill(
                        status=202, json={"jobId": NEW, "kind": "narration", "status": "pending"}
                    )
                elif path == "/api/creation/narration-cancel":
                    r.fulfill(json={**body, "kind": "narration", "cancelRequested": True})
                else:
                    r.fulfill(status=400, json={"error": revision_error})
            elif path == "/api/creation/jobs":
                r.fulfill(json={"jobs": jobs})
            elif path.endswith("/edit"):
                r.fulfill(json=editor)
            elif "/narration-files/" in path or path.endswith("/video"):
                r.fulfill(status=404, body="")
            elif path.endswith("/publication"):
                r.fulfill(
                    json={
                        "renderJobId": RENDER,
                        "expectedRenderReceiptSha256": "b" * 64,
                        "frames": 90,
                        "fps": 30,
                        "videoUrl": f"/api/creation/jobs/{RENDER}/video",
                        "coverFrame": 0,
                        "title": "t",
                        "description": "d",
                        "tags": [],
                    }
                )
            elif path == f"/api/creation/jobs/{NEW}":
                current = states.pop(0) if len(states) > 1 else states[0]
                r.fulfill(json=current)
            elif path == f"/api/creation/jobs/{ROOT}":
                r.fulfill(json={**jobs[0], "projectId": "one", "editor": editor})
            elif extra_routes and path in extra_routes:
                r.fulfill(json=extra_routes[path])
            else:
                r.fulfill(status=404, json={"error": f"未模拟 {path}"})

        page.route("**/*", route)
        try:
            page.goto("http://workspace.test/creation")
            yield pw, page, posts
        finally:
            browser.close()


def open_editor(pw, page):
    page.locator("#history button").filter(has_text="剪辑版本").click()
    pw.expect(page.locator("#narration-controls")).to_be_visible()


def revision_posts(posts):
    return [body for path, body in posts if path == "/api/creation/revisions"]


def test_generate_preview_attach_with_nonzero_start():
    states = [
        narration_job("running"),
        narration_job("completed", narrationAsset=narration_asset(NEW)),
    ]
    with workspace(job_states=states, viewport={"width": 390, "height": 844}) as (pw, page, posts):
        open_editor(pw, page)
        voice = page.locator("#narration-voice")
        pw.expect(voice.locator("option")).to_have_text(
            ["Microsoft Zira · 英语（美国）", "Microsoft Huihui · 中文（简体）"]
        )
        pw.expect(voice).to_have_value("v-huihui")
        pw.expect(page.locator("#narration-notice")).to_contain_text("商用许可未核实")
        pw.expect(page.locator("#narration-generate")).to_be_disabled()
        pw.expect(page.locator("#narration-attach")).to_be_disabled()
        voice.select_option("v-zira")
        page.locator("#narration-text").fill("你好，旁白")
        pw.expect(page.locator("#narration-count")).to_have_text("5 / 10000 字")
        page.locator("#narration-generate").click()
        pw.expect(page.locator("#narration-cancel")).to_be_visible()
        pw.expect(page.locator("#narration-audio")).to_have_attribute(
            "src", f"/api/creation/jobs/{NEW}/narration-files/narration.wav"
        )
        post = posts[0]
        assert post[0] == "/api/creation/narrations"
        assert set(post[1]) == {"requestId", "projectId", "text", "voiceId"}
        assert len(post[1]["requestId"]) == 32
        assert post[1]["projectId"] == "one"
        assert post[1]["text"] == "你好，旁白"
        assert post[1]["voiceId"] == "v-zira"
        pw.expect(page.locator("#narration-preview")).to_contain_text("时长 1.000 秒")
        pw.expect(page.locator("#narration-text-link")).to_have_attribute(
            "href", f"/api/creation/jobs/{NEW}/narration-files/narration.txt"
        )
        pw.expect(page.locator("#narration-cancel")).to_be_hidden()
        assert len(posts) == 1 and not revision_posts(posts)
        page.locator("#narration-start").fill("2")
        pw.expect(page.locator("#narration-start-frame")).to_contain_text("第 60 帧")
        pw.expect(page.locator("#narration-fit")).to_have_text("")
        page.locator("#narration-gain").fill("-6")
        page.locator("#narration-ducking").check()
        page.locator("#narration-attach").click()
        pw.expect(page.locator("#narration-current")).to_contain_text("第 60 帧")
        pw.expect(page.locator("#render")).to_be_disabled()
        page.locator("#save-revision").click()
        pw.expect(page.locator("#notice")).to_contain_text("已捕获")
        assert revision_posts(posts)[-1]["narration"] == {
            "assetJobId": NEW,
            "receiptSha256": "e" * 64,
            "startFrame": 60,
            "gainDb": -6,
            "ducking": "narration-v1",
        }
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_cancel_generation_and_overlong_warning():
    states = [
        narration_job("running"),
        narration_job("interrupted", error={"code": "cancelled", "message": "已取消"}),
    ]
    with workspace(job_states=states) as (pw, page, posts):
        open_editor(pw, page)
        page.locator("#narration-text").fill("很长的旁白")
        page.locator("#narration-generate").click()
        pw.expect(page.locator("#narration-status")).to_contain_text("正在合成")
        page.locator("#narration-cancel").click()
        pw.expect(page.locator("#narration-status")).to_contain_text("旁白未完成：已取消")
        assert ("/api/creation/narration-cancel", {"jobId": NEW}) in posts
        pw.expect(page.locator("#narration-audio")).to_have_count(0)
        pw.expect(page.locator("#narration-generate")).to_be_enabled()
    done = narration_job("completed", narrationAsset=narration_asset(NEW, seconds=2))
    with workspace(job_states=[done]) as (pw, page, posts):
        open_editor(pw, page)
        page.locator("#narration-text").fill("两秒旁白")
        page.locator("#narration-generate").click()
        pw.expect(page.locator("#narration-audio")).to_have_count(1)
        pw.expect(page.locator("#narration-fit")).to_have_text("")
        page.locator("#narration-start").fill("1.5")
        pw.expect(page.locator("#narration-fit")).to_contain_text("起点后成片只剩 1.500 秒")
        page.locator("#narration-start").fill("1")
        pw.expect(page.locator("#narration-fit")).to_have_text("")
        page.locator("#narration-start").fill("-1")
        pw.expect(page.locator("#narration-attach")).to_be_disabled()


def inherited_editor():
    return make_editor(
        narration={
            "assetJobId": OLD,
            "receiptSha256": "e" * 64,
            "startFrame": 30,
            "gainDb": -3,
            "ducking": "narration-v1",
        },
        narrationAsset=narration_asset(OLD),
    )


def test_inherited_narration_is_shown_modified_and_removed():
    with workspace(editor=inherited_editor()) as (pw, page, posts):
        open_editor(pw, page)
        current = page.locator("#narration-current")
        pw.expect(current).to_contain_text("当前已挂接旁白")
        pw.expect(current).to_contain_text("第 30 帧")
        pw.expect(current).to_contain_text("-3 dB")
        pw.expect(page.locator("#narration-current-audio")).to_have_attribute(
            "src", f"/api/creation/jobs/{OLD}/narration-files/narration.wav"
        )
        pw.expect(page.locator("#narration-start")).to_have_value("1")
        pw.expect(page.locator("#narration-gain")).to_have_value("-3")
        pw.expect(page.locator("#narration-ducking")).to_be_checked()
        pw.expect(page.locator("#narration-remove")).to_be_enabled()
        page.locator("#save-revision").click()
        pw.expect(page.locator("#notice")).to_contain_text("已捕获")
        assert "narration" not in revision_posts(posts)[-1]
        page.locator("#narration-gain").fill("-9")
        page.locator("#narration-start").fill("0.5")
        pw.expect(page.locator("#render")).to_be_disabled()
        page.locator("#save-revision").click()
        pw.expect(page.locator("#notice")).to_contain_text("已捕获")
        assert revision_posts(posts)[-1]["narration"] == {
            "assetJobId": OLD,
            "receiptSha256": "e" * 64,
            "startFrame": 15,
            "gainDb": -9,
            "ducking": "narration-v1",
        }
        page.locator("#narration-remove").click()
        pw.expect(page.locator("#narration-current")).to_contain_text("将被移除")
        page.locator("#save-revision").click()
        pw.expect(page.locator("#notice")).to_contain_text("已捕获")
        assert "narration" in revision_posts(posts)[-1]
        assert revision_posts(posts)[-1]["narration"] is None
        assert len(revision_posts(posts)) == 3


def test_server_error_is_shown_without_losing_the_editor():
    message = "旁白长 2.000 秒，起点后只剩 1.000 秒；请改短文字、调整起点或移除旁白。"
    with workspace(editor=inherited_editor(), revision_error=message) as (pw, page, posts):
        open_editor(pw, page)
        page.locator("#narration-start").fill("2")
        page.locator("#save-revision").click()
        pw.expect(page.locator("#notice")).to_contain_text(message)
        pw.expect(page.locator("[data-clip-id]")).to_have_count(1)
        pw.expect(page.locator("#narration-start")).to_have_value("2")
        pw.expect(page.locator("#narration-current")).to_contain_text("第 60 帧")
        pw.expect(page.locator("#save-revision")).to_be_enabled()
        assert revision_posts(posts)[-1]["narration"]["startFrame"] == 60


def test_voice_failure_keeps_other_editing_available():
    with workspace(voices=None) as (pw, page, posts):
        open_editor(pw, page)
        pw.expect(page.locator("#narration-notice")).to_have_text("本地声音不可用，可继续其他编辑")
        pw.expect(page.locator("#narration-voice")).to_be_disabled()
        page.locator("#narration-text").fill("没有声音")
        pw.expect(page.locator("#narration-generate")).to_be_disabled()
        pw.expect(page.locator("#bgm-track")).to_be_visible()
        page.locator("#save-revision").click()
        pw.expect(page.locator("#notice")).to_contain_text("已捕获")
        assert "narration" not in revision_posts(posts)[-1]
        assert all(path != "/api/creation/narrations" for path, _ in posts)


def test_render_with_narration_offers_text_download():
    render = {
        "jobId": RENDER,
        "kind": "render",
        "status": "completed",
        "projectId": "one",
        "createdAt": "2026-10-31",
        "artifact": {
            "mediaType": "video/mp4",
            "sizeBytes": 1024,
            "previewUrl": f"/api/creation/jobs/{RENDER}/video",
            "downloadUrl": f"/api/creation/jobs/{RENDER}/video?download=1",
            "narrationTextUrl": f"/api/creation/jobs/{RENDER}/narration-text",
        },
    }
    with workspace(extra_jobs=[render], extra_routes={f"/api/creation/jobs/{RENDER}": render}) as (
        pw,
        page,
        posts,
    ):
        page.locator("#history button").filter(has_text="视频").click()
        link = page.locator("#download-narration-text")
        pw.expect(link).to_contain_text("旁白文本")
        pw.expect(link).to_have_attribute("href", f"/api/creation/jobs/{RENDER}/narration-text")
        assert not posts
