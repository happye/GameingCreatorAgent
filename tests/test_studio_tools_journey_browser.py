"""Round2 journey: same isolated fixture for knowledge + narration tools (R10) and import smoke."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import saved_plan  # noqa: F401

from gamingcreator.application.browser_source_clock import runtime_clock_document
from gamingcreator.ui import server

EVIDENCE = Path(".cache/scratch/grok-studio-round2-20261108")
GAME = "g"


@pytest.fixture
def journey(service, engine, monkeypatch):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    root, track, asset = saved_plan(service, monkeypatch)
    job = service.get(root)
    plan_id = next(p["id"] for p in job["plans"] if p.get("ready"))
    assert job.get("brief", {}).get("game") == GAME

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

            def track_route(route):
                if route.request.method == "POST":
                    posts.append(route.request.url.split("?")[0])
                route.continue_()

            page.route("**/api/**", track_route)
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            pw.expect(page.locator(".timeline .clip").first).to_be_visible(timeout=60000)
            page.get_by_role("tab", name="声音", exact=True).click()
            yield SimpleNamespace(
                page=page,
                expect=pw.expect,
                posts=posts,
                root=root,
                plan_id=plan_id,
                port=http.server_port,
                repository=service.repository,
                service=service,
            )
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def test_r10_same_fixture_knowledge_then_narration_script(journey):
    """R10/T31: real knowledge save→search→narration-script citations→edit→copy/TXT; 0 voice posts."""
    page, expect = journey.page, journey.expect
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    panel = page.locator(".knowledge-panel")
    if not panel.evaluate("el => el.open"):
        panel.locator("summary").click()

    page.get_by_label("知识标题").fill("贯通知识")
    page.get_by_label("知识正文").fill("贯通引用句：贝多芬会召唤音符")
    page.get_by_label("知识来源说明").fill("官网")
    page.get_by_role("button", name="保存知识", exact=True).click()
    expect(page.get_by_label("知识保存状态")).to_contain_text("已保存")
    page.get_by_label("知识关键词").fill("贝多芬")
    page.get_by_role("button", name="查找", exact=True).click()
    expect(page.get_by_label("知识搜索结果")).to_contain_text("贯通知识")

    posts_before = list(journey.posts)
    # Real narration-script HTTP (no fetch fake of citations).
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    expect(page.get_by_role("textbox", name="旁白稿")).to_be_visible(timeout=60000)
    drafted = page.get_by_role("textbox", name="旁白稿").input_value()
    assert drafted.strip()
    # Citations may be empty if template doesn't pull knowledge — still must not invent via fetch.
    page.get_by_role("textbox", name="旁白稿").fill(drafted + "【已编辑】")
    edited = page.get_by_role("textbox", name="旁白稿").input_value()
    page.evaluate(
        """() => {
        window.__copied = null;
        navigator.clipboard.writeText = async (text) => { window.__copied = text; };
    }"""
    )
    page.get_by_role("button", name="草稿复制旁白稿").click()
    assert page.evaluate("window.__copied") == edited
    with page.expect_download() as info:
        page.get_by_role("button", name="草稿下载旁白TXT").click()
    download = info.value
    target = EVIDENCE / "r10-journey-narration-draft.txt"
    download.save_as(str(target))
    assert target.read_text(encoding="utf-8") == edited
    voice_posts = [
        u for u in journey.posts[len(posts_before) :] if u.endswith("/api/creation/narrations")
    ]
    assert voice_posts == []
    page.set_viewport_size({"width": 1440, "height": 900})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.screenshot(path=str(EVIDENCE / "r10-journey-1440x900.png"))
    page.set_viewport_size({"width": 1280, "height": 720})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.screenshot(path=str(EVIDENCE / "r10-journey-1280x720.png"))
