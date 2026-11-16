"""G15: 200-clip timeline, last clip still selectable and trimmable."""

from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401
from test_studio_audio_graph_browser import ROOT, generate

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui import creation_jobs, server

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

FPS = 30
CLIP_FRAMES = 3
CLIP_US = (CLIP_FRAMES * 1_000_000 + FPS - 1) // FPS
CLIP_COUNT = 200


def _segments(asset):
    max_start = asset.duration_us - CLIP_US
    step = max_start // (CLIP_COUNT - 1)
    rows = []
    position = 0
    for index in range(CLIP_COUNT):
        start = index * step
        rows.append(
            {
                "runId": "run",
                "eventId": f"e{index}",
                "mediaId": asset.media_id,
                "sourceSha256": asset.sha256,
                "sourcePath": str(asset.source_path),
                "startUs": start,
                "endUs": start + CLIP_US,
                "sourceDurationUs": asset.duration_us,
                "outputStartFrame": position,
                "outputFrames": CLIP_FRAMES,
                "evidenceIds": [],
                "scriptDraft": f"镜头{index}",
                "uncertainty": None,
                "score": 1,
            }
        )
        position += CLIP_FRAMES
    return rows


def long_plan(jobs, monkeypatch):
    source, _music = generate(jobs.repository)
    asset = asyncio.run(
        FfmpegMediaProcessor(ROOT).probe(source, CancellationContext("studio-test", 30))
    )
    segments = _segments(asset)
    events = tuple(
        SemanticEvent(
            row["eventId"],
            asset.media_id,
            "run",
            SourceRange(row["startUs"], row["endUs"], asset.duration_us),
            (row["scriptDraft"],),
            (),
            (),
            "visual",
            None,
        )
        for row in segments
    )
    timeline = SimpleNamespace(
        run=SimpleNamespace(run_id="run", asset=asset),
        events=events,
        transcripts=(),
    )

    async def load_run(run_id):
        return timeline.run

    async def completed(run_id):
        return timeline

    async def load_timeline(*args, **kwargs):
        return timeline

    async def close():
        pass

    async def open_store(*args, **kwargs):
        return SimpleNamespace(
            load_run=load_run,
            load_completed_timeline=completed,
            load_timeline=load_timeline,
            close=close,
        )

    async def planner(project, runs, brief_path, output, *args, **kwargs):
        write_creation(
            output,
            {
                "plans.json": {
                    "schemaVersion": "creation-plan-v1",
                    "fps": FPS,
                    "brief": json.loads(brief_path.read_text()),
                    "plans": [
                        {
                            "id": "chronological",
                            "structure": "按时间",
                            "mode": "feature_showcase",
                            "ready": True,
                            "gaps": [],
                            "scriptStatus": "draft",
                            "segments": segments,
                        }
                    ],
                }
            },
            (),
        )

    monkeypatch.setattr(SqliteTimelineStore, "open", open_store)
    monkeypatch.setattr(creation_jobs, "execute_plan_creation", planner)
    req = request()
    req["brief"]["targetDuration"] = 20
    root = jobs.submit("plan", req)["jobId"]
    state = finish(jobs, root)
    assert state["status"] == "completed", state.get("error")
    return root, asset


@pytest.fixture
def studio_long(service, monkeypatch):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    root, asset = long_plan(service, monkeypatch)
    edit = service.edit(root, "chronological")
    assert len(edit["clips"]) == CLIP_COUNT

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "sourceName": "tone.mp4",
                    "status": "completed",
                    "completedEligible": True,
                    "durationUs": asset.duration_us,
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
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps({"artifacts/project": {"id": root, "kind": "plan"}})
            page.add_init_script(
                f"if(!localStorage.getItem('studio-v1'))localStorage.setItem('studio-v1',{prefs!r});"
                f"if(!localStorage.getItem('studio-last-job-v1'))localStorage.setItem('studio-last-job-v1',{last!r});"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            pw.expect(page.locator(".timeline .clip")).to_have_count(CLIP_COUNT, timeout=30_000)
            yield page
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def test_last_of_200_clips_can_scroll_select_and_trim(studio_long):
    page = studio_long
    area = page.locator(".track-area")
    first = page.locator(".timeline .clip").first
    last = page.locator(".timeline .clip").last
    first.scroll_into_view_if_needed()
    first.click()
    expect(first).to_have_attribute("aria-current", "true")
    page.get_by_role("textbox", name="镜头字幕").fill("首镜")
    page.locator(".insp-tabs").get_by_role("tab", name="导出", exact=True).click()
    expect(
        page.locator(".insp-tabs").get_by_role("tab", name="导出", exact=True)
    ).to_have_attribute("aria-selected", "true")
    page.locator("label.form-row").filter(has=page.locator("option[value='sidecar']")).locator(
        "select"
    ).select_option("sidecar")
    cue = page.locator(".caption-block").first
    expect(cue).to_have_text("首镜")
    cue_left = cue.evaluate("el => el.style.left")

    page.get_by_role("button", name="8倍", exact=True).click()
    expect(page.get_by_role("button", name="8倍", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    page.wait_for_function("el => el.scrollWidth > el.clientWidth * 2", arg=area.element_handle())
    last.scroll_into_view_if_needed()
    page.evaluate("el => { el.scrollLeft = el.scrollWidth; }", area.element_handle())
    expect(last).to_be_visible()
    last.click()
    expect(last).to_have_attribute("aria-current", "true")
    expect(first).not_to_have_attribute("aria-current", "true")

    handle = page.get_by_role("slider", name="拖动裁剪出点")
    handle.scroll_into_view_if_needed()
    expect(handle).to_be_visible()
    before = handle.get_attribute("aria-valuenow")
    box = handle.bounding_box()
    assert box and box["width"] > 2
    mid_y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + box["width"] / 2, mid_y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 - 40, mid_y, steps=8)
    page.mouse.up()
    expect(handle).not_to_have_attribute("aria-valuenow", before, timeout=5000)
    expect(page.locator(".timeline .clip")).to_have_count(CLIP_COUNT)
    expect(last).to_have_attribute("aria-current", "true")

    page.get_by_role("button", name="适应窗口", exact=True).click()
    first.scroll_into_view_if_needed()
    expect(cue).to_have_text("首镜")
    assert cue.evaluate("el => el.style.left") == cue_left
