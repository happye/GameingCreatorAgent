"""Real Studio HTTP revisions preserve manual captions without changing transcripts."""

# ruff: noqa: F811

import uuid

import pytest
from test_clip_replacement_jobs import replacements  # noqa: F401
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401

expect = pytest.importorskip("playwright.sync_api").expect

pytestmark = pytest.mark.browser


def select_shot(page):
    # Until the editor has loaded, the timeline shows the plan's read-only shots and a click
    # selects nothing (verify 7bedec9 failure). Click again until the shot inspector opens.
    field = page.get_by_label("镜头字幕", exact=True)
    for _ in range(20):
        page.locator(".timeline .clip").first.click(position={"x": 10, "y": 10})
        try:
            field.wait_for(state="visible", timeout=500)
            break
        except Exception:  # noqa: BLE001 - editor still loading; retry the click
            continue
    return field


def save_captions(page):
    with page.expect_response(
        lambda r: "/api/creation/revisions" in r.url and r.request.method == "POST"
    ) as response:
        page.get_by_role("button", name="保存版本", exact=True).click()
    accepted = response.value.json()
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
        "修改镜头、声音或叠加后可保存新版本", timeout=20000
    )
    return accepted["jobId"]


def test_caption_is_locked_while_save_request_is_pending(studio_audio):
    page = studio_audio
    field = select_shot(page)
    field.fill("本次保存的字幕")
    pending = []
    page.route("**/api/creation/revisions", lambda route: pending.append(route))
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(field).to_be_disabled()
    expect(page.get_by_role("button", name="恢复自动字幕", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="此镜头不显示字幕", exact=True)).to_be_disabled()
    assert len(pending) == 1
    assert pending[0].request.post_data_json["subtitleOverrides"][0]["text"] == "本次保存的字幕"
    pending[0].continue_()
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
        "修改镜头、声音或叠加后可保存新版本", timeout=20000
    )
    field = select_shot(page)
    expect(field).to_be_enabled()
    expect(field).to_have_value("本次保存的字幕")


def test_caption_write_hide_restore_and_undo(studio_audio, service):
    page = studio_audio
    field = select_shot(page)
    expect(page.get_by_role("status", name="镜头字幕状态")).to_contain_text("自动字幕")
    text = "手写开场\n保留换行"
    field.fill(text)
    expect(page.get_by_role("status", name="镜头字幕状态")).to_contain_text("手写字幕")
    job = save_captions(page)
    saved = page.request.get(
        page.url.removesuffix("/studio") + f"/api/creation/jobs/{job}/edit?planId=hook-first"
    ).json()["subtitleOverrides"]
    assert len(saved) == 1 and saved[0]["text"] == text
    base = page.url.removesuffix("/studio")
    rendered = page.request.post(
        base + "/api/creation/renders",
        data={
            "requestId": uuid.uuid4().hex,
            "revisionJobId": job,
            "width": 320,
            "height": 180,
            "subtitleMode": "sidecar",
        },
    ).json()["jobId"]
    result = page.evaluate(
        """async id => {
        for (let i = 0; i < 300; i++) {
            const job = await (await fetch('/api/creation/jobs/' + id)).json();
            if (['completed', 'failed'].includes(job.status)) return job;
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        throw new Error('render did not finish');
    }""",
        rendered,
    )
    assert result["status"] == "completed", result
    assert result["artifact"]["subtitleCueCount"] == 1
    assert text in page.request.get(base + result["artifact"]["subtitleUrl"]).text()
    assert (service.directory(rendered) / "result/video.mp4").stat().st_size > 1000
    page.reload()
    expect(select_shot(page)).to_have_value(text)
    page.get_by_role("button", name="此镜头不显示字幕", exact=True).click()
    hidden = save_captions(page)
    assert (
        page.request.get(
            page.url.removesuffix("/studio") + f"/api/creation/jobs/{hidden}/edit?planId=hook-first"
        ).json()["subtitleOverrides"][0]["text"]
        == ""
    )
    expect(select_shot(page)).to_have_value("")
    page.get_by_role("button", name="恢复自动字幕", exact=True).click()
    page.get_by_role("button", name="撤销修改", exact=True).click()
    expect(page.get_by_role("status", name="镜头字幕状态")).to_have_text("此镜头不显示字幕。")
    page.get_by_role("button", name="恢复自动字幕", exact=True).click()
    automatic = save_captions(page)
    assert (
        page.request.get(
            page.url.removesuffix("/studio")
            + f"/api/creation/jobs/{automatic}/edit?planId=hook-first"
        ).json()["subtitleOverrides"]
        == []
    )
    page.reload()
    select_shot(page)
    expect(page.get_by_role("status", name="镜头字幕状态")).to_contain_text("自动字幕")


