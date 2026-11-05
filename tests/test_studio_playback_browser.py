"""Real browser hooks with deterministic media clocks; no user footage or network."""

import functools
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from gamingcreator.application.rendering import output_start_frames

HARNESS = r"""
import {h, render} from '/vendor/preact.module.js';
import {useRef, useState} from '/vendor/hooks.module.js';
import {editTimeline, usePlanPlayer} from '/studio/preview.js';
import {useAudioPreview} from '/studio/audio.js';
Object.defineProperty(HTMLMediaElement.prototype, 'seekable', {
    get() { return {length:1, start:() => 0, end:() => 100}; }
});
const clocks = new WeakMap();
function state(el) {
    if (!clocks.has(el)) clocks.set(el, {time: 0, paused: true, ready: 4, seeking: false, writes: []});
    return clocks.get(el);
}
for (const [key, prop] of Object.entries({src:'src', currentTime:'time', paused:'paused', readyState:'ready', seeking:'seeking'})) {
    Object.defineProperty(HTMLMediaElement.prototype, key, {
        get() { return state(this)[prop] ?? ''; },
        set(value) {
            state(this)[prop] = value;
            if (key === 'currentTime') {
                state(this).writes.push(value);
                if (this.tagName === 'VIDEO') { state(this).seeking = true; this.dispatchEvent(new Event('seeking')); }
            }
        }
    });
}
HTMLMediaElement.prototype.play = function() { state(this).paused = false; this.dispatchEvent(new Event('playing')); return Promise.resolve(); };
HTMLMediaElement.prototype.load = function() {};
HTMLMediaElement.prototype.pause = function() { state(this).paused = true; };
const items = [
    {runId:'one', startUs:1000000, endUs:3000000, outStartUs:0, outDurUs:2000000},
    {runId:'one', startUs:7000000, endUs:9000000, outStartUs:2000000, outDurUs:2000000}
];
const urlFor = id => '/media/' + id;
const audio = {mix:{sourceGainDb:-12, bgm:{trackId:'music', gainDb:0}}};
const tracks = [{trackId:'music', trackReceiptSha256:'test'}];
function App() {
    const video = useRef(null);
    const [plan, setPlan] = useState(items);
    const [disabled, setDisabled] = useState("");
    window.transitionPlan = () => {
        setDisabled("转场请导出后观看");
        setPlan(editTimeline(items.map((item, index) => ({...item,
            speed:{numerator:1, denominator:1}, transitionIn:{frames:index ? 15 : 0}})), 30));
    };
    window.replacePlan = () => setPlan([{...items[0], startUs:11000000, endUs:13000000}]);
    const player = usePlanPlayer(video, plan, urlFor, null, disabled);
    window.player = player;
    return h('div', {}, h('video', {ref:video}), h('video', {id:'exported'}), useAudioPreview(player, audio, 30, video, tracks));
}
render(h(App), document.body);
window.media = () => ({videos:[...document.querySelectorAll('video')], video:[...document.querySelectorAll('[data-preview-slot]')].find(v => v.style.opacity !== '0') || document.querySelector('[data-preview-slot]'), music:document.querySelectorAll('audio')[1]});
window.clock = el => state(el);
window.event = (name) => media().video.dispatchEvent(new Event(name));
window.finishSeek = () => { document.querySelectorAll('video').forEach(v => {
    state(v).seeking = false; state(v).ready = 4;
    v.dispatchEvent(new Event('seeked')); v.dispatchEvent(new Event('canplay'));
}); };
window.closeEditor = () => { window.removedMedia = media(); render(null, document.body); };
"""


@pytest.fixture
def playback_page():
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(static))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.route("**/media/**", lambda route: route.fulfill(body=""))
            page.route("**/api/**", lambda route: route.fulfill(body=""))
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.evaluate("document.body.innerHTML = ''")
            page.add_script_tag(type="module", content=HARNESS)
            page.wait_for_function("window.player !== undefined")
            yield page
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def start(page, target=0):
    page.evaluate("target => { void player.seek(target, true); }", target)
    page.wait_for_function("[...document.querySelectorAll('video')].some(v => clock(v).seeking)")
    page.evaluate("finishSeek()")
    page.wait_for_function("player.playing && !media().music.paused")


def test_waiting_freezes_music_and_resume_aligns_once(playback_page):
    page = playback_page
    start(page)
    page.evaluate("clock(media().video).time = 1.8; event('timeupdate')")
    page.wait_for_function("player.outUs === 800000")
    page.evaluate("clock(media().music).time = .8; event('waiting')")
    page.wait_for_function("player.buffering && media().music.paused")
    page.evaluate("clock(media().video).time = 2; event('timeupdate')")
    assert page.evaluate("player.outUs") == 800000
    page.evaluate("event('playing')")
    page.wait_for_function("!player.buffering && !media().music.paused")
    writes = page.evaluate("clock(media().music).writes.length")
    page.evaluate("clock(media().music).time = 1.7; event('timeupdate')")
    page.wait_for_timeout(120)
    assert page.evaluate("clock(media().music).writes.length") == writes
    assert page.evaluate("media().music.currentTime") == 1.7


