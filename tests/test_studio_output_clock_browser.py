"""G16: 0.5x/1x/2x plus crossfade UI follows the saved output clock after reload."""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401
from test_creation_planner import brief, clips
from test_narration_jobs import choice, done, engine  # noqa: F401
from test_studio_audio_graph_browser import ROOT, generate

from gamingcreator.application.browser_source_clock import runtime_clock_document
from gamingcreator.application.creative_planner import plan_creation
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import output_start_frames
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.music_library import MusicLibrary
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui import creation_jobs, server

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

FPS = 30
SPEEDS = ((1, 2), (1, 1), (2, 1))
FADE_FRAMES = 15  # 交叉淡化 0.5 秒, offered in the inspector
NARRATION_START = 15
CAPTIONS = ("半速首镜", "原速二镜", "倍速三镜")


def clip_frames(start_us, end_us, numerator, denominator, fps=FPS):
    return (end_us - start_us) * fps * denominator // (1_000_000 * numerator)


def out_us(frame, fps=FPS):
    return frame * 1_000_000 / fps


def timecode(us):
    seconds = max(0, int(us // 1_000_000))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def px(value):
    return float(str(value).replace("px", "") or 0)


def mixed_plan(jobs, monkeypatch):
    source, music = generate(jobs.repository)
    asset = asyncio.run(
        FfmpegMediaProcessor(ROOT).probe(source, CancellationContext("studio-test", 30))
    )
    material = tuple(
        replace(
            c,
            asset=asset,
            event=replace(
                c.event,
                media_id=asset.media_id,
                source_range=SourceRange(
                    c.event.source_range.start_us, c.event.source_range.end_us, asset.duration_us
                ),
            ),
        )
        for c in clips()
    )
    timeline = SimpleNamespace(
        run=SimpleNamespace(run_id="run", asset=asset),
        events=tuple(c.event for c in material),
        transcripts=(),
    )

    async def load_run(run_id):
        return timeline.run

    async def completed(run_id):
        return timeline

    async def close():
        pass

    async def open_store(*args, **kwargs):
        return SimpleNamespace(load_run=load_run, load_completed_timeline=completed, close=close)

    report = plan_creation(brief(), material, 30)

    async def planner(project, runs, brief_path, output, *args, **kwargs):
        report["brief"] = json.loads(brief_path.read_text())
        write_creation(output, {"plans.json": report}, ())

    monkeypatch.setattr(SqliteTimelineStore, "open", open_store)
    monkeypatch.setattr(creation_jobs, "execute_plan_creation", planner)
    req = request()
    req["brief"]["targetDuration"] = 20
    root = jobs.submit("plan", req)["jobId"]
    state = finish(jobs, root)
    assert state["status"] == "completed", state.get("error")
    track = asyncio.run(
        MusicLibrary(jobs.repository).register(
            music, "tone", "generated", "unknown", None, CancellationContext("studio-test", 30)
        )
    )
    return root, track, asset


def expected_clock(rows):
    lengths = [
        clip_frames(
            row["startUs"], row["endUs"], row["speed"]["numerator"], row["speed"]["denominator"]
        )
        for row in rows
    ]
    transitions = [int(row["transitionIn"]["frames"]) for row in rows]
    starts = output_start_frames(tuple(lengths), tuple(transitions))
    start_us = [out_us(frame) for frame in starts]
    dur_us = [out_us(length) for length in lengths]
    return {
        "starts": list(starts),
        "lengths": lengths,
        "startUs": start_us,
        "durUs": dur_us,
        "totalUs": start_us[-1] + dur_us[-1],
        "speeds": [row["speed"]["numerator"] / row["speed"]["denominator"] for row in rows],
        "narrationUs": out_us(NARRATION_START),
    }


def read_layout(page):
    return page.evaluate(
        """() => {
            const clips = [...document.querySelectorAll('.track-row[data-track="picture"] .clip')];
            const captions = [...document.querySelectorAll('.caption-block')];
            const voice = document.querySelector('.track-row[data-track="voice"] .bar');
            const heads = [...document.querySelectorAll('.playhead')];
            const tc = document.querySelector('.transport .tc')?.textContent || '';
            const start = document.querySelector('[role="slider"][aria-label="旁白起点"]');
            return {
                clips: clips.map((el) => ({
                    left: el.style.left,
                    width: el.style.width,
                    title: el.title,
                    speed: el.querySelector('.clip-speed')?.textContent || '',
                })),
                captions: captions.map((el) => ({
                    left: el.style.left,
                    text: (el.textContent || '').trim(),
                    title: el.title,
                })),
                voice: voice ? {left: voice.style.left, width: voice.style.width} : null,
                playheads: heads.map((el) => el.style.left),
                tc,
                narrationFrame: start ? start.getAttribute('aria-valuenow') : null,
            };
        }"""
    )


def assert_clock_layout(layout, clock, *, captions=None, playhead_us=None):
    assert len(layout["clips"]) == 3, layout["clips"]
    first = px(layout["clips"][0]["left"])
    assert abs(first) < 0.51, layout["clips"][0]
    scale = px(layout["clips"][1]["left"]) / clock["startUs"][1]
    assert scale > 0
    for index, clip in enumerate(layout["clips"]):
        assert abs(px(clip["left"]) - clock["startUs"][index] * scale) < 0.51, (index, clip, clock)
        expected_width = max(1, clock["durUs"][index] * scale - 1)
        assert abs(px(clip["width"]) - expected_width) < 0.51, (index, clip, expected_width)
        assert timecode(clock["startUs"][index]) in clip["title"], clip["title"]
        speed = clock["speeds"][index]
        if speed != 1:
            assert clip["speed"] == f"{speed:g}×", clip
            assert f"{speed:g}×" in clip["title"], clip["title"]
        else:
            assert clip["speed"] == "", clip
    assert layout["narrationFrame"] == str(NARRATION_START), layout["narrationFrame"]
    assert layout["voice"], layout
    assert abs(px(layout["voice"]["left"]) - clock["narrationUs"] * scale) < 0.51, layout["voice"]
    if captions:
        assert len(layout["captions"]) == len(captions), layout["captions"]
        for index, caption in enumerate(layout["captions"]):
            assert captions[index] in caption["text"], caption
            # User-written cues start on the clip's output-clock origin.
            assert abs(px(caption["left"]) - clock["startUs"][index] * scale) < 0.51, (
                index,
                caption,
                clock,
            )
            assert timecode(clock["startUs"][index]) in caption["title"], caption["title"]
    if playhead_us is not None:
        assert layout["playheads"] and all(
            item == layout["playheads"][0] for item in layout["playheads"]
        )
        assert abs(px(layout["playheads"][0]) - playhead_us * scale) < 0.51, layout["playheads"]
        shown, total = [part.strip() for part in layout["tc"].split("/")]
        assert shown == timecode(playhead_us), layout["tc"]
        assert total == timecode(clock["totalUs"]), layout["tc"]
    return scale


def enable_sidecar_captions(page):
    export_tab = page.locator(".insp-tabs").get_by_role("tab", name="导出", exact=True)
    export_tab.click()
    expect(export_tab).to_have_attribute("aria-selected", "true")
    page.locator("label.form-row").filter(has=page.locator("option[value='sidecar']")).locator(
        "select"
    ).select_option("sidecar")


def click_clip(page, index, clock):
    """Select a clip in its exclusive body so a later crossfade layer does not steal the click."""
    clip = page.locator(".track-row[data-track='picture'] .clip").nth(index)
    box = clip.bounding_box()
    assert box and box["width"] > 4, box
    lengths = clock["lengths"]
    incoming = 0 if index == 0 else FADE_FRAMES / lengths[index]
    outgoing = 0 if index == len(lengths) - 1 else FADE_FRAMES / lengths[index]
    frac = (incoming + (1 - outgoing)) / 2
    page.mouse.click(box["x"] + box["width"] * frac, box["y"] + box["height"] / 2)
    return clip


def fill_captions(page, texts, clock):
    field = page.get_by_label("镜头字幕", exact=True)
    for index, text in enumerate(texts):
        for _ in range(20):
            click_clip(page, index, clock)
            try:
                field.wait_for(state="visible", timeout=500)
                break
            except Exception:  # noqa: BLE001 - inspector may still be on another tab
                continue
        field.fill(text)
        expect(page.locator(".caption-block").nth(index)).to_contain_text(text, timeout=10_000)


@pytest.fixture
def studio_mixed(service, engine, monkeypatch):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    root, track, asset = mixed_plan(service, monkeypatch)
    narration = done(service, text="旁白测试本地声音" * 3)
    edit = service.edit(root, "hook-first")
    assert len(edit["clips"]) >= 3, edit["clips"]
    rows = []
    for index, (clip, (numerator, denominator)) in enumerate(
        zip(edit["clips"][:3], SPEEDS, strict=True)
    ):
        rows.append(
            {
                **{k: clip[k] for k in ("clipId", "startUs", "endUs")},
                "speed": {"numerator": numerator, "denominator": denominator},
                "transitionIn": {"type": "cut", "frames": 0}
                if index == 0
                else {"type": "crossfade", "frames": FADE_FRAMES},
            }
        )
    clock = expected_clock(rows)
    request_body = dict(
        requestId="c" * 32,
        parentJobId=root,
        planId="hook-first",
        expectedParentReceiptSha256=edit["expectedParentReceiptSha256"],
        clips=rows,
        audioMix=dict(
            sourceGainDb=-60,
            bgm=dict(trackId=track.track_id, trackReceiptSha256=track.receipt_sha256, gainDb=0),
            ducking="source-v1",
        ),
        narration=choice(narration, start=NARRATION_START, gain=-60),
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
            pw.expect(page.locator(".track-row[data-track='picture'] .clip")).to_have_count(3)
            pw.expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
                "修改镜头、声音或叠加后可保存新版本"
            )
            yield page, clock
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def test_mixed_speed_crossfade_display_matches_saved_output_clock(studio_mixed):
    page, clock = studio_mixed
    expect(page.locator(".clip-speed")).to_have_text(["0.5×", "2×"])
    layout = read_layout(page)
    assert_clock_layout(layout, clock)

    enable_sidecar_captions(page)
    fill_captions(page, CAPTIONS, clock)
    click_clip(page, 2, clock)
    expect(page.locator(".track-row[data-track='picture'] .clip").nth(2)).to_have_attribute(
        "aria-current", "true"
    )
    page.wait_for_function(
        """expected => {
            const tc = document.querySelector('.transport .tc')?.textContent || '';
            return tc.startsWith(expected);
        }""",
        arg=timecode(clock["startUs"][2]),
    )
    layout = read_layout(page)
    assert_clock_layout(layout, clock, captions=CAPTIONS, playhead_us=clock["startUs"][2])

    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/api/creation/revisions")
    ) as submitted:
        page.get_by_role("button", name="保存版本", exact=True).click()
    body = json.loads(submitted.value.post_data)
    assert [(row["speed"], row["transitionIn"]["frames"]) for row in body["clips"]] == [
        ({"numerator": 1, "denominator": 2}, 0),
        ({"numerator": 1, "denominator": 1}, FADE_FRAMES),
        ({"numerator": 2, "denominator": 1}, FADE_FRAMES),
    ]
    assert body["narration"]["startFrame"] == NARRATION_START
    expect(page.get_by_role("status", name="版本保存状态")).to_contain_text(
        "修改镜头、声音或叠加后可保存新版本", timeout=30_000
    )

    page.reload()
    expect(page.locator(".track-row[data-track='picture'] .clip")).to_have_count(3)
    expect(page.locator(".clip-speed")).to_have_text(["0.5×", "2×"])
    expect(page.get_by_role("slider", name="旁白起点")).to_have_attribute(
        "aria-valuenow", str(NARRATION_START)
    )
    enable_sidecar_captions(page)
    expect(page.locator(".caption-block")).to_have_count(3, timeout=10_000)
    for index, text in enumerate(CAPTIONS):
        expect(page.locator(".caption-block").nth(index)).to_contain_text(text)
    click_clip(page, 1, clock)
    page.wait_for_function(
        """expected => {
            const tc = document.querySelector('.transport .tc')?.textContent || '';
            return tc.startsWith(expected);
        }""",
        arg=timecode(clock["startUs"][1]),
    )
    layout = read_layout(page)
    assert_clock_layout(layout, clock, captions=CAPTIONS, playhead_us=clock["startUs"][1])