def test_invalid_caption_blocks_save_and_export(studio_audio):
    page = studio_audio
    field = select_shot(page)
    for text in ("字" * 2001, "  \n ", "bad --> timing", "bad\x7ftext"):
        field.fill(text)
        expect(page.get_by_role("button", name="保存版本", exact=True)).to_be_disabled()
        expect(page.get_by_role("button", name="导出成片", exact=True)).to_be_disabled()
    field.fill("有效字幕")
    expect(page.get_by_role("button", name="保存版本", exact=True)).to_be_enabled()
    page.get_by_role("button", name="撤销修改", exact=True).click()
    expect(field).to_have_value("")


def test_replacement_clears_caption_and_requires_save(replacements, monkeypatch):
    import json
    import threading

    from playwright.sync_api import sync_playwright

    from gamingcreator.ui import server

    jobs, root, _ = replacements

    async def runs(project):
        return {
            "runs": [
                {"id": i, "status": "completed", "sourceName": i, "completedEligible": True}
                for i in ("run", "B")
            ]
        }

    monkeypatch.setattr(server, "project_runs_payload", runs)
    http = server.create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps({"artifacts/project": {"id": root, "kind": "plan"}})
            page.add_init_script(
                f"if(!localStorage.getItem('studio-v1'))localStorage.setItem('studio-v1',{prefs!r});"
                f"if(!localStorage.getItem('studio-last-job-v1'))localStorage.setItem('studio-last-job-v1',{last!r});"
            )
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            select_shot(page).fill("旧画面字幕")
            page.get_by_role("button", name="替换这段画面", exact=True).click()
            page.get_by_role("button", name="换成这段", exact=True).first.click()
            field = page.get_by_label("镜头字幕", exact=True)
            expect(field).to_have_value("")
            expect(field).to_be_disabled()
            expect(page.get_by_role("button", name="此镜头不显示字幕", exact=True)).to_be_disabled()
            expect(page.get_by_role("button", name="恢复自动字幕", exact=True)).to_be_disabled()
            expect(
                page.get_by_text("先保存替换版本，再编辑新镜头字幕。", exact=True)
            ).to_be_visible()
            job = save_captions(page)
            edit = page.request.get(
                page.url.removesuffix("/studio") + f"/api/creation/jobs/{job}"
            ).json()
            assert edit["editor"]["subtitleOverrides"] == [], edit
            expect(select_shot(page)).to_be_enabled()
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def test_deleted_caption_is_filtered_and_parent_switch_isolated(studio_audio):
    page = studio_audio
    page.get_by_role("tab", name="声音", exact=True).click()
    page.get_by_role("button", name="移除旁白", exact=True).click()
    page.get_by_role("tab", name="镜头", exact=True).click()
    select_shot(page).fill("只属于第一个镜头")
    page.get_by_role("button", name="删除这段", exact=True).click()
    job = save_captions(page)
    base = page.url.removesuffix("/studio")
    edit = page.request.get(base + f"/api/creation/jobs/{job}/edit?planId=hook-first").json()
    assert edit["subtitleOverrides"] == []
    select_shot(page).fill("未保存的版本字幕")
    page.on("dialog", lambda dialog: dialog.accept())
    plans = page.locator("button.plan")
    plans.last.click()
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
        "修改镜头、声音或叠加后可保存新版本"
    )
    expect(select_shot(page)).to_have_value("")