def test_cut_stop_and_latest_seek_win(playback_page):
    page = playback_page
    start(page)
    page.wait_for_function("[...document.querySelectorAll('video')].some(v => clock(v).time === 7)")
    page.evaluate("finishSeek()")
    writes_before_cut = page.evaluate(
        "[...document.querySelectorAll('video')].map(v => clock(v).writes.length)"
    )
    page.evaluate("clock(media().video).time = 3; event('timeupdate')")
    assert (
        page.evaluate("[...document.querySelectorAll('video')].map(v => clock(v).writes.length)")
        == writes_before_cut
    )
    page.wait_for_function("player.outUs === 2000000 && !media().music.paused")
    page.evaluate("void player.seek(500000, true)")
    page.wait_for_function("[...document.querySelectorAll('video')].some(v => clock(v).seeking)")
    page.evaluate("player.stop(); finishSeek()")
    page.wait_for_timeout(100)
    assert page.evaluate("!player.playing && media().video.paused && media().music.paused")
    page.evaluate("void player.seek(0, true); void player.seek(2500000, true)")
    page.wait_for_function(
        "[...document.querySelectorAll('video')].some(v => v.currentTime === 7.5)"
    )
    page.evaluate("finishSeek()")
    page.wait_for_function("player.playing && !media().music.paused")
    assert page.evaluate("player.outUs") == 2500000
    writes = page.evaluate("clock(media().video).writes.length")
    page.evaluate("player.stop(); void player.seek(2500000, true)")
    page.wait_for_function("player.playing")
    assert page.evaluate("clock(media().video).writes.length") == writes


def test_plan_replacement_cancels_pending_metadata_seek(playback_page):
    page = playback_page
    page.evaluate("clock(media().video).ready = 0; void player.seek(0, true)")
    page.wait_for_function("player.buffering")
    page.evaluate("replacePlan()")
    page.wait_for_function("player.totalUs === 2000000")
    page.evaluate("clock(media().video).ready = 4; event('loadedmetadata')")
    page.wait_for_timeout(100)
    assert page.evaluate("clock(media().video).writes") == []
    assert page.evaluate("!player.playing && media().video.paused")
    start(page)
    assert page.evaluate("media().video.currentTime") == 11


def test_leaving_editor_stops_detached_media(playback_page):
    page = playback_page
    start(page)
    page.evaluate("closeEditor()")
    page.wait_for_function("removedMedia.videos.every(v => v.paused) && removedMedia.music.paused")


REAL_HARNESS = r"""
import {h, render} from '/vendor/preact.module.js';
import {useRef} from '/vendor/hooks.module.js';
import {editTimeline, usePlanPlayer} from '/studio/preview.js';
window.writes = []; window.handoffs = []; window.preloaded = [];
const descriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime');
Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {...descriptor, set(value) {
    window.writes.push({value,src:this.src}); descriptor.set.call(this,value);
}});
const clips = [1, 7, window.unreachable ? 20 : 2].map((start, i) => ({
    runId:i === 2 ? 'two' : 'one', startUs:start*1e6,
    endUs:(start + window.speed)*1e6,
    speed:{numerator:window.speed*2, denominator:2}, transitionIn:{frames:0}
}));
const items = editTimeline(clips, 30);
const urlFor = id => '/media/' + id;
function App() {
    const first = useRef(null), second = useRef(null);
    const player = usePlanPlayer(first, items, urlFor, second);
    window.player = player;
    return h('div', {}, h('video', {ref:first}), h('video', {ref:second}));
}
render(h(App), document.body);
window.activeVideo = () => [...document.querySelectorAll('video')].find(v => v.style.opacity === '1');
let previous = -1;
function capture() {
    const video = activeVideo(), out = window.player.outUs;
    const index = Math.floor(out / 1e6);
    if (video && index !== previous && player.playing) {
        handoffs.push({index, src:video.src, time:video.currentTime});
        previous = index;
    }
    for (const el of document.querySelectorAll('video')) {
        if (el.style.opacity === '0' && el.readyState >= 3 && !el.seeking && el.currentTime >= 7) {
            preloaded.push(el.currentTime);
        }
    }
    requestAnimationFrame(capture);
}
requestAnimationFrame(capture);
"""


