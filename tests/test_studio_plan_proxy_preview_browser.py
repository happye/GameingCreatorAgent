"""B04: 方案双播放器按已核代理预加载；变速转场仍走输出时钟；保存不带预览地址。"""
# ruff: noqa: F811

from __future__ import annotations

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from browser_http import browser_server
from test_benchmark_source_clock_browser import probe_source, synthesize
from test_creation_jobs import finish, service  # noqa: F401
from test_preview_clock_align_browser import plant_playable_proxy
from test_studio_audio_graph_browser import saved_plan

from gamingcreator.application.browser_source_clock import build_source_clock, clock_document
from gamingcreator.ui import server

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

HARNESS = r"""
import {h, render} from '/vendor/preact.module.js';
import {useRef} from '/vendor/hooks.module.js';
import {editTimeline, usePlanPlayer} from '/studio/preview.js';
import {choosePreview} from '/studio/api.js';
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
const runs = {
    one: {videoUrl:'/api/media?project=p&run=one', proxyUrl:'/api/media?project=p&run=one&proxy=1'},
    two: {videoUrl:'/api/media?project=p&run=two', proxyUrl:'https://evil.example/api/media?project=p&run=two&proxy=1'},
};
const urlFor = (runId) => choosePreview(runs[runId].videoUrl, runs[runId].proxyUrl).url;
const clips = [
    {runId:'one', startUs:0, endUs:2000000, speed:{numerator:1, denominator:1}, transitionIn:{frames:0}},
    {runId:'two', startUs:0, endUs:2000000, speed:{numerator:2, denominator:1}, transitionIn:{frames:15}},
];
window.expected = editTimeline(clips, 30);
function App() {
    const first = useRef(null), second = useRef(null);
    const player = usePlanPlayer(first, window.expected, urlFor, second);
    window.player = player;
    return h('div', {}, h('video', {ref:first}), h('video', {ref:second}));
}
render(h(App), document.body);
window.finishSeek = () => { document.querySelectorAll('video').forEach(v => {
    state(v).seeking = false; state(v).ready = 4;
    v.dispatchEvent(new Event('seeked')); v.dispatchEvent(new Event('canplay'));
}); };
window.slotInfo = () => [...document.querySelectorAll('[data-preview-slot]')].map(v => ({
    src: v.getAttribute('src') || v.src, rate: v.playbackRate, opacity: v.style.opacity,
}));
"""


def query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url or "").query).items()}


