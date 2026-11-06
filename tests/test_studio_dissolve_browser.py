"""Generated local media: real 206 decoding and export dissolve pixel comparisons."""

import asyncio
import functools
import json
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace

import pytest
from browser_http import browser_server

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderPlan
from gamingcreator.infrastructure.crossfade_render import compose_transitions

HARNESS = r"""
import {h, render} from '/vendor/preact.module.js';
import {useRef} from '/vendor/hooks.module.js';
import {editTimeline, usePlanPlayer} from '/studio/preview.js';
const rate=window.speed;
const clips=[1,10,2].map((start,i)=>({runId:i===2?'two':'one',
 startUs:start*1e6,endUs:(start+3*rate)*1e6,
 sourceClock:{originUs:0},speed:{numerator:rate*2,denominator:2},transitionIn:{frames:i?30:0}}));
const items=editTimeline(clips,30), urlFor=id=>'/media/'+id;
function App(){const first=useRef(null),second=useRef(null);
 window.player=usePlanPlayer(first,items,urlFor,second);
 return h('div',{id:'stage',style:'position:relative;width:160px;height:90px;background:black'},
 h('video',{ref:first,style:'position:absolute;width:160px;height:90px'}),
 h('video',{ref:second,style:'position:absolute;width:160px;height:90px'}));}
render(h(App),document.body);
"""


def ffmpeg(*args):
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *map(str, args)],
        check=True,
        capture_output=True,
        timeout=45,
    ).stdout


def generate_sources(tmp_path):
    one, two = tmp_path / "one.mp4", tmp_path / "two.mp4"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=red:s=160x90:r=30:d=8",
        "-f",
        "lavfi",
        "-i",
        "color=lime:s=160x90:r=30:d=10",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=18",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "2:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        one,
    )
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=blue:s=160x90:r=30:d=10",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:duration=10",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        two,
    )
    return one, two


def generate(tmp_path, speed):
    one, two = generate_sources(tmp_path)
    parts = []
    for i, (source, start) in enumerate([(one, 1), (one, 10), (two, 2)]):
        part = tmp_path / f"part{i}.nut"
        ffmpeg(
            "-ss",
            start,
            "-t",
            3 * speed,
            "-i",
            source,
            "-vf",
            f"setpts=(PTS-STARTPTS)/{speed},fps=30",
            "-af",
            f"atempo={speed}",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            part,
        )
        parts.append(part)
    plan = RenderPlan(tuple(SimpleNamespace(output_frames=90) for _ in parts), 30, (0, 30, 30))
    rendered, _ = asyncio.run(
        compose_transitions(
            "ffmpeg", plan, parts, CancellationContext("generated-dissolve", 60), 160, 90
        )
    )
    assert (
        len(ffmpeg("-i", rendered, "-map", "0:v", "-f", "rawvideo", "-pix_fmt", "gray", "-"))
        == plan.frames * 160 * 90
    )
    return {"one": one.read_bytes(), "two": two.read_bytes()}, rendered, plan


def range_reply(route, media):
    data = media[route.request.url.rsplit("/", 1)[-1]]
    requested = route.request.headers.get("range", "bytes=0-")
    first, last = requested.removeprefix("bytes=").split("-", 1)
    start, end = int(first), min(int(last) if last else len(data) - 1, len(data) - 1)
    route.fulfill(
        status=206,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes {start}-{end}/{len(data)}",
        },
        body=data[start : end + 1],
    )


