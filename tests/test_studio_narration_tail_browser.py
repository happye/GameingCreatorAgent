"""A03: narration tail uses downward fit, not round-then-save-reject."""

from __future__ import annotations

import json
import threading
import wave

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401
from test_narration_jobs import engine, sapi  # noqa: F401
from test_studio_audio_graph_browser import saved_plan

from gamingcreator.application.browser_source_clock import runtime_clock_document
from gamingcreator.ui import server

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

SAMPLES = 16100
RATE = 16000
FPS = 30
OUTPUT_FRAMES = 90
MAX_START = 59  # ceil(16100 * 30 / 16000) = 31; 90 - 31 = 59


@pytest.fixture
def studio_tail(service, engine, monkeypatch):  # noqa: F811
    async def invoke(mode, request_path, context):
        context.check_cancelled()
        if mode == "list":
            return await engine.invoke(mode, request_path, context)
        request_body = json.loads(request_path.read_text(encoding="utf-8"))
        with wave.open(request_body["wavPath"], "wb") as wav:
            wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x00\x10" * SAMPLES)
        return b"{}"

    monkeypatch.setattr(sapi, "_invoke", invoke)
    pw = pytest.importorskip("playwright.sync_api")
    root, track, asset = saved_plan(service, monkeypatch)
    narration = None
    # done() after the exact wav hook is in place
    from test_narration_jobs import choice, done

    narration = done(service, text="tail-fit")  # exact 16100@16000 wav is hooked above
    asset_info = narration["narrationAsset"]
    assert asset_info["sampleCount"] == SAMPLES, asset_info
    assert asset_info["sampleRate"] == RATE, asset_info
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
    # Same 90-frame output as studio_audio (crossfade shortens the two clips to 3s).
    request_body = dict(
        requestId="e" * 32,
        parentJobId=root,
        planId="hook-first",
        expectedParentReceiptSha256=edit["expectedParentReceiptSha256"],
        clips=rows,
        audioMix=dict(
            sourceGainDb=-60,
            bgm=dict(trackId=track.track_id, trackReceiptSha256=track.receipt_sha256, gainDb=0),
            ducking="source-v1",
        ),
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
            browser = runtime.chromium.launch(
                headless=True, args=["--autoplay-policy=no-user-gesture-required"]
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps({"artifacts/project": {"id": revision, "kind": "revision"}})
            page.add_init_script(
                f"if(!localStorage.getItem('studio-v1'))localStorage.setItem('studio-v1',{prefs!r});"
                f"if(!localStorage.getItem('studio-last-job-v1'))localStorage.setItem('studio-last-job-v1',{last!r});"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            pw.expect(page.locator(".timeline .clip")).to_have_count(2)
            pw.expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
                "修改镜头、声音或叠加后可保存新版本"
            )
            yield page
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def test_narration_max_start_is_59_for_16100_samples(studio_tail, tmp_path):
    page = studio_tail
    start = page.get_by_role("slider", name="旁白起点")
    expect(start).to_have_attribute("aria-valuenow", "15")
    clock = page.evaluate(
        """() => {
            const scroll = document.querySelector(".track-scroll");
            return {
                totalUs: Number(scroll?.dataset.totalUs),
                fps: Number(scroll?.dataset.fps),
            };
        }"""
    )
    assert clock["totalUs"] == OUTPUT_FRAMES * 1_000_000 / FPS, clock
    assert clock["fps"] == FPS, clock

    start.focus()
    for _ in range(12):
        page.keyboard.press("Shift+ArrowRight")
    expect(start).to_have_attribute("aria-valuenow", str(MAX_START))
    page.keyboard.press("ArrowRight")
    expect(start).to_have_attribute("aria-valuenow", str(MAX_START))
    expect(page.get_by_role("status", name="版本保存状态")).not_to_contain_text("不会自动截断")
    expect(page.locator(".track-note")).to_have_count(0)

    # Keyboard already left the start at 59, so rewind to 15 before the drag case.
    while start.get_attribute("aria-valuenow") != "15":
        button = page.get_by_role("button", name="撤销一步")
        assert button.is_enabled(), "should be able to undo keyboard moves back to 15"
        button.click()
    expect(start).to_have_attribute("aria-valuenow", "15")

    # Pointer drag past the tail still clamps to 59, and is one undo step.
    start.scroll_into_view_if_needed()
    box = start.bounding_box()
    assert box and box["width"] > 4
    mid_y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + 2, mid_y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] + 400, mid_y, steps=20)
    page.mouse.up()
    expect(start).to_have_attribute("aria-valuenow", str(MAX_START))

    page.get_by_role("button", name="撤销一步").click()
    expect(start).to_have_attribute("aria-valuenow", "15")
    page.get_by_role("button", name="重做").click()
    expect(start).to_have_attribute("aria-valuenow", str(MAX_START))

    # Sound-panel seconds field must not accept 60 (2.0s) either.
    page.get_by_role("tab", name="声音", exact=True).click()
    field = page.get_by_label("起点（成片秒）")
    field.fill("2")
    field.blur()
    expect(start).to_have_attribute("aria-valuenow", str(MAX_START))

    with page.expect_request(
        lambda r: r.method == "POST" and r.url.endswith("/api/creation/revisions")
    ) as submitted:
        page.get_by_role("button", name="保存版本", exact=True).click()
    body = json.loads(submitted.value.post_data)
    assert body["narration"]["startFrame"] == MAX_START
    expect(page.get_by_role("status", name="版本保存状态")).to_contain_text(
        "修改镜头、声音或叠加后可保存新版本", timeout=30000
    )
    expect(start).to_have_attribute("aria-valuenow", str(MAX_START))
