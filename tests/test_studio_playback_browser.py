"""Real browser hooks with deterministic media clocks; no user footage or network."""

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HARNESS = r"""
import {h, render} from '/vendor/preact.module.js';
import {useRef, useState} from '/vendor/hooks.module.js';
import {usePlanPlayer} from '/studio/preview.js';
import {useAudioPreview} from '/studio/audio.js';
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
HTMLMediaElement.prototype.pause = function() { state(this).paused = true; };
const items = [
    {runId:'one', startUs:1000000, endUs:3000000, outStartUs:0, outDurUs:2000000},
    {runId:'one', startUs:7000000, endUs:9000000, outStartUs:2000000, outDurUs:2000000}
];
const urlFor = id => '/media/' + id;
const audio = {mix:{bgm:{trackId:'music', gainDb:0}}};
const tracks = [{trackId:'music', trackReceiptSha256:'test'}];
function App() {
    const video = useRef(null);
    const [plan, setPlan] = useState(items);
    window.replacePlan = () => setPlan([{...items[0], startUs:11000000, endUs:13000000}]);
    const player = usePlanPlayer(video, plan, urlFor);
    window.player = player;
    return h('div', {}, h('video', {ref:video}), useAudioPreview(player, audio, 30, video, tracks));
}
render(h(App), document.body);
window.media = () => ({video:document.querySelector('video'), music:document.querySelectorAll('audio')[1]});
window.clock = el => state(el);
window.event = (name) => media().video.dispatchEvent(new Event(name));
window.finishSeek = () => { state(media().video).seeking = false; state(media().video).ready = 4; event('seeked'); event('canplay'); };
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
    page.wait_for_function("clock(media().video).seeking")
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
    page.evaluate("clock(media().video).time = 3; event('timeupdate')")
    page.wait_for_function("clock(media().video).seeking && media().music.paused")
    page.evaluate("finishSeek()")
    page.wait_for_function("player.outUs === 2000000 && !media().music.paused")
    page.evaluate("void player.seek(500000, true)")
    page.wait_for_function("clock(media().video).seeking")
    page.evaluate("player.stop(); finishSeek()")
    page.wait_for_timeout(100)
    assert page.evaluate("!player.playing && media().video.paused && media().music.paused")
    page.evaluate("void player.seek(0, true); void player.seek(2500000, true)")
    page.wait_for_function("media().video.currentTime === 7.5")
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
    page.wait_for_function("removedMedia.video.paused && removedMedia.music.paused")