def test_dual_slots_follow_verified_proxy_speed_and_output_clock():
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(static))
    http = browser_server(handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.route("**/api/**", lambda route: route.fulfill(body=""))
            page.goto(f"http://127.0.0.1:{http.server_port}/")
            page.evaluate("document.body.innerHTML = ''")
            page.add_script_tag(type="module", content=HARNESS)
            page.wait_for_function("window.player !== undefined")
            expected = page.evaluate("expected")
            assert expected[0]["outStartUs"] == 0
            assert expected[0]["rate"] == 1
            assert expected[1]["transitionFrames"] == 15
            assert expected[1]["rate"] == 2
            # Official clock: 60 frames minus a 15-frame dissolve, then 30 frames at 2x.
            assert expected[1]["outStartFrame"] == 45
            assert expected[1]["outStartUs"] == 1_500_000
            page.evaluate("void player.seek(0)")
            page.wait_for_function(
                "[...document.querySelectorAll('video')].some(v => (v.getAttribute('src')||v.src).includes('proxy=1'))"
            )
            page.evaluate("finishSeek()")
            page.wait_for_function(
                "slotInfo().filter(v => v.src).length >= 2 || player.totalUs > 0"
            )
            page.wait_for_timeout(50)
            page.evaluate("finishSeek()")
            slots = page.evaluate("slotInfo()")
            srcs = [query(item["src"]) for item in slots if item["src"]]
            assert any(item.get("run") == "one" and item.get("proxy") == "1" for item in srcs)
            assert any(item.get("run") == "two" and "proxy" not in item for item in srcs)
            rates = {query(item["src"]).get("run"): item["rate"] for item in slots if item["src"]}
            assert rates.get("one") == 1
            assert rates.get("two") == 2
            overlap = expected[1]["outStartUs"] + 250_000
            page.evaluate("target => void player.seek(target)", overlap)
            page.evaluate("finishSeek()")
            page.wait_for_function(f"player.outUs === {overlap}")
            opacities = page.evaluate("slotInfo().map(v => Number(v.opacity))")
            assert sum(value > 0 for value in opacities) == 2
            browser.close()
    finally:
        http.shutdown()
        http.server_close()


def test_edit_workspace_preview_uses_proxy_and_save_keeps_clip_rows(service, monkeypatch, tmp_path):  # noqa: ARG001
    playwright = pytest.importorskip("playwright.sync_api")
    root_job, _track, asset = saved_plan(service, monkeypatch)
    preview = tmp_path / "preview-proxy.mp4"
    synthesize(preview, "zero")
    official = clock_document(build_source_clock(probe_source(preview)))
    plant_playable_proxy(service.repository, preview, asset.sha256, official["durationUs"])
    edit = service.edit(root_job, "hook-first")
    rows = [
        {
            **{key: row[key] for key in ("clipId", "startUs", "endUs")},
            "speed": {"numerator": 1, "denominator": 1},
        }
        for row in edit["clips"][:2]
    ]
    rows[0]["transitionIn"] = {"type": "cut", "frames": 0}
    rows[1]["transitionIn"] = {"type": "crossfade", "frames": 30}
    revision = service.submit(
        "revision",
        dict(
            requestId="d" * 32,
            parentJobId=root_job,
            planId="hook-first",
            expectedParentReceiptSha256=edit["expectedParentReceiptSha256"],
            clips=rows,
        ),
    )["jobId"]
    completed = finish(service, revision)
    assert completed["status"] == "completed", completed
    video = "/api/media?project=artifacts/project&run=run"
    posted = []

    async def runs(_project, *args, **kwargs):
        return {
            "runs": [
                {
                    "id": "run",
                    "sourceName": "tone.mp4",
                    "status": "completed",
                    "completedEligible": True,
                    "sourceClock": official,
                    "videoUrl": video,
                    "proxyUrl": video + "&proxy=1",
                }
            ]
        }

    monkeypatch.setattr(server, "project_runs_payload", runs)
    http = server.create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as runtime:
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

            def capture(route):
                request = route.request
                if request.method == "POST" and "/api/creation/" in request.url:
                    posted.append(json.loads(request.post_data or "{}"))
                route.continue_()

            page.route("**/api/creation/**", capture)
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            expect(page.locator(".timeline .clip")).to_have_count(2)
            page.get_by_role("button", name="预览方案").click()
            page.wait_for_function(
                """() => [...document.querySelectorAll('[data-preview-slot]')]
                    .some(v => (v.getAttribute('src') || v.src || '').includes('proxy=1'))""",
                timeout=20000,
            )
            srcs = page.evaluate(
                "[...document.querySelectorAll('[data-preview-slot]')].map(v => v.getAttribute('src') || v.src || '')"
            )
            assert any(query(src).get("proxy") == "1" for src in srcs)
            page.get_by_title("第 1 个镜头", exact=False).click(force=True)
            end = page.locator('fieldset[aria-label="镜头编辑"] label:has-text("出点") input')
            expect(end).to_be_visible()
            end.fill(str(float(end.input_value()) - 0.1))
            end.press("Tab")
            button = page.get_by_role("button", name="保存版本")
            expect(button).to_be_enabled(timeout=10000)
            button.click()
            page.wait_for_function("() => window.__unused || true")
            page.wait_for_timeout(500)
            assert posted, "save did not post a revision"
            body = next(
                item
                for item in posted
                if item.get("clips") or item.get("kind") == "revision" or "clips" in item
            )
            saved = body.get("clips") or body.get("body", {}).get("clips")
            if saved is None and "payload" in body:
                saved = body["payload"].get("clips")
            # client.submit may wrap fields at the top level.
            if saved is None:
                raise AssertionError(f"unexpected save body keys: {sorted(body)}")
            for row in saved:
                assert set(row) <= {"clipId", "startUs", "endUs", "speed", "transitionIn"}
                assert "proxy" not in json.dumps(row)
                assert "videoUrl" not in row and "proxyUrl" not in row
            assert [row["clipId"] for row in saved] == [row["clipId"] for row in rows]
            assert not errors, errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