def compare_paused_frames(page, rendered, artifact_dir):
    for overlap in (2, 4):
        for progress in (0.25, 0.5, 0.75):
            target = overlap + progress
            page.evaluate("target => {void player.seek(target*1e6)}", target)
            page.wait_for_function("!player.buffering && !player.playing")
            page.wait_for_timeout(90)
            shot = page.locator("#stage").screenshot(path=str(artifact_dir / f"{target}.png"))
            pixels = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    "pipe:0",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgb24",
                    "-",
                ],
                input=shot,
                capture_output=True,
                check=True,
                timeout=10,
            ).stdout
            preview = tuple(pixels[(45 * 160 + 80) * 3 : (45 * 160 + 80) * 3 + 3])
            raw = ffmpeg(
                "-i",
                rendered,
                "-ss",
                target,
                "-frames:v",
                1,
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            )
            offset = (45 * 160 + 80) * 3
            expected = tuple(raw[offset : offset + 3])
            assert preview == pytest.approx(expected, abs=12), (target, preview, expected)
            assert page.evaluate("[...document.querySelectorAll('video')].every(v=>v.paused)")
            assert page.evaluate(
                "[...document.querySelectorAll('video')].map(v=>v.volume)"
            ) == pytest.approx([1 - progress, progress])


def capture_audio(page):
    page.evaluate(r"""async () => {
        const context = new AudioContext();
        const analyser = context.createAnalyser(); analyser.fftSize = 4096;
        analyser.smoothingTimeConstant = 0;
        for (const video of document.querySelectorAll('video')) {
            context.createMediaElementSource(video).connect(analyser);
        }
        analyser.connect(context.destination); await context.resume();
        window.audioContext = context; window.audioSamples = [];
        const spectrum = new Float32Array(analyser.frequencyBinCount);
        function sample() {
            const out = player.outUs / 1e6;
            if (player.playing && !player.buffering && out > 4.15 && out < 4.85) {
                analyser.getFloatFrequencyData(spectrum);
                const peak = hz => {
                    const bin = Math.round(hz * analyser.fftSize / context.sampleRate);
                    return Math.max(...spectrum.slice(bin - 2, bin + 3));
                };
                audioSamples.push({out, old: peak(440), next: peak(880)});
            }
            if (out < player.totalUs / 1e6) requestAnimationFrame(sample);
        }
        requestAnimationFrame(sample);
    }""")


def assert_audio_ramp(page):
    rows = page.evaluate("audioSamples")
    early = [r for r in rows if 4.2 < r["out"] < 4.35]
    late = [r for r in rows if 4.65 < r["out"] < 4.8]
    assert early and late
    # Decoded tones through a real AudioContext, measured after media volume.
    # Timing/FFT windows permit latency; this asserts direction, not sample identity.
    assert sum(r["old"] - r["next"] for r in early) / len(early) > 2
    assert sum(r["next"] - r["old"] for r in late) / len(late) > 2


@pytest.mark.parametrize("speed", [0.5, 1, 2])
def test_real_dissolve_matches_export_and_completes(tmp_path, speed):
    playwright = pytest.importorskip("playwright.sync_api")
    media, rendered, plan = generate(tmp_path, speed)
    static = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
    server = browser_server(functools.partial(SimpleHTTPRequestHandler, directory=str(static)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    artifacts = Path(".cache/dissolve-evidence") / str(speed)
    artifacts.mkdir(parents=True, exist_ok=True)
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.route("**/media/**", lambda route: range_reply(route, media))
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.evaluate("document.body.innerHTML=''")
            page.evaluate("speed=>window.speed=speed", speed)
            page.add_script_tag(type="module", content=HARNESS)
            page.wait_for_function("window.player !== undefined")
            assert page.evaluate("player.totalUs") == plan.frames * 1e6 / plan.fps
            compare_paused_frames(page, rendered, artifacts)
            capture_audio(page)
            page.evaluate("void player.seek(0,true)")
            page.wait_for_function("player.playing")
            page.wait_for_function(
                "!player.playing && player.outUs===player.totalUs", timeout=20000
            )
            (artifacts / "audio-spectrum.json").write_text(
                json.dumps(page.evaluate("audioSamples")), encoding="utf-8"
            )
            assert_audio_ramp(page)
            assert page.evaluate("player.error") == ""
            assert page.evaluate("[...document.querySelectorAll('video')].every(v=>v.paused)")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