@pytest.mark.parametrize(
    ("speed", "range_supported"), [(0.5, True), (1, True), (2, True), (1, False)]
)
def test_real_decoders_preload_distant_same_file_and_cross_file(tmp_path, speed, range_supported):
    """Actual Chromium decoding, not mocked media readiness or clocks."""
    playwright = pytest.importorskip("playwright.sync_api")
    media = tmp_path / "generated.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=30:duration=10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(media),
        ],
        check=True,
        timeout=30,
        capture_output=True,
    )
    static = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(static))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            data = media.read_bytes()

            def serve_media(route):
                requested = route.request.headers.get("range")
                headers = {
                    "Accept-Ranges": "bytes" if range_supported else "none",
                    "Content-Type": "video/mp4",
                }
                if requested and range_supported:
                    first, last = requested.removeprefix("bytes=").split("-", 1)
                    start, end = int(first), int(last) if last else len(data) - 1
                    end = min(end, len(data) - 1)
                    headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
                    route.fulfill(status=206, headers=headers, body=data[start : end + 1])
                else:
                    route.fulfill(status=200, headers=headers, body=data)

            page.route("**/media/**", serve_media)
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.evaluate("document.body.innerHTML = ''")
            page.evaluate("value => window.speed = value", speed)
            page.evaluate("value => window.unreachable = value", not range_supported)
            page.add_script_tag(type="module", content=REAL_HARNESS)
            page.wait_for_function("window.player !== undefined")
            page.evaluate("void player.seek(0, true)")
            if not range_supported:
                page.wait_for_function("!player.playing && player.error.length > 0")
                assert page.evaluate("player.outUs") in (0, 2_000_000)
                assert page.evaluate("[...document.querySelectorAll('video')].every(v => v.paused)")
                handoffs = page.evaluate("handoffs")
                for row in handoffs:
                    assert row["index"] < 2
                    assert row["time"] == pytest.approx([1, 7][row["index"]], abs=0.12)
                browser.close()
                return
            page.wait_for_function("player.playing && activeVideo()?.readyState >= 3")
            page.wait_for_function("!player.playing && player.outUs === player.totalUs")
            starts = output_start_frames((30, 30, 30))
            assert page.evaluate("player.totalUs") == (starts[-1] + 30) * 1_000_000 / 30
            handoffs = page.evaluate("handoffs")
            assert [row["index"] for row in handoffs] == [0, 1, 2]
            assert [row["time"] for row in handoffs] == pytest.approx([1, 7, 2], abs=0.12)
            assert handoffs[2]["src"].endswith("/two")
            assert page.evaluate("preloaded.length") > 0
            assert page.evaluate("player.error") == ""
            assert page.evaluate("[...document.querySelectorAll('video')].every(v => v.paused)")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_speculative_seek_does_not_freeze_music(playback_page):
    page = playback_page
    start(page)
    page.wait_for_function(
        "[...document.querySelectorAll('video')].some(v => v.style.opacity === '0' && clock(v).seeking)"
    )
    assert page.evaluate("!player.buffering && !media().music.paused")
    page.evaluate("player.stop()")
    assert page.evaluate("[...document.querySelectorAll('video')].every(v => v.paused)")


def test_transition_preview_disabled_preserves_export_duration(playback_page):
    page = playback_page
    page.evaluate("transitionPlan()")
    page.wait_for_function("player.totalUs === 3500000 && player.error.length > 0")
    starts = output_start_frames((60, 60), (0, 15))
    assert page.evaluate("player.totalUs") == (starts[-1] + 60) * 1_000_000 / 30
    page.evaluate("void player.seek(0, true); player.toggle()")
    page.wait_for_timeout(100)
    assert page.evaluate("!player.playing && !player.buffering")
    assert page.evaluate(
        "[...document.querySelectorAll('video')].every(v => v.paused && !clock(v).writes.length)"
    )


def test_stop_during_preload_then_resume_restarts_pending_slot(playback_page):
    page = playback_page
    start(page)
    page.wait_for_function(
        "[...document.querySelectorAll('[data-preview-slot]')].some(v => v.style.opacity === '0' && clock(v).seeking)"
    )
    page.evaluate("player.stop(); void player.seek(0, true)")
    page.wait_for_function("player.playing")
    page.evaluate("finishSeek()")
    page.evaluate("clock(media().video).time = 3; event('timeupdate')")
    page.wait_for_function("player.outUs === 2000000 && !player.buffering")
    assert page.evaluate("player.playing && !media().video.paused && !player.error")
    page.evaluate("clock(media().video).time = 9; event('timeupdate')")
    page.wait_for_function("!player.playing && player.outUs === player.totalUs")


def test_seek_into_preloaded_clip_releases_previous_slot(playback_page):
    page = playback_page
    start(page)
    page.wait_for_function(
        "[...document.querySelectorAll('[data-preview-slot]')].some(v => v.currentTime === 7)"
    )
    page.evaluate("finishSeek(); void player.seek(2500000, true)")
    page.wait_for_function(
        "[...document.querySelectorAll('[data-preview-slot]')].some(v => v.currentTime === 7.5)"
    )
    page.evaluate("finishSeek()")
    page.wait_for_function("player.playing && !player.buffering")
    visible = page.evaluate(
        "[...document.querySelectorAll('[data-preview-slot]')].filter(v => v.style.opacity === '1').map(v => v.currentTime)"
    )
    assert visible == [7.5]


def test_source_gain_does_not_change_mixed_export_volume(playback_page):
    page = playback_page
    start(page)
    assert page.evaluate("media().video.volume") == pytest.approx(10 ** (-12 / 20))
    assert page.evaluate("document.querySelector('#exported').volume") == 1
