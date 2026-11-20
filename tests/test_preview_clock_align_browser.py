"""B05: 代理与原片必须用官方源时钟对齐；对不齐就继续用原片，不能猜偏移。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

import pytest
from test_benchmark_source_clock_browser import probe_source, synthesize
from test_detail_inspection import refuse_sends
from test_inspection_http import workspace
from test_sqlite_store import CONFIG, event_fixture, sha

from gamingcreator.application.browser_source_clock import build_source_clock, clock_document
from gamingcreator.application.media import SamplingParameters
from gamingcreator.domain.media import MediaPreprocessingResult, VisualEvidence
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.proxy_media import SETTINGS, proxy_directory
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

CLOCK_JS = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/source-clock.js"


def plant_playable_proxy(
    repository, source: Path, source_sha256: str, source_duration_us: int, body: bytes | None = None
):
    directory = proxy_directory(repository, source_sha256)
    directory.mkdir(parents=True, exist_ok=True)
    data = body if body is not None else source.read_bytes()
    (directory / "proxy.mp4").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (directory / "receipt.json").write_text(
        json.dumps(
            {
                "schemaVersion": "editing-proxy-receipt-v1",
                "sourceSha256": source_sha256,
                "sourceDurationUs": source_duration_us,
                "settings": SETTINGS,
                "bytes": len(data),
                "budgetBytes": len(data) + 1,
                "durationUs": source_duration_us,
                "proxySha256": digest,
                "use": "preview-only; renders read the original source",
            }
        ),
        encoding="utf-8",
    )


def seed_playable_project(root: Path, *, kind: str = "zero"):
    source = root / "artifacts" / "source.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    synthesize(source, kind)
    return _seed_from_file(root, source)


@pytest.fixture(scope="module")
def clock_videos(tmp_path_factory):
    root = tmp_path_factory.mktemp("clock-videos")
    zero, nonzero = root / "zero.mp4", root / "nonzero.mp4"
    synthesize(zero, "zero")
    synthesize(nonzero, "nonzero")
    return {"zero": zero, "nonzero": nonzero}


def _serve(directory: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_align_preview_keeps_original_when_proxy_axis_does_not_match(clock_videos):
    playwright = pytest.importorskip("playwright.sync_api")
    official = clock_document(build_source_clock(probe_source(clock_videos["nonzero"])))
    server = _serve(clock_videos["nonzero"].parent)
    try:
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.add_script_tag(path=str(CLOCK_JS))
            result = page.evaluate(
                """async ({clock, original, proxy}) => {
                    const aligned = await SourceClock.alignPreview([clock], original, original, true);
                    const mismatched = await SourceClock.alignPreview([clock], original, proxy, true);
                    return {aligned, mismatched, originUs: clock.originUs};
                }""",
                {
                    "clock": official,
                    "original": f"{origin}/nonzero.mp4",
                    "proxy": f"{origin}/zero.mp4",
                },
            )
            browser.close()
    finally:
        server.shutdown()
    assert result["aligned"]["source"] == "proxy"
    assert result["aligned"]["established"] is True
    assert result["aligned"]["reason"] is None
    assert result["aligned"]["clock"]["originUs"] == official["originUs"]
    assert result["mismatched"]["source"] == "original"
    assert result["mismatched"]["reason"] == "axis_mismatch"
    assert result["mismatched"]["clock"]["originUs"] == official["originUs"]
    assert "0" not in str(result["mismatched"]["clock"]["originUs"]) or official["originUs"] != 0
    assert result["mismatched"]["clock"]["originUs"] != 0


def test_preview_clock_reason_text_is_explicit():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page()
        page.add_script_tag(path=str(CLOCK_JS))
        text = page.evaluate(
            """() => ({
                axis: SourceClock.previewClockReason("axis_mismatch"),
                duration: SourceClock.previewClockReason("duration_mismatch"),
                http: SourceClock.previewClockReason("proxy_http_failed"),
                decode: SourceClock.previewClockReason("proxy_decode_failed"),
                other: SourceClock.previewClockReason("seek_incomplete"),
                empty: SourceClock.previewClockReason(null),
                playbackEmpty: SourceClock.playbackErrorText(null),
                playbackAbort: SourceClock.playbackErrorText({code: 1}),
                playbackNetwork: SourceClock.playbackErrorText({code: 2}),
                playbackDecode: SourceClock.playbackErrorText({code: 3}),
                playbackUnsupported: SourceClock.playbackErrorText({code: 4}),
            })"""
        )
        browser.close()
    assert text == {
        "axis": "代理起点与原片对不齐，已改用原片",
        "duration": "代理时长与原片对不齐，已改用原片",
        "http": "代理无法加载，已改用原片",
        "decode": "代理解码失败，已改用原片",
        "other": "代理时钟不可信，已改用原片",
        "empty": None,
        "playbackEmpty": "原视频暂时无法播放",
        "playbackAbort": "原片播放被中止，请重试",
        "playbackNetwork": "原片加载失败，暂时无法播放",
        "playbackDecode": "原片解码失败，暂时无法播放",
        "playbackUnsupported": "浏览器无法播放该原片",
    }


def _video_query(page, locator):
    src = page.locator(locator).get_attribute("src") or ""
    return {key: values[0] for key, values in parse_qs(urlparse(src).query).items()}


def test_workbench_aligned_proxy_toggle_stays_on_the_same_source_moment(
    tmp_path, monkeypatch, clock_videos
):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    project, bundle, _timeline = _seed_from_file(tmp_path, clock_videos["zero"])
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    official = clock_document(build_source_clock(bundle.asset))
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#timeline-count")).not_to_have_text("0", timeout=20000)
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            expect(page.locator("#preview-clock-reason")).to_be_hidden()
            assert _video_query(page, "#source-video").get("proxy") == "1"
            page.wait_for_function(
                """(origin) => {
                    const v = document.getElementById("source-video");
                    return v && Number.isFinite(v.duration) && v.duration > 0 && window.SourceClock
                        && SourceClock.sourceUsToPlayerSeconds(origin, 500000) !== null;
                }""",
                arg=official,
                timeout=20000,
            )
            page.evaluate(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    v.currentTime = SourceClock.sourceUsToPlayerSeconds(clock, 500000);
                }""",
                official,
            )
            page.wait_for_function(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    const us = SourceClock.playerToSourceUs(clock, v.currentTime);
                    return us !== null && Math.abs(us - 500000) <= 80000;
                }""",
                arg=official,
                timeout=10000,
            )
            page.locator("#proxy-toggle-input").uncheck()
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            assert "proxy" not in _video_query(page, "#source-video")
            page.wait_for_function(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    if (!v || !v.currentSrc || v.currentSrc.includes("proxy=1")) return false;
                    const us = SourceClock.playerToSourceUs(clock, v.currentTime);
                    return us !== null && Math.abs(us - 500000) <= 80000;
                }""",
                arg=official,
                timeout=20000,
            )
            page.locator("#proxy-toggle-input").check()
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            page.wait_for_function(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    if (!v || !v.currentSrc || !v.currentSrc.includes("proxy=1")) return false;
                    const us = SourceClock.playerToSourceUs(clock, v.currentTime);
                    return us !== null && Math.abs(us - 500000) <= 80000;
                }""",
                arg=official,
                timeout=20000,
            )
            assert not errors, errors
        finally:
            browser.close()


def _seed_from_file(
    root: Path, video: Path, *, run_id: str = "run-1", source_name: str = "source.mp4"
):
    source_root = root / "artifacts"
    source_root.mkdir(parents=True, exist_ok=True)
    source = source_root / source_name
    if source.resolve() != video.resolve():
        source.write_bytes(video.read_bytes())
    asset = probe_source(source)
    project = source_root / "project"
    directory = project / "runs" / run_id / "media"
    directory.mkdir(parents=True, exist_ok=True)
    image_path = directory / "frame.png"
    image_path.write_bytes(b"not a real image: storage fixture")
    video = next(stream for stream in asset.streams if stream.kind == "video")
    image = VisualEvidence(
        f"{run_id}:{asset.media_id}:image:000000",
        image_path,
        sha(image_path),
        video.start_pts,
        video.time_base,
        asset.instant(video.start_pts, video.time_base),
    )
    bundle = MediaPreprocessingResult(
        asset, (image,), None, directory / "media-manifest.json", "fixture-v1", "fixture-processor"
    )
    write_manifest(bundle, SamplingParameters())
    event = replace(
        event_fixture(
            bundle, run_id=run_id, event_id=f"{run_id}:{bundle.asset.media_id}:event:" + "ab" * 12
        ),
        observable_facts=("画面左侧有白色头发的主体。",),
        modality="visual",
    )

    async def create():
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run(run_id, bundle.asset, CONFIG)
            await store.begin_stage(run_id, "media", bundle.asset.sha256)
            await store.persist_media_bundle(run_id, bundle)
            await store.begin_stage(run_id, "vision", "a" * 64)
            await store.persist_timeline(run_id, "vision", (event,), (), "b" * 64)
            await store.complete_run(run_id)
            return await store.load_timeline(run_id, require_completed=True)
        finally:
            await store.close()

    return project, bundle, asyncio.run(create())


def test_workbench_and_studio_keep_original_when_proxy_pts_does_not_match(
    tmp_path, monkeypatch, clock_videos
):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    project, bundle, _timeline = _seed_from_file(tmp_path, clock_videos["nonzero"])
    plant_playable_proxy(
        tmp_path,
        bundle.asset.source_path,
        bundle.asset.sha256,
        bundle.asset.duration_us,
        body=clock_videos["zero"].read_bytes(),
    )
    official = clock_document(build_source_clock(bundle.asset))
    assert official["originUs"] > 0
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#timeline-count")).not_to_have_text("0", timeout=20000)
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("[data-preview-clock-reason]")).to_have_attribute(
                "data-preview-clock-reason", "axis_mismatch", timeout=20000
            )
            expect(page.locator("#preview-clock-reason")).to_have_text(
                "代理起点与原片对不齐，已改用原片"
            )
            assert "proxy" not in _video_query(page, "#source-video")
            page.wait_for_function(
                "() => document.getElementById('source-video')?.readyState >= 1", timeout=20000
            )
            page.evaluate(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    v.currentTime = SourceClock.sourceUsToPlayerSeconds(clock, 0);
                }""",
                official,
            )
            observed = page.evaluate(
                """(clock) => {
                    const v = document.getElementById("source-video");
                    return {
                        currentTime: v.currentTime,
                        sourceUs: SourceClock.playerToSourceUs(clock, v.currentTime),
                        originSeconds: clock.originUs / 1e6,
                    };
                }""",
                official,
            )
            # 停在源时刻 0，也就是播放器时间约等于原片起点，而不是被猜成从 0 秒起播。
            assert observed["currentTime"] == pytest.approx(official["originUs"] / 1e6, abs=0.08)
            assert observed["sourceUs"] == pytest.approx(0, abs=80_000)
            assert observed["currentTime"] > 1  # 非零 PTS，没有被猜成 0

            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("[data-preview-clock-reason]")).to_have_attribute(
                "data-preview-clock-reason", "axis_mismatch"
            )
            expect(page.locator("[data-preview-clock-reason]")).to_have_text(
                "代理起点与原片对不齐，已改用原片"
            )
            assert "proxy" not in _video_query(page, ".viewer video")
            assert not errors, errors
        finally:
            browser.close()


def test_studio_aligned_proxy_is_used_when_clocks_match(tmp_path, monkeypatch, clock_videos):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = _seed_from_file(tmp_path, clock_videos["zero"])
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text(
                "编辑代理（非原片）", timeout=20000
            )
            expect(page.locator("[data-preview-source]")).to_have_attribute(
                "data-preview-source", "proxy"
            )
            expect(page.locator("[data-preview-clock-reason]")).to_have_count(0)
            assert _video_query(page, ".viewer video").get("proxy") == "1"
            assert not errors, errors
        finally:
            browser.close()
