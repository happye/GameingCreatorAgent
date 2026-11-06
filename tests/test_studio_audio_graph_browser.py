"""Real Studio/media/receipts; fake planner, SAPI, timeline store and runs payload."""

import asyncio
import json
import os
import subprocess
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_audio_preview_graph_browser import amplitude
from test_creation_jobs import finish, request, service  # noqa: F401
from test_creation_planner import brief, clips
from test_narration_jobs import choice, done, engine  # noqa: F401

from gamingcreator.application.browser_source_clock import runtime_clock_document
from gamingcreator.application.creative_planner import plan_creation
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.music_library import MusicLibrary
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui import creation_jobs, server

ROOT = Path(__file__).resolve().parents[1]


def generate(repository):
    tools = repository / ".tools/ffmpeg/bin"
    tools.mkdir(parents=True)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        os.link(ROOT / ".tools/ffmpeg/bin" / name, tools / name)
    (repository / "footage").mkdir()
    source = repository / "footage/source.mp4"
    command = [str(tools / "ffmpeg.exe"), "-v", "error", "-nostdin", "-n"]
    subprocess.run(
        command
        + [
            "-f",
            "lavfi",
            "-i",
            "color=red:s=64x48:r=30:d=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=337:sample_rate=48000:duration=10",
            "-af",
            "volume=3.2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    music = repository / "music.wav"
    subprocess.run(
        command
        + [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=907:sample_rate=48000:duration=1",
            "-af",
            "volume=0.8",
            str(music),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    return source, music


def saved_plan(jobs, monkeypatch):
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
    req["brief"]["targetDuration"] = 6
    root = jobs.submit("plan", req)["jobId"]
    state = finish(jobs, root)
    assert state["status"] == "completed", state.get("error")
    track = asyncio.run(
        MusicLibrary(jobs.repository).register(
            music, "tone", "generated", "unknown", None, CancellationContext("studio-test", 30)
        )
    )
    return root, track, asset


@pytest.fixture
def studio_audio(service, engine, monkeypatch):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    root, track, asset = saved_plan(service, monkeypatch)
    narration = done(service, text="旁白测试本地声音" * 3)
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
    for name in ("audio-preview-graph.js", "audio-ducking-processor.js"):
        monkeypatch.setitem(
            server.ASSETS,
            f"/assets/studio/{name}",
            (f"studio/{name}", "text/javascript; charset=utf-8"),
        )

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
                f"localStorage.setItem('studio-v1',{prefs!r});localStorage.setItem('studio-last-job-v1',{last!r});"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            pw.expect(page.locator(".timeline .clip")).to_have_count(2)
            pw.expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
                "修改镜头或声音后可保存新版本"
            )
            yield page
            assert not errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


CAPTURE = """async (seconds) => {
 seconds = seconds || 4.2;
 const video=document.querySelector('[data-preview-slot]'), g=video.studioAudioGraph;
 const recorder=g.context.createScriptProcessor(1024,2,2), samples=[], observations=[];
 const done=new Promise(resolve=>{recorder.onaudioprocess=e=>{
   samples.push(...e.inputBuffer.getChannelData(0));
   const v=[...document.querySelectorAll('[data-preview-slot]')];
   observations.push({weights:[...g.weights],times:v.map(x=>x.currentTime),
       music:g.elements[2].currentTime,voice:g.elements[3].currentTime});
   if(samples.length>g.context.sampleRate*seconds)resolve();
 }});
 g.gate.connect(recorder);recorder.connect(g.context.destination);await done;
 g.gate.disconnect(recorder);recorder.disconnect();
 return {samples,rate:g.context.sampleRate,observations};
}"""


def test_real_studio_dissolve_audio_clock_ducking_and_pause(studio_audio):
    page = studio_audio
    page.get_by_role("button", name="预览方案", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('[data-preview-slot]').studioAudioGraph?.node"
    )
    result = page.evaluate(CAPTURE)
    assert max(abs(x) for x in result["samples"]) < 0.951
    assert 0.00001 < amplitude(result["samples"], result["rate"], 907) < 0.02
    overlap = [
        row for row in result["observations"] if all(0.05 < w < 0.95 for w in row["weights"])
    ]
    assert overlap, (result["observations"][::20], page.locator(".viewer").inner_text())
    assert all(abs(sum(row["weights"]) - 1) < 0.001 for row in overlap)
    assert any(abs(row["times"][0] - row["times"][1]) > 2 for row in overlap)
    assert any(row["voice"] > 1 and 0 <= row["music"] < 1.05 for row in overlap)
    for row in overlap:
        out = row["times"][0] - 6  # The saved hook-first starts at source second six.
        assert abs(row["voice"] - (out - 0.5)) < 0.12
        phase_error = abs(row["music"] - out % 1)
        assert min(phase_error, abs(phase_error - 1)) < 0.12
    replay = page.get_by_role("button", name="预览方案", exact=True)
    replay.wait_for(state="visible", timeout=10000)
    page.wait_for_function(
        """() => {
        const parts=document.querySelector('.transport .tc').textContent.split('/').map(s=>s.trim());
        return parts[0] === parts[1] && parts[0] !== '00:00';
    }""",
        timeout=10000,
    )
    replay.click()
    page.wait_for_function(
        """() => {
        const video=document.querySelector('[data-preview-slot]');
        return !video.paused && video.currentTime >= 6 && video.currentTime < 6.5;
    }""",
        timeout=10000,
    )
    assert page.locator(".transport .tc").inner_text().split("/")[0].strip() == "00:00"
    restarted = page.evaluate(CAPTURE, 0.75)
    assert amplitude(restarted["samples"], restarted["rate"], 907) > 0.00001
    page.get_by_role("button", name="暂停", exact=True).click()
    page.wait_for_function(
        "() => [...document.querySelectorAll('video[data-preview-slot], audio')].every(el=>el.paused)"
    )
    page.wait_for_function(
        "() => document.querySelector('[data-preview-slot]').studioAudioGraph.gate.gain.value === 0",
        timeout=2000,
    )

    silent = page.evaluate(CAPTURE, 0.2)
    assert max(abs(x) for x in silent["samples"][2048:]) < 1e-8
    page.evaluate(
        "window.exitedAudioGraph=document.querySelector('[data-preview-slot]').studioAudioGraph"
    )
    page.get_by_role("tab", name="素材", exact=True).click()
    page.wait_for_function("() => exitedAudioGraph.context.state === 'closed'")
    assert page.evaluate("exitedAudioGraph.elements.every(el=>el.paused)")
