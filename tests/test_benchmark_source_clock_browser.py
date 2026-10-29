"""Real synthetic source clocks through both builders and a local Chromium.

Each clip is generated on the spot with the project FFmpeg and carries a machine-readable
frame-index barcode (ten binary patches plus a grey sync patch), so a screenshot of the real
player proves which canonical source moment is on screen instead of trusting `currentTime`
against itself. The pages are produced by the production builders; the browser observations
are development evidence, never human acceptance. Nothing here uses user footage, a
database, model output, a network request or a paid API.
"""

import asyncio
import hashlib
import importlib.util
import json
import struct
import subprocess
import zlib
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest
from media_generator_clocks import generator_clock
from test_benchmark import document
from test_benchmark_preparation import plan_fixture
from test_material_tasks import CONFIG

from gamingcreator.application.benchmark import BenchmarkHit, parse_manifest, run_benchmark
from gamingcreator.application.benchmark_preparation import canonical_json, loads_plan
from gamingcreator.application.benchmark_reference_review import (
    RUNTIME_CLOCKS,
    build_reference_context,
    context_hash,
    validate_reference_record,
)
from gamingcreator.application.benchmark_review import build_review_context, validate_review
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.media import MediaAsset, floor_us
from gamingcreator.infrastructure.benchmark_review_files import publish_review_bundle
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.ui.benchmark_reference_review import render_reference_review
from gamingcreator.ui.benchmark_review import render_benchmark_review

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
FFPROBE = ROOT / ".tools/ffmpeg/bin/ffprobe.exe"
PREPARED_AT = "2026-10-23T10:00:00+08:00"
START_US, END_US = 300_000, 700_000
INSIDE_COVERAGE = (800_000, 1_200_000)
# The barcode geometry is shared by the clip synthesis and the screenshot decoder.
WIDTH, HEIGHT, FPS, SECONDS = 320, 180, 30, 2
BITS, PATCH, STEP = 10, 22, 30
BIT_ROW = (8, 30)
SYNC_ROW = (40, 62)
FRAME_US = 1_000_000 // FPS
# Explicit tolerances for the playback evidence: the seek is deterministic, `play` may
# trail it slightly, the stop must stay far below the clip end, and the decoded frame is
# allowed to be one frame either side of the measured position.
SEEK_TOLERANCE = 0.02
START_TOLERANCE = 0.1
PAUSE_SLACK = 0.5
CONTENT_TOLERANCE_US = FRAME_US + 5_000
# A playing pipeline can present a few frames ahead of `currentTime`; only the stop instant
# itself is checked with this window, while explicit seeks use the one-frame tolerance.
PAUSE_CONTENT_TOLERANCE_US = 4 * FRAME_US + 5_000
SUPPORTED = ("zero", "nonzero", "audio_late")
ALL_KINDS = ("zero", "nonzero", "audio_late", "video_late", "extra_track")
# Matroska/WebM enter the same automatic path since TD002 (packet-timestamp durations).
# Chromium maps these exactly; the refused ones below must fall back to manual entry.
AUTOMATIC = (
    *((kind, "mp4") for kind in SUPPORTED),
    ("zero", "mkv"),
    ("zero", "webm"),
    ("audio_late", "webm"),
)
REFUSED = {
    ("nonzero", "mkv"): "时长与保存的原片时长不一致",
    ("nonzero", "webm"): "时长与保存的原片时长不一致",
    ("audio_late", "mkv"): "起点与保存的原片起点不一致",
}


def _reference_script():
    spec = importlib.util.spec_from_file_location(
        "source_clock_reference_script", ROOT / "scripts/prepare-benchmark-references.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REFERENCE_SCRIPT = _reference_script()


@dataclass(frozen=True)
class ClockCase:
    kind: str
    asset: MediaAsset
    frame_sources: tuple[int, ...]
    candidate: tuple[dict[str, object], dict[str, object]]
    reference: tuple[dict[str, object], dict[str, object]]
    reference_assets: dict[str, MediaAsset]
    candidate_page: Path
    reference_page: Path


def marker_expression() -> str:
    return (
        "if(between(Y,8,29)*lt(mod(X-8,30),22)*lt(floor((X-8)/30),10),"
        "255*gt(mod(floor(N/pow(2,floor((X-8)/30))),2),0.5),"
        "if(between(Y,40,61)*lt(X,30),128,48))"
    )


def synthesize(path: Path, kind: str) -> None:
    """A 2 s 30 fps clip whose frame index is readable from a screenshot."""
    assert FFMPEG.is_file(), "Project-local FFmpeg is required for source-clock fixtures."
    video_source = f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}:d={SECONDS}"
    audio_source = f"sine=frequency=440:sample_rate=48000:duration={SECONDS}"
    command = [str(FFMPEG), "-hide_banner", "-nostdin", "-y", "-v", "error"]
    if kind == "video_late":
        command += ["-itsoffset", "0.5"]
    command += ["-f", "lavfi", "-i", video_source]
    if kind == "audio_late":
        command += ["-itsoffset", "0.5"]
    command += ["-f", "lavfi", "-i", audio_source]
    mapping = ["-map", "0:v", "-map", "1:a"]
    if kind == "extra_track":
        # A second, longer audio track: the container duration no longer matches the two
        # streams the project probes, so the browser chronology must be refused.
        command += ["-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=3"]
        mapping += ["-map", "2:a"]
    if kind == "nonzero":
        command += ["-output_ts_offset", "2.5"]
    # OBS-style .mkv keeps H.264/AAC; WebM only allows VP8/VP9/AV1 with Opus/Vorbis.
    video_codec, audio_codec = (
        ("libvpx-vp9", "libopus")
        if path.suffix == ".webm"
        else (
            "libx264",
            "aac",
        )
    )
    command += [
        *mapping,
        "-vf",
        f"format=gray,geq=lum='{marker_expression()}',format=yuv420p",
        "-c:v",
        video_codec,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        audio_codec,
    ]
    if kind != "extra_track":
        command += ["-shortest"]
    command += [str(path)]
    subprocess.run(
        command, check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
    )


def probe_source(path: Path) -> MediaAsset:
    return asyncio.run(
        FfmpegMediaProcessor(ROOT).probe(path, CancellationContext("source-clock", 60))
    )


def video_frame_sources(path: Path, asset: MediaAsset) -> tuple[int, ...]:
    """Canonical source µs of every presented video frame, straight from ffprobe."""
    video = next(stream for stream in asset.streams if stream.kind == "video")
    output = subprocess.run(
        [
            str(FFPROBE),
            "-v",
            "error",
            "-select_streams",
            str(video.index),
            "-show_entries",
            "frame=pts_time",
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    moments = sorted(
        Fraction(line.strip().strip(","))
        for line in output.stdout.decode().splitlines()
        if line.strip().strip(",")
    )
    assert moments, "the fixture must contain decoded video frames"
    return tuple(floor_us(moment - asset.origin_seconds) for moment in moments)


def candidate_review(
    asset: MediaAsset, ranges: tuple[tuple[int, int], ...] = ((START_US, END_US),)
) -> tuple[dict[str, object], dict[str, object]]:
    raw = document()
    raw["queries"][0]["candidateLabels"] = []
    raw["media"] = [
        {
            "mediaId": asset.media_id,
            "runId": "run-1",
            "sha256": asset.sha256,
            "durationUs": asset.duration_us,
        }
    ]
    raw["queries"][0].update({"mediaId": asset.media_id, "runId": "run-1"})
    run = StoredRun("run-1", asset, CONFIG, "f" * 64, RunStatus.COMPLETED, None)
    timeline = StoredTimeline(run, (), (), (), (), ())
    identifiers = tuple(f"event-{index}" for index in range(len(ranges)))
    hits = tuple(
        BenchmarkHit(identifier, start, end, position)
        for position, (identifier, (start, end)) in enumerate(
            zip(identifiers, ranges, strict=True), 1
        )
    )
    metadata = {
        "runs": [
            {
                "runId": run.run_id,
                "pipelineVersion": run.configuration.pipeline_version,
                "configHash": run.config_hash,
            }
        ],
        "retrievalVersion": "synthetic-source-clock-v1",
        "retrievalMode": "lexical",
    }

    async def search(query):
        return hits

    async def verify(media):
        return None

    report = asyncio.run(
        run_benchmark(parse_manifest(raw), search, verify_media=verify, runner_metadata=metadata)
    )
    report["queries"][0]["retrievalId"] = "retrieval-1"
    stored_hits = [
        {
            "rank": position,
            "candidate_id": f"candidate-{position - 1}",
            "event_id": identifier,
            "start_us": start,
            "end_us": end,
            "evidence_ids": ["synthetic-source-clock:image"],
        }
        for position, (identifier, (start, end)) in enumerate(
            zip(identifiers, ranges, strict=True), 1
        )
    ]
    candidates = [
        {
            "rank": row["rank"],
            "candidateId": row["candidate_id"],
            "eventId": row["event_id"],
            "mediaId": asset.media_id,
            "startUs": row["start_us"],
            "endUs": row["end_us"],
            "evidenceIds": row["evidence_ids"],
            "observableFacts": ["synthetic clock fixture fact"],
        }
        for row in stored_hits
    ]
    retrievals = {
        "retrieval-1": {
            "retrievalId": "retrieval-1",
            "runId": "run-1",
            "mediaId": asset.media_id,
            "query": raw["queries"][0]["text"],
            "retrievalVersion": "synthetic-source-clock-v1",
            "parameters": {"mode": "lexical", "topK": 10},
            "hits": stored_hits,
            "result": {"candidates": candidates},
        }
    }
    return build_review_context(
        raw,
        report,
        report_sha256=hashlib.sha256(json.dumps(report).encode()).hexdigest(),
        binding_sha256=hashlib.sha256(json.dumps(raw).encode()).hexdigest(),
        timelines={"run-1": timeline},
        retrievals=retrievals,
    )


def reference_review(
    assets: dict[str, MediaAsset], directory: Path
) -> tuple[dict[str, object], dict[str, object]]:
    raw, _ = plan_fixture(directory, count=len(assets))
    for index, identifier in enumerate(assets):
        raw["sources"][index]["path"] = str(assets[identifier].source_path)
    return build_reference_context(loads_plan(json.dumps(raw)), assets, PREPARED_AT)


def clock_case(
    tmp_path: Path,
    kind: str,
    *,
    ranges: tuple[tuple[int, int], ...] = ((START_US, END_US),),
    second_media: MediaAsset | None = None,
    container: str = "mp4",
) -> ClockCase:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / f"{kind} 源 空格.{container}"
    synthesize(source, kind)
    asset = probe_source(source)
    frames = video_frame_sources(source, asset)
    candidate = candidate_review(asset, ranges)
    assets = {"source-0": asset}
    if second_media is not None:
        assets["source-1"] = second_media
    reference = reference_review(assets, tmp_path)
    candidate_page = tmp_path / f"{kind}-candidate.html"
    candidate_page.write_text(render_benchmark_review(*candidate), encoding="utf-8")
    reference_page = tmp_path / f"{kind}-reference.html"
    reference_page.write_text(render_reference_review(*reference), encoding="utf-8")
    return ClockCase(
        kind, asset, frames, candidate, reference, assets, candidate_page, reference_page
    )


def decode_png(data: bytes) -> tuple[int, int, int, list[bytes]]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    cursor, idat, width, height, depth, color = 8, b"", 0, 0, 0, 0
    while cursor < len(data):
        length = struct.unpack(">I", data[cursor : cursor + 4])[0]
        kind = data[cursor + 4 : cursor + 8]
        body = data[cursor + 8 : cursor + 8 + length]
        cursor += 12 + length
        if kind == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
    assert depth == 8
    raw = zlib.decompress(idat)
    stride = width * channels
    rows: list[bytes] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset : offset + stride])
        offset += stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                line[index] = (line[index] + left) & 0xFF
            elif filter_type == 2:
                line[index] = (line[index] + up) & 0xFF
            elif filter_type == 3:
                line[index] = (line[index] + (left + up) // 2) & 0xFF
            elif filter_type == 4:
                estimate = left + up - upper_left
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
                line[index] = (line[index] + predictor) & 0xFF
            else:
                assert filter_type == 0
        rows.append(bytes(line))
        previous = line
    return width, height, channels, rows


def read_marker(png: bytes) -> tuple[int, int]:
    """Decode the frame-index barcode and check the grey sync patch.

    The element screenshot is mapped with the browser's default `object-fit: contain`
    letterboxing, so a one-pixel rounding difference in the player box cannot shift a patch.
    """
    width, height, channels, rows = decode_png(png)
    assert channels in (3, 4)
    scale = min(width / WIDTH, height / HEIGHT)
    assert 0.9 <= scale <= 1.5, f"unexpected player box {width}x{height}"
    offset_x = (width - WIDTH * scale) / 2
    offset_y = (height - HEIGHT * scale) / 2

    def level(x: int, y: int) -> int:
        px = min(width - 1, max(0, round(offset_x + x * scale)))
        py = min(height - 1, max(0, round(offset_y + y * scale)))
        start = px * channels
        return (rows[py][start] + rows[py][start + 1] + rows[py][start + 2]) // 3

    index = 0
    levels = []
    for bit in range(BITS):
        value = level(8 + STEP * bit + PATCH // 2, (BIT_ROW[0] + BIT_ROW[1]) // 2)
        levels.append(value)
        if value >= 128:
            index |= 1 << bit
        else:
            assert value <= 110, f"ambiguous marker patch {bit}: {levels}"
    sync = level(19, (SYNC_ROW[0] + SYNC_ROW[1]) // 2)
    return index, sync


def open_page(browser, path: Path):
    page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    requests, errors = [], []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url)
            if not request.url.startswith(("file:", "data:", "blob:"))
            else None
        ),
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(path.as_uri())
    return page, requests, errors


def normalize_player(page) -> None:
    """Fix the player box to the clip size so a screenshot can be decoded pixel by pixel."""
    page.evaluate(
        """() => {
            const video = document.getElementById('source-video');
            video.controls = false;
            video.style.width = '320px';
            video.style.height = '180px';
            video.style.maxWidth = 'none';
            video.style.maxHeight = 'none';
        }"""
    )


def wait_clock_ready(page) -> None:
    try:
        page.wait_for_function(
            "() => { const button = document.querySelector('.slot button');"
            " return button !== null && !button.disabled; }",
            timeout=30000,
        )
    except Exception as error:  # noqa: BLE001 - report the page's own state on a timeout
        raise AssertionError(
            "automatic replay never became available: "
            f"clock={page.locator('#clock-state').inner_text()!r} "
            f"note={page.locator('[data-clock=note]').first.inner_text()!r}"
        ) from error


def wait_for_pause_at(page, end_player: float) -> None:
    try:
        page.wait_for_function(
            "end => { const video = document.getElementById('source-video');"
            " return video.paused && video.currentTime >= end; }",
            arg=end_player,
            timeout=30000,
        )
    except Exception as error:  # noqa: BLE001 - report playback state on a timeout
        state = page.evaluate(
            """() => { const video = document.getElementById('source-video');
                return {currentTime: video.currentTime, paused: video.paused, ended: video.ended,
                        readyState: video.readyState, error: video.error && video.error.code,
                        playState: document.getElementById('play-state').textContent}; }"""
        )
        raise AssertionError(f"interval replay did not stop at {end_player}: {state}") from error


def wait_capture_ready(page) -> None:
    page.wait_for_function(
        "() => !document.getElementById('capture-start').disabled", timeout=30000
    )


def wait_selected_media(page, asset: MediaAsset) -> None:
    """Wait until the visible player really shows the selected query's media."""
    page.wait_for_function(
        """url => {
            const video = document.getElementById('source-video');
            return video.currentSrc === url && video.readyState >= 1 && video.seekable.length > 0;
        }""",
        arg=asset.source_path.as_uri(),
        timeout=30000,
    )


def present_at(page, target: float) -> float:
    """Seek, wait for the presented frame and let the compositor settle.

    A media whose first seek has not resolved yet may advertise a header-only seekable range
    (a non-zero-PTS MP4 reported [0, 2.022] before the first seek), so a clamped target is
    retried once after a small warm-up seek, exactly as a user's first scrub would resolve it.
    """
    return page.evaluate(
        """async target => {
            const video = document.getElementById('source-video');
            const settle = value => new Promise(resolve => {
                if (Math.abs(video.currentTime - value) <= 1e-9) { resolve(video.currentTime); return; }
                const done = () => { video.removeEventListener('seeked', done); resolve(video.currentTime); };
                video.addEventListener('seeked', done);
                try { video.currentTime = value; } catch (error) { resolve(null); }
                setTimeout(() => { video.removeEventListener('seeked', done); resolve(video.currentTime); }, 5000);
            });
            const ranges = video.seekable;
            const knownEnd = ranges.length ? ranges.end(ranges.length - 1) : 0;
            if (target > knownEnd + 0.001) await settle(0.000001);
            let settled = await settle(target);
            if (settled === null || Math.abs(settled - target) > 0.002) settled = await settle(target);
            if (video.requestVideoFrameCallback) {
                await new Promise(resolve => {
                    let finished = false;
                    const finish = () => { if (finished) return; finished = true; resolve(); };
                    video.requestVideoFrameCallback(finish);
                    setTimeout(finish, 1500);
                });
            }
            await new Promise(resolve => setTimeout(resolve, 150));
            return settled;
        }""",
        target,
    )


def displayed_source(page, frame_sources: tuple[int, ...]) -> int:
    png = page.locator("#source-video").screenshot()
    index, sync = read_marker(png)
    assert 100 <= sync <= 150, f"grey sync patch was not readable: {sync}"
    assert index < len(frame_sources), f"decoded frame {index} outside the clip"
    return frame_sources[index]


def origin_us(asset: MediaAsset) -> int:
    return round(float(asset.origin_seconds) * 1_000_000)


def selected_media(context: dict[str, object]) -> dict[str, object]:
    return context["media"][0]  # type: ignore[return-value]


def reference_clock(context: dict[str, object], index: int = 0) -> dict[str, object]:
    """Runtime clock document of a reference context (kept outside the stored identity)."""
    media = context["media"][index]  # type: ignore[index]
    return context[RUNTIME_CLOCKS][media["id"]]  # type: ignore[index]


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_synthetic_probe_and_builders_expose_the_measured_clock(tmp_path, kind):
    case = clock_case(tmp_path, kind)
    asset = case.asset
    starts = {stream.kind: float(stream.start_seconds) for stream in asset.streams}
    assert asset.origin_seconds == min(stream.start_seconds for stream in asset.streams)
    # The delayed-video fixture loses the first 0.5 s to `-shortest`.
    assert len(case.frame_sources) == (45 if kind == "video_late" else 60)
    assert list(case.frame_sources) == sorted(case.frame_sources)
    review, _ = case.candidate
    reference, _ = case.reference
    row = selected_media(review)
    clock = row["sourceClock"]
    assert clock is not None and clock["schemaVersion"] == "browser-source-clock-v1"
    assert clock["originUs"] == origin_us(asset)
    assert clock["durationUs"] == asset.duration_us
    assert row["automaticPlaybackSupported"] is True
    # The reference page keeps its stored identity: no clock in the media row, the original
    # zero-origin flag unchanged, and the clock projected outside the hashed context.
    reference_row = reference["media"][0]  # type: ignore[index]
    assert "sourceClock" not in reference_row
    assert reference_clock(reference) == clock
    legacy_capture = asset.origin_seconds == 0 and all(
        stream.start_seconds == 0 for stream in asset.streams
    )
    assert reference_row["automaticTimeCapture"] is legacy_capture
    if kind == "zero":
        assert set(starts.values()) == {0.0}
        assert clock["originUs"] == 0
    elif kind == "nonzero":
        expected = generator_clock(FFMPEG)
        assert starts["video"] == expected.absolute_video_start_us / 1_000_000
        assert 2.477 < starts["audio"] < 2.479
        assert asset.duration_us == expected.duration_us
        assert clock["originUs"] == expected.origin_us
        assert clock["videoStartUs"] == expected.relative_video_start_us
    elif kind == "audio_late":
        assert starts["video"] == 0 and 0.4 < starts["audio"] < 0.6
        assert clock["videoStartUs"] == 0
        assert clock["audioStartUs"] >= 400_000
    elif kind == "video_late":
        assert 0.4 < starts["video"] < 0.6 and starts["audio"] == 0
        assert clock["videoStartUs"] >= 400_000
        assert asset.origin_seconds == 0
    else:  # extra_track: the probed span is 2 s, the container header says 3 s
        assert clock["durationUs"] == 2_000_000
        assert starts["video"] == 0 and starts["audio"] == 0


@pytest.mark.parametrize(("kind", "container"), AUTOMATIC)
def test_candidate_page_seeks_plays_and_pauses_inside_the_canonical_interval(
    tmp_path, kind, container
):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, kind, container=container)
    clock = selected_media(case.candidate[0])["sourceClock"]
    assert clock is not None
    start_player = (START_US + clock["originUs"]) / 1_000_000
    end_player = (END_US + clock["originUs"]) / 1_000_000
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            normalize_player(page)
            wait_clock_ready(page)
            playwright.expect(page.locator("#clock-state")).to_contain_text(
                "已把浏览器播放位置核对为规范源时间"
            )
            playwright.expect(page.locator("[data-clock=note]").first).to_have_text("")
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    window.clockEvents = [];
                    for (const name of ['seeking', 'seeked', 'play', 'playing', 'pause', 'ended']) {
                        video.addEventListener(name, () => window.clockEvents.push({
                            name, at: performance.now(), currentTime: video.currentTime, ended: video.ended,
                        }));
                    }
                }"""
            )
            page.locator(".slot button").first.click()
            wait_for_pause_at(page, end_player)
            playwright.expect(page.locator("#play-state")).to_contain_text("第1位")
            playwright.expect(page.locator("#play-state")).to_contain_text("规范源 0.300–0.700秒")
            assert (
                page.locator("#open-source").get_attribute("href")
                == case.asset.source_path.as_uri()
            )
            events = page.evaluate("() => window.clockEvents")
            names = [event["name"] for event in events]
            seeks = [event for event in events if event["name"] in ("seeking", "seeked")]
            plays = [event for event in events if event["name"] == "play"]
            pauses = [event for event in events if event["name"] == "pause"]
            assert seeks and plays and pauses
            assert "ended" not in names
            assert any(
                abs(event["currentTime"] - start_player) <= SEEK_TOLERANCE for event in seeks
            )
            assert abs(plays[0]["currentTime"] - start_player) <= START_TOLERANCE
            final_pause = pauses[-1]
            assert final_pause["at"] > max(event["at"] for event in seeks + plays)
            assert final_pause["ended"] is False
            assert (
                end_player - SEEK_TOLERANCE <= final_pause["currentTime"] < end_player + PAUSE_SLACK
            )
            measured = page.evaluate("() => document.getElementById('source-video').currentTime")
            # The frame on screen at the stop belongs to the measured player position. A
            # playing pipeline may present one to three frames ahead of `currentTime`, so the
            # pause-moment check uses a bounded window; the canonical corners are then read
            # after an explicit seek, where the presented frame is deterministic.
            paused_source = displayed_source(page, case.frame_sources)
            measured_source = floor_us(Fraction(measured) - case.asset.origin_seconds)
            expected_index = max(
                index for index, value in enumerate(case.frame_sources) if value <= measured_source
            )
            assert (
                abs(paused_source - case.frame_sources[expected_index])
                <= PAUSE_CONTENT_TOLERANCE_US
            )
            assert abs(paused_source - END_US) <= PAUSE_SLACK * 1_000_000
            # Seek back to the canonical interval start and read the picture there too.
            start_settled = present_at(page, start_player)
            assert abs(start_settled - start_player) <= SEEK_TOLERANCE
            assert (
                abs(displayed_source(page, case.frame_sources) - START_US) <= CONTENT_TOLERANCE_US
            )
            end_settled = present_at(page, end_player)
            assert abs(end_settled - end_player) <= SEEK_TOLERANCE
            assert abs(displayed_source(page, case.frame_sources) - END_US) <= CONTENT_TOLERANCE_US
            # A non-zero-PTS MP4 legitimately grows its duration after seeks; a repeated
            # automatic replay must keep working instead of silently degrading to manual.
            assert page.locator(".slot button").first.is_enabled()
            before = page.evaluate("() => window.clockEvents.length")
            page.locator(".slot button").first.click()
            page.wait_for_function(
                "start => window.clockEvents.slice(start).some(event => event.name === 'play')"
                " && window.clockEvents.slice(start).some(event => event.name === 'pause')"
                " && document.getElementById('source-video').paused",
                arg=before,
                timeout=30000,
            )
            assert page.evaluate("() => document.getElementById('source-video').currentTime") >= (
                end_player - SEEK_TOLERANCE
            )
            assert not page.evaluate("() => document.getElementById('source-video').ended")
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            blank = Path(pending.value.path()).read_bytes()
            assert json.loads(blank) == case.candidate[1]
            validate_review(blank, case.candidate[1], case.candidate[0])
            assert not requests and not errors
        finally:
            browser.close()


@pytest.mark.parametrize(("kind", "container"), AUTOMATIC)
def test_reference_page_capture_equals_the_picture_canonical_moment(tmp_path, kind, container):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, kind, container=container)
    clock = reference_clock(case.reference[0])
    assert clock is not None
    start_player = (START_US + clock["originUs"]) / 1_000_000
    end_player = (1_500_000 + clock["originUs"]) / 1_000_000
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.reference_page)
            normalize_player(page)
            wait_capture_ready(page)
            playwright.expect(page.locator("#clock-state")).to_contain_text(
                "已把浏览器播放位置换算为规范源时间"
            )
            assert page.locator("#open-source").is_hidden()
            settled = present_at(page, start_player)
            assert abs(settled - start_player) <= SEEK_TOLERANCE
            assert (
                abs(displayed_source(page, case.frame_sources) - START_US) <= CONTENT_TOLERANCE_US
            )
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.300000")
            # Non-zero-PTS metadata grows after this seek; the capability must stay, because
            # only a shrink is an unexpected change.
            playwright.expect(page.locator("#clock-state")).to_contain_text(
                "已把浏览器播放位置换算为规范源时间"
            )
            assert page.locator("#capture-start").is_enabled()
            assert page.locator("#capture-end").is_enabled()
            settled = present_at(page, end_player)
            assert abs(settled - end_player) <= SEEK_TOLERANCE
            assert (
                abs(displayed_source(page, case.frame_sources) - 1_500_000) <= CONTENT_TOLERANCE_US
            )
            page.locator("#capture-end").click()
            playwright.expect(page.locator("#end-seconds")).to_have_value("1.500000")
            page.locator("#event-id").fill("fixture-action")
            page.locator("#event-group").fill("fixture-same-action")
            page.locator("#reason").fill("Synthetic clock fixture, not human acceptance.")
            page.locator("#add-reference").click()
            playwright.expect(page.locator(".slot")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            saved = Path(pending.value.path()).read_bytes()
            record = validate_reference_record(saved, case.reference[0], case.reference_assets)
            events = record["plan"]["queries"][0]["referenceEvents"]
            assert events[0]["usableRanges"] == [{"startUs": 300_000, "endUs": 1_500_000}]
            assert not requests and not errors
        finally:
            browser.close()


@pytest.mark.parametrize(("kind", "container"), list(REFUSED))
def test_unverifiable_matroska_clock_falls_back_to_manual_on_both_pages(tmp_path, kind, container):
    """Where Chromium's Matroska timeline disagrees with the probe, nothing is mapped."""
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, kind, container=container)
    reason = REFUSED[(kind, container)]
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent.includes('无法核对')",
                timeout=30000,
            )
            assert page.locator(".slot button").first.is_disabled()
            playwright.expect(page.locator("[data-clock=note]").first).to_contain_text(reason)
            assert (
                page.locator("#open-source").get_attribute("href")
                == case.asset.source_path.as_uri()
            )
            page.close()
            page, requests, errors = open_page(browser, case.reference_page)
            page.wait_for_function(
                "reason => document.getElementById('clock-state').textContent.includes(reason)",
                arg=reason,
                timeout=30000,
            )
            assert page.locator("#capture-start").is_disabled()
            assert page.locator("#capture-end").is_disabled()
            playwright.expect(page.locator("#open-source")).to_be_visible()
            assert not requests and not errors
        finally:
            browser.close()


def test_video_late_replays_only_picture_intervals_and_refuses_head_capture(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path / "outside", "video_late", ranges=((START_US, END_US),))
    inside = clock_case(tmp_path / "inside", "video_late", ranges=(INSIDE_COVERAGE,))
    clock = selected_media(case.candidate[0])["sourceClock"]
    assert clock is not None and clock["videoStartUs"] >= 400_000
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            wait_clock_ready_text = "() => document.getElementById('clock-state').textContent.includes('已把浏览器播放位置核对')"
            page.wait_for_function(wait_clock_ready_text, timeout=30000)
            button = page.locator(".slot button").first
            assert button.is_disabled()
            playwright.expect(page.locator("[data-clock=note]").first).to_contain_text(
                "超出原片有画面的部分"
            )
            playwright.expect(page.locator("#open-source")).to_be_visible()
            assert (
                page.locator("#open-source").get_attribute("href")
                == case.asset.source_path.as_uri()
            )
            assert page.evaluate("() => document.getElementById('source-video').currentSrc") == ""
            # The same media with an interval inside the picture range replays normally.
            page.close()
            page, requests, errors = open_page(browser, inside.candidate_page)
            normalize_player(page)
            wait_clock_ready(page)
            page.locator(".slot button").first.click()
            inside_clock = selected_media(inside.candidate[0])["sourceClock"]
            assert inside_clock is not None
            end_player = (INSIDE_COVERAGE[1] + inside_clock["originUs"]) / 1_000_000
            wait_for_pause_at(page, end_player)
            measured = page.evaluate("() => document.getElementById('source-video').currentTime")
            measured_source = floor_us(Fraction(measured) - inside.asset.origin_seconds)
            expected_index = max(
                index
                for index, value in enumerate(inside.frame_sources)
                if value <= measured_source
            )
            assert (
                abs(
                    displayed_source(page, inside.frame_sources)
                    - inside.frame_sources[expected_index]
                )
                <= PAUSE_CONTENT_TOLERANCE_US
            )
            page.close()
            # The reference page may still capture inside the picture range.
            page, requests, errors = open_page(browser, case.reference_page)
            normalize_player(page)
            wait_capture_ready(page)
            playwright.expect(page.locator("#clock-state")).to_contain_text("没有画面")
            assert abs(present_at(page, 0.2) - 0.2) <= SEEK_TOLERANCE
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#status")).to_contain_text("没有可核对的原片画面")
            playwright.expect(page.locator("#start-seconds")).to_have_value("")
            assert abs(present_at(page, 1.2) - 1.2) <= SEEK_TOLERANCE
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("1.200000")
            assert not requests and not errors
        finally:
            browser.close()


def test_contradictory_container_duration_keeps_manual_path_and_local_link(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "extra_track")
    clock = selected_media(case.candidate[0])["sourceClock"]
    assert clock is not None and clock["durationUs"] == 2_000_000
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent.includes('无法核对')",
                timeout=30000,
            )
            playwright.expect(page.locator("#clock-state")).to_contain_text("无法核对为规范源时间")
            assert page.locator(".slot button").first.is_disabled()
            playwright.expect(page.locator("[data-clock=note]").first).to_contain_text(
                "时长与保存的原片时长不一致"
            )
            playwright.expect(page.locator("#open-source")).to_be_visible()
            assert (
                page.locator("#open-source").get_attribute("href")
                == case.asset.source_path.as_uri()
            )
            assert page.evaluate("() => document.getElementById('source-video').currentSrc") == ""
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            blank = Path(pending.value.path()).read_bytes()
            assert json.loads(blank) == case.candidate[1]
            validate_review(blank, case.candidate[1], case.candidate[0])
            page.close()
            page, requests, errors = open_page(browser, case.reference_page)
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent.includes('时长与保存的原片时长不一致')",
                timeout=30000,
            )
            assert page.locator("#capture-start").is_disabled()
            playwright.expect(page.locator("#open-source")).to_be_visible()
            # Manual canonical source entry still goes through the formal validation.
            page.locator("#start-seconds").fill("0.250000")
            page.locator("#end-seconds").fill("1.000000")
            page.locator("#event-id").fill("fixture-action")
            page.locator("#event-group").fill("fixture-same-action")
            page.locator("#reason").fill("Synthetic clock fixture, not human acceptance.")
            page.locator("#add-reference").click()
            playwright.expect(page.locator(".slot")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            saved = Path(pending.value.path()).read_bytes()
            record = validate_reference_record(saved, case.reference[0], case.reference_assets)
            assert record["plan"]["queries"][0]["referenceEvents"][0]["usableRanges"] == [
                {"startUs": 250_000, "endUs": 1_000_000}
            ]
            assert not requests and not errors
        finally:
            browser.close()


def test_missing_media_keeps_manual_path_and_local_link(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    case.asset.source_path.unlink()
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent.includes('无法核对')",
                timeout=30000,
            )
            assert page.locator(".slot button").first.is_disabled()
            playwright.expect(page.locator("[data-clock=note]").first).to_contain_text(
                "浏览器不能读取这段原片"
            )
            playwright.expect(page.locator("#open-source")).to_be_visible()
            assert page.evaluate("() => document.getElementById('source-video').currentSrc") == ""
            page.close()
            page, requests, errors = open_page(browser, case.reference_page)
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent.includes('浏览器不能读取这段原片')",
                timeout=30000,
            )
            assert page.locator("#capture-start").is_disabled()
            playwright.expect(page.locator("#open-source")).to_be_visible()
            page.locator("#start-seconds").fill("0.250000")
            page.locator("#end-seconds").fill("1.000000")
            page.locator("#event-id").fill("fixture-action")
            page.locator("#event-group").fill("fixture-same-action")
            page.locator("#reason").fill("Synthetic clock fixture, not human acceptance.")
            page.locator("#add-reference").click()
            playwright.expect(page.locator(".slot")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            saved = Path(pending.value.path()).read_bytes()
            record = validate_reference_record(saved, case.reference[0], case.reference_assets)
            assert record["plan"]["queries"][0]["referenceEvents"][0]["usableRanges"] == [
                {"startUs": 250_000, "endUs": 1_000_000}
            ]
            assert not requests and not errors
        finally:
            browser.close()


def test_rapid_interval_and_media_switches_never_apply_stale_clock(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    ranges = ((START_US, END_US), INSIDE_COVERAGE)
    case = clock_case(tmp_path / "candidate", "zero", ranges=ranges)
    other = probe_media(tmp_path / "other", "zero")
    reference = clock_case(tmp_path / "reference", "nonzero", ranges=ranges, second_media=other)
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            # One media, two intervals: the later click must own the player.
            page, requests, errors = open_page(browser, case.candidate_page)
            normalize_player(page)
            wait_clock_ready(page)
            buttons = page.locator(".slot button")
            buttons.nth(0).click()
            buttons.nth(1).click()
            clock = selected_media(case.candidate[0])["sourceClock"]
            assert clock is not None
            end_player = (INSIDE_COVERAGE[1] + clock["originUs"]) / 1_000_000
            wait_for_pause_at(page, end_player)
            playwright.expect(page.locator("#play-state")).to_contain_text("第2位")
            measured = page.evaluate("() => document.getElementById('source-video').currentTime")
            assert end_player - SEEK_TOLERANCE <= measured < end_player + PAUSE_SLACK
            assert not page.evaluate("() => document.getElementById('source-video').ended")
            measured_source = floor_us(Fraction(measured) - case.asset.origin_seconds)
            expected_index = max(
                index for index, value in enumerate(case.frame_sources) if value <= measured_source
            )
            assert (
                abs(displayed_source(page, case.frame_sources) - case.frame_sources[expected_index])
                <= PAUSE_CONTENT_TOLERANCE_US
            )
            page.close()
            # Two different media: the selected query's clock must be the one used.
            page, requests, errors = open_page(browser, reference.reference_page)
            normalize_player(page)
            page.locator("#query-select").select_option("1")
            page.locator("#query-select").select_option("0")
            first = reference_clock(reference.reference[0], 0)
            second = reference_clock(reference.reference[0], 1)
            assert first is not None and second is not None
            wait_selected_media(page, reference.asset)
            wait_capture_ready(page)
            playwright.expect(page.locator("#clock-state")).to_contain_text(
                f"原片开头 {generator_clock(FFMPEG).head_hint_seconds} 秒没有画面"
            )
            settled = present_at(page, (START_US + first["originUs"]) / 1_000_000)
            assert abs(settled - (START_US + first["originUs"]) / 1_000_000) <= SEEK_TOLERANCE
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.300000")
            page.locator("#query-select").select_option("1")
            other_asset = reference.reference_assets["source-1"]
            wait_selected_media(page, other_asset)
            wait_capture_ready(page)
            playwright.expect(page.locator("#clock-state")).to_contain_text("可用“用当前位置标记”")
            settled = present_at(page, (1_000_000 + second["originUs"]) / 1_000_000)
            assert abs(settled - (1_000_000 + second["originUs"]) / 1_000_000) <= SEEK_TOLERANCE
            page.locator("#capture-end").click()
            playwright.expect(page.locator("#end-seconds")).to_have_value("1.000000")
            assert not requests and not errors
        finally:
            browser.close()


def probe_media(directory: Path, kind: str) -> MediaAsset:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{kind} 源 空格.mp4"
    synthesize(path, kind)
    return probe_source(path)


def stored_identity(context):
    return {key: value for key, value in context.items() if key != RUNTIME_CLOCKS}


def test_legacy_reference_package_filled_record_and_new_page_keep_identity(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path / "case", "zero")
    context, template = case.reference
    identity = stored_identity(context)
    assert context_hash(identity) == template["contextSha256"]
    assert "sourceClock" not in identity["media"][0]
    assert identity["media"][0]["automaticTimeCapture"] is True

    filled = json.loads(json.dumps(template))
    filled["plan"]["queries"][0]["referenceEvents"] = [
        {
            "humanEventId": "legacy-action",
            "independenceGroup": "legacy-group",
            "usableRanges": [{"startUs": 250_000, "endUs": 750_000}],
            "reason": "Legacy filled reference; not human acceptance.",
        }
    ]
    filled["plan"]["labelVersion"] = "legacy-reference-v1"
    filled["plan"]["humanReferences"] = {
        "confirmed": True,
        "annotators": ["legacy-annotator"],
        "reviewed": True,
    }
    filled_bytes = canonical_json(filled)
    record_path = tmp_path / "旧记录.json"
    record_path.write_bytes(filled_bytes)
    package = tmp_path / "旧标注包"
    publish_review_bundle(
        package,
        {
            "plan-input.json": canonical_json(identity["plan"]),
            "context.json": canonical_json(identity),
            "record-template.json": canonical_json(template),
            "review.html": b"legacy review page bytes",
        },
        [],
    )
    # Production CLI validates the unchanged legacy package and record bytes.
    output = tmp_path / "导入计划"
    arguments = [
        "--review-directory",
        str(package),
        "--record",
        str(record_path),
        "--output",
        str(output),
    ]
    assert REFERENCE_SCRIPT.main(arguments) == 0
    assert (output / "context.json").read_bytes() == (package / "context.json").read_bytes()
    assert (output / "record-input.json").read_bytes() == filled_bytes
    assert (output / "reference-record.json").read_bytes() == filled_bytes
    assert (output / "benchmark-plan.json").read_bytes() == canonical_json(filled["plan"])
    # The new page renders the same legacy context/template bytes and accepts the same record.
    page_path = tmp_path / "旧标注页.html"
    page_path.write_text(render_reference_review(identity, template), encoding="utf-8")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, page_path)
            normalize_player(page)
            # A legacy zero-origin media keeps its automatic capture through runtime confirmation.
            wait_capture_ready(page)
            page.locator("#load-record").set_input_files(
                {"name": "legacy.json", "mimeType": "application/json", "buffer": filled_bytes}
            )
            playwright.expect(page.locator("#status")).to_contain_text("已有标注已载入")
            playwright.expect(page.locator("#label-version")).to_have_value("legacy-reference-v1")
            playwright.expect(page.locator("#annotators")).to_have_value("legacy-annotator")
            assert page.locator("#confirmed").is_checked()
            assert page.locator("#reviewed").is_checked()
            playwright.expect(page.locator(".slot")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            downloaded = Path(pending.value.path()).read_bytes()
            assert json.loads(downloaded) == filled
            validate_reference_record(downloaded, identity, case.reference_assets)
            # An unfilled template stays unfilled after load and download.
            page.locator("#load-record").set_input_files(
                {
                    "name": "blank.json",
                    "mimeType": "application/json",
                    "buffer": canonical_json(template),
                }
            )
            playwright.expect(page.locator("#status")).to_contain_text("已有标注已载入")
            assert not page.locator("#confirmed").is_checked()
            assert not page.locator("#reviewed").is_checked()
            playwright.expect(page.locator("#label-version")).to_have_value("")
            playwright.expect(page.locator("#annotators")).to_have_value("")
            playwright.expect(page.locator(".slot")).to_have_count(0)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            assert json.loads(Path(pending.value.path()).read_bytes()) == template
            present_at(page, 0.25)
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.250000")
            assert not requests and not errors
        finally:
            browser.close()


def test_legacy_special_clock_package_stays_manual(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path / "case", "nonzero")
    context, template = case.reference
    identity = stored_identity(context)
    assert context_hash(identity) == template["contextSha256"]
    assert identity["media"][0]["automaticTimeCapture"] is False
    page_path = tmp_path / "旧特殊时钟.html"
    page_path.write_text(render_reference_review(identity, template), encoding="utf-8")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, page_path)
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent.includes('没有可核对的浏览器时钟')",
                timeout=30000,
            )
            assert page.locator("#capture-start").is_disabled()
            playwright.expect(page.locator("#open-source")).to_be_visible()
            page.locator("#start-seconds").fill("0.250000")
            page.locator("#end-seconds").fill("1.000000")
            page.locator("#event-id").fill("legacy-manual-action")
            page.locator("#event-group").fill("legacy-manual-group")
            page.locator("#reason").fill("Legacy manual reference; not human acceptance.")
            page.locator("#add-reference").click()
            playwright.expect(page.locator(".slot")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            record = validate_reference_record(
                Path(pending.value.path()).read_bytes(), identity, case.reference_assets
            )
            assert record["plan"]["queries"][0]["referenceEvents"][0]["usableRanges"] == [
                {"startUs": 250_000, "endUs": 1_000_000}
            ]
            assert not requests and not errors
        finally:
            browser.close()


def test_settle_fails_closed_and_observe_rejects_incomplete_seek(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            normalize_player(page)
            wait_clock_ready(page)
            normal = page.evaluate(
                """async () => {
                    const video = document.getElementById('source-video');
                    await SourceClock.prepare(video, source.context.media[0].videoUrl);
                    return SourceClock.settle(video, 0.5);
                }"""
            )
            assert abs(normal - 0.5) <= SEEK_TOLERANCE
            # Controlled fault: the browser moves but never reports `seeked`. The observation
            # must fail closed instead of reporting the position that was just assigned.
            missing = page.evaluate(
                """async () => {
                    const video = document.getElementById('source-video');
                    window.blockSeeked = event => event.stopImmediatePropagation();
                    video.addEventListener('seeked', window.blockSeeked, true);
                    const value = await SourceClock.settle(video, 1.0);
                    return {value, currentTime: video.currentTime};
                }"""
            )
            assert missing["value"] is None
            assert abs(missing["currentTime"] - 1.0) <= SEEK_TOLERANCE
            # Controlled fault: the element claims to be seeking while already at the target.
            # The same-value shortcut must not return a stale position.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'seeking', {configurable: true, get: () => true});
                }"""
            )
            same_target = page.evaluate(
                """async () => {
                    const video = document.getElementById('source-video');
                    const value = await SourceClock.settle(video, video.currentTime);
                    delete video.seeking;
                    return value;
                }"""
            )
            assert same_target is None
            # The observation rejects a middle seek that never completed.
            observed = page.evaluate(
                """async () => {
                    const probe = document.createElement('video');
                    probe.preload = 'metadata'; probe.muted = true;
                    await SourceClock.prepare(probe, source.context.media[0].videoUrl);
                    const descriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime');
                    let assignments = 0;
                    Object.defineProperty(probe, 'currentTime', {
                        configurable: true,
                        get() { return descriptor.get.call(probe); },
                        set(value) {
                            assignments += 1;
                            if (assignments === 2) return; // drop the intermediate seek
                            descriptor.set.call(probe, value);
                        },
                    });
                    const clock = SourceClock.clockCandidates(source.context.media[0])[0];
                    const observation = await SourceClock.observe(probe);
                    const verdict = SourceClock.validate(clock, observation);
                    probe.removeAttribute('src'); probe.load();
                    return {middle: observation.middleSeconds, established: verdict.established,
                            reason: verdict.reason};
                }"""
            )
            assert observed["middle"] is None
            assert observed["established"] is False
            assert observed["reason"] == "seek_incomplete"
            assert not requests and not errors
        finally:
            browser.close()


def test_reference_capture_refuses_seeking_or_unready_player(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.reference_page)
            normalize_player(page)
            wait_capture_ready(page)
            present_at(page, 0.5)
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'seeking', {configurable: true, get: () => true});
                }"""
            )
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#status")).to_contain_text("仍在定位原片")
            playwright.expect(page.locator("#start-seconds")).to_have_value("")
            page.evaluate("() => { delete document.getElementById('source-video').seeking; }")
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.500000")
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'readyState', {configurable: true, get: () => 1});
                }"""
            )
            page.locator("#capture-end").click()
            playwright.expect(page.locator("#status")).to_contain_text("仍在定位原片")
            playwright.expect(page.locator("#end-seconds")).to_have_value("")
            page.evaluate("() => { delete document.getElementById('source-video').readyState; }")
            page.locator("#capture-end").click()
            playwright.expect(page.locator("#end-seconds")).to_have_value("0.500000")
            assert not requests and not errors
        finally:
            browser.close()


def test_reference_visible_metadata_contradiction_is_not_overridden_by_probe(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    init_script = """(() => {
        const duration = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'duration');
        Object.defineProperty(HTMLMediaElement.prototype, 'duration', {
            configurable: true,
            get() {
                const value = duration.get.call(this);
                return this.id === 'source-video' && Number.isFinite(value) ? value + 1 : value;
            },
        });
        const load = HTMLMediaElement.prototype.load;
        HTMLMediaElement.prototype.load = function() {
            if (!this.isConnected) { setTimeout(() => load.call(this), 600); } else { load.call(this); }
        };
    })();"""
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            errors, requests = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: (
                    requests.append(item.url)
                    if not item.url.startswith(("file:", "data:", "blob:"))
                    else None
                ),
            )
            page.add_init_script(script=init_script)
            page.goto(case.reference_page.as_uri())
            # The visible metadata arrives first and says 3 s; the probe that finishes later
            # proves the resource is 2 s. The contradiction must decide, not the late probe.
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent"
                ".includes('时长与保存的原片时长不一致')",
                timeout=30000,
            )
            assert page.locator("#capture-start").is_disabled()
            playwright.expect(page.locator("#open-source")).to_be_visible()
            playwright.expect(page.locator("#clock-state")).to_contain_text("请手填规范源时间")
            page.locator("#start-seconds").fill("0.250000")
            page.locator("#end-seconds").fill("1.000000")
            page.locator("#event-id").fill("fault-action")
            page.locator("#event-group").fill("fault-group")
            page.locator("#reason").fill("Controlled browser fault fixture, not human acceptance.")
            page.locator("#add-reference").click()
            playwright.expect(page.locator(".slot")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            validate_reference_record(
                Path(pending.value.path()).read_bytes(), case.reference[0], case.reference_assets
            )
            assert not requests and not errors
            # Contrast: without the fault the same page establishes the mapping.
            normal = browser.new_page()
            normal.goto(case.reference_page.as_uri())
            normal.wait_for_function(
                "() => !document.getElementById('capture-start').disabled", timeout=30000
            )
            normal.close()
        finally:
            browser.close()


def test_reference_visible_axis_mismatch_revokes_mapping(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    uri = case.asset.source_path.as_uri()
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.reference_page)
            normalize_player(page)
            wait_capture_ready(page)
            # Controlled fault: while the player still looks untouched (0), the element reports
            # 0.5 once the axis probe seeks; the visible-element axis check must revoke.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    const descriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime');
                    let moved = false;
                    Object.defineProperty(video, 'currentTime', {
                        configurable: true,
                        get: () => (moved ? 0.5 : 0),
                        set: (value) => { moved = true; descriptor.set.call(video, value); },
                    });
                    video.removeAttribute('src'); video.load();
                }"""
            )
            page.evaluate("url => { document.getElementById('source-video').src = url; }", uri)
            page.wait_for_function(
                "() => document.getElementById('capture-start').disabled"
                " && document.getElementById('clock-state').textContent"
                ".includes('播放起点与保存的原片起点不一致')",
                timeout=30000,
            )
            playwright.expect(page.locator("#open-source")).to_be_visible()
            # Removing the fault and reloading re-establishes the automatic capability.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    delete video.currentTime;
                    video.removeAttribute('src'); video.load();
                }"""
            )
            page.evaluate("url => { document.getElementById('source-video').src = url; }", uri)
            wait_capture_ready(page)
            present_at(page, 0.5)
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.500000")
            assert not requests and not errors
        finally:
            browser.close()


def test_reference_reload_and_duration_shrink_revoke_and_restore(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    uri = case.asset.source_path.as_uri()
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.reference_page)
            normalize_player(page)
            wait_capture_ready(page)
            present_at(page, 0.25)
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.250000")
            # An emptied player revokes the capability but keeps manual entry and the link.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    video.removeAttribute('src'); video.load();
                }"""
            )
            page.wait_for_function("() => document.getElementById('capture-start').disabled")
            playwright.expect(page.locator("#open-source")).to_be_visible()
            page.evaluate("url => { document.getElementById('source-video').src = url; }", uri)
            wait_capture_ready(page)
            present_at(page, 0.5)
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.500000")
            # An unexpected duration shrink revokes and re-establishes fail-closed.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'duration', {configurable: true, get: () => 1.0});
                    video.dispatchEvent(new Event('durationchange'));
                }"""
            )
            page.wait_for_function("() => document.getElementById('capture-start').disabled")
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    delete video.duration;
                    video.removeAttribute('src'); video.load();
                }"""
            )
            page.evaluate("url => { document.getElementById('source-video').src = url; }", uri)
            wait_capture_ready(page)
            present_at(page, 0.5)
            page.locator("#capture-end").click()
            playwright.expect(page.locator("#end-seconds")).to_have_value("0.500000")
            assert not requests and not errors
        finally:
            browser.close()


def test_candidate_revalidates_reloaded_generation_and_rejects_duration_shrink(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    clock = selected_media(case.candidate[0])["sourceClock"]
    assert clock is not None
    end_player = (END_US + clock["originUs"]) / 1_000_000
    uri = case.asset.source_path.as_uri()
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            normalize_player(page)
            wait_clock_ready(page)
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    window.clockEvents = [];
                    for (const name of ['play', 'pause', 'ended']) {
                        video.addEventListener(name, () => window.clockEvents.push({name, at: performance.now()}));
                    }
                }"""
            )
            page.locator(".slot button").first.click()
            wait_for_pause_at(page, end_player)
            plays_before = page.evaluate(
                "() => window.clockEvents.filter(event => event.name === 'play').length"
            )
            # Same URL, new load generation, but `seeked` never reports: the replay must be
            # revalidated and refused, not served from a permanent URL-keyed mapping.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    window.blockSeeked = event => event.stopImmediatePropagation();
                    video.addEventListener('seeked', window.blockSeeked, true);
                    video.load();
                }"""
            )
            page.locator(".slot button").first.click()
            playwright.expect(page.locator("#play-state")).to_contain_text("播放起点")
            assert (
                page.evaluate(
                    "() => window.clockEvents.filter(event => event.name === 'play').length"
                )
                == plays_before
            )
            assert page.evaluate("() => document.getElementById('source-video').paused")
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    video.removeEventListener('seeked', window.blockSeeked, true);
                }"""
            )
            mark = page.evaluate("() => window.clockEvents.length")
            page.locator(".slot button").first.click()
            page.wait_for_function(
                "start => window.clockEvents.slice(start).some(event => event.name === 'pause')"
                " && document.getElementById('source-video').paused",
                arg=mark,
                timeout=30000,
            )
            assert page.evaluate("() => document.getElementById('source-video').currentTime") >= (
                end_player - SEEK_TOLERANCE
            )
            # A declared duration shrink invalidates the generation and fails closed.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'duration', {configurable: true, get: () => 1.0});
                    video.dispatchEvent(new Event('durationchange'));
                }"""
            )
            page.locator(".slot button").first.click()
            playwright.expect(page.locator("#play-state")).to_contain_text("原片时长发生了意外变化")
            # Restore the element; a new generation is validated and plays again.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    delete video.duration;
                    video.removeAttribute('src'); video.load();
                }"""
            )
            page.evaluate("url => { document.getElementById('source-video').src = url; }", uri)
            mark = page.evaluate("() => window.clockEvents.length")
            page.locator(".slot button").first.click()
            page.wait_for_function(
                "start => window.clockEvents.slice(start).some(event => event.name === 'pause')"
                " && document.getElementById('source-video').paused",
                arg=mark,
                timeout=30000,
            )
            assert "ended" not in page.evaluate("() => window.clockEvents.map(event => event.name)")
            assert not requests and not errors
        finally:
            browser.close()


def test_reference_nonzero_visible_zero_axis_is_refused(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "nonzero")
    clock = reference_clock(case.reference[0])
    assert clock is not None and clock["originUs"] == generator_clock(FFMPEG).origin_us
    init_script = """(() => {
        // Controlled fault: after the axis probe performs its first seek, the visible element
        // reports position 0 although the clock origin is 2.478 s. The old OR check accepted
        // this as "axis == probe target"; it must instead stay unconfirmed and manually usable.
        const descriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime');
        const probed = new WeakMap();
        Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
            configurable: true,
            get() {
                if (this.id !== 'source-video') return descriptor.get.call(this);
                return probed.get(this) ? 0 : descriptor.get.call(this);
            },
            set(value) {
                if (this.id === 'source-video') probed.set(this, true);
                descriptor.set.call(this, value);
            },
        });
        window.restoreCurrentTime = () => Object.defineProperty(
            HTMLMediaElement.prototype, 'currentTime', descriptor);
    })();"""
    uri = case.asset.source_path.as_uri()
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            errors, requests = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: (
                    requests.append(item.url)
                    if not item.url.startswith(("file:", "data:", "blob:"))
                    else None
                ),
            )
            page.add_init_script(script=init_script)
            page.goto(case.reference_page.as_uri())
            page.wait_for_function(
                "() => document.getElementById('capture-start').disabled"
                " && document.getElementById('clock-state').textContent.includes('请手填规范源时间')",
                timeout=30000,
            )
            playwright.expect(page.locator("#open-source")).to_be_visible()
            playwright.expect(page.locator("#start-seconds")).to_have_value("")
            # Removing the fault and reloading restores the normal non-zero regression.
            page.evaluate("() => window.restoreCurrentTime()")
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    video.removeAttribute('src'); video.load();
                }"""
            )
            page.evaluate("url => { document.getElementById('source-video').src = url; }", uri)
            page.wait_for_function(
                "() => !document.getElementById('capture-start').disabled", timeout=30000
            )
            target = (500_000 + clock["originUs"]) / 1_000_000
            settled = present_at(page, target)
            assert abs(settled - target) <= SEEK_TOLERANCE
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.500000")
            assert not requests and not errors
        finally:
            browser.close()


def test_reference_moved_player_stays_pending_then_idle_validation_recovers(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    # Delay the detached probe (not the visible element) so the reviewer can move the player
    # while the generation validation is still running.
    init_script = """(() => {
        const load = HTMLMediaElement.prototype.load;
        HTMLMediaElement.prototype.load = function() {
            if (!this.isConnected) { setTimeout(() => load.call(this), 600); } else { load.call(this); }
        };
    })();"""
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(script=init_script)
            page.goto(case.reference_page.as_uri())
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    video.currentTime = 0.5;
                }"""
            )
            # Interaction alone must never publish ready: the page stays pending/manual.
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent"
                ".includes('尚未确认，正在等待播放器空闲后重新核对')",
                timeout=15000,
            )
            assert page.locator("#capture-start").is_disabled()
            playwright.expect(page.locator("#open-source")).to_be_visible()
            playwright.expect(page.locator("#start-seconds")).to_have_value("")
            # Once idle, the bounded revalidation probes the axis itself and restores the
            # reviewer's position instead of trusting the interaction.
            page.wait_for_function(
                "() => !document.getElementById('capture-start').disabled", timeout=15000
            )
            position = page.evaluate("() => document.getElementById('source-video').currentTime")
            assert abs(position - 0.5) <= 0.05
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.500000")
            assert not errors
        finally:
            browser.close()


def test_reference_zero_duration_growth_and_nonfinite_revoke(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    uri = case.asset.source_path.as_uri()
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.reference_page)
            normalize_player(page)
            wait_capture_ready(page)
            for reported, message in (
                (3.0, "意外变化"),
                (float("inf"), "没有读到可用的原片时长"),
                (float("nan"), "没有读到可用的原片时长"),
            ):
                page.evaluate(
                    """reported => {
                        const video = document.getElementById('source-video');
                        Object.defineProperty(video, 'duration', {configurable: true, get: () => reported});
                        video.dispatchEvent(new Event('durationchange'));
                    }""",
                    reported,
                )
                page.wait_for_function("() => document.getElementById('capture-start').disabled")
                playwright.expect(page.locator("#clock-state")).to_contain_text(message)
                playwright.expect(page.locator("#open-source")).to_be_visible()
                # Reload: remove the fault, reload the media, and the capability returns.
                page.evaluate(
                    """() => {
                        const video = document.getElementById('source-video');
                        delete video.duration;
                        video.removeAttribute('src'); video.load();
                    }"""
                )
                page.evaluate("url => { document.getElementById('source-video').src = url; }", uri)
                wait_capture_ready(page)
            assert not requests and not errors
        finally:
            browser.close()


def test_reference_nonzero_duration_growth_allowed_only_within_axis_end(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "nonzero")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.reference_page)
            normalize_player(page)
            wait_capture_ready(page)
            # The measured post-seek growth of a non-zero-PTS file stays within its absolute
            # axis end (origin + span = 4.5 s) and must keep the capability.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'duration', {configurable: true, get: () => 3.5});
                    video.dispatchEvent(new Event('durationchange'));
                }"""
            )
            assert page.locator("#capture-start").is_enabled()
            playwright.expect(page.locator("#clock-state")).to_contain_text(
                "已把浏览器播放位置换算为规范源时间"
            )
            # Growth past the absolute axis end is unexpected and revokes.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'duration', {configurable: true, get: () => 4.6});
                    video.dispatchEvent(new Event('durationchange'));
                }"""
            )
            page.wait_for_function("() => document.getElementById('capture-start').disabled")
            playwright.expect(page.locator("#clock-state")).to_contain_text("意外变化")
            assert not requests and not errors
        finally:
            browser.close()


def test_candidate_zero_duration_growth_and_nonfinite_refuse_replay(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    clock = selected_media(case.candidate[0])["sourceClock"]
    assert clock is not None
    end_player = (END_US + clock["originUs"]) / 1_000_000
    uri = case.asset.source_path.as_uri()
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            normalize_player(page)
            wait_clock_ready(page)
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    window.clockEvents = [];
                    for (const name of ['play', 'pause']) {
                        video.addEventListener(name, () => window.clockEvents.push({name}));
                    }
                }"""
            )
            page.locator(".slot button").first.click()
            wait_for_pause_at(page, end_player)
            plays_before = page.evaluate(
                "() => window.clockEvents.filter(event => event.name === 'play').length"
            )
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'duration', {configurable: true, get: () => 3.0});
                    video.dispatchEvent(new Event('durationchange'));
                }"""
            )
            page.locator(".slot button").first.click()
            playwright.expect(page.locator("#play-state")).to_contain_text("原片时长发生了意外变化")
            assert (
                page.evaluate(
                    "() => window.clockEvents.filter(event => event.name === 'play').length"
                )
                == plays_before
            )
            # Non-finite follows the same fail-closed path on a freshly validated generation.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    delete video.duration;
                    video.removeAttribute('src'); video.load();
                }"""
            )
            page.evaluate("url => { document.getElementById('source-video').src = url; }", uri)
            page.locator(".slot button").first.click()
            wait_for_pause_at(page, end_player)
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    Object.defineProperty(video, 'duration', {configurable: true, get: () => Infinity});
                    video.dispatchEvent(new Event('durationchange'));
                }"""
            )
            page.locator(".slot button").first.click()
            playwright.expect(page.locator("#play-state")).to_contain_text("原片时长无效")
            assert (
                page.evaluate(
                    "() => window.clockEvents.filter(event => event.name === 'play').length"
                )
                == plays_before + 1
            )
            assert not requests and not errors
        finally:
            browser.close()


def test_candidate_reload_during_axis_await_cancels_old_request(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    clock = selected_media(case.candidate[0])["sourceClock"]
    assert clock is not None
    end_player = (END_US + clock["originUs"]) / 1_000_000
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            normalize_player(page)
            wait_clock_ready(page)
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    window.clockEvents = [];
                    for (const name of ['play', 'pause', 'ended']) {
                        video.addEventListener(name, () => window.clockEvents.push({name}));
                    }
                    window.blockSeeked = event => event.stopImmediatePropagation();
                    video.addEventListener('seeked', window.blockSeeked, true);
                }"""
            )
            page.locator(".slot button").first.click()
            page.wait_for_timeout(200)  # the axis settle is still awaiting `seeked`
            # External reload of the same URL while the old request is locating.
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    video.load();
                    video.removeEventListener('seeked', window.blockSeeked, true);
                    video.dispatchEvent(new Event('seeked')); // late event for the old request
                }"""
            )
            page.wait_for_timeout(800)
            assert (
                page.evaluate("() => window.clockEvents.filter(e => e.name === 'play').length") == 0
            )
            assert page.evaluate("() => document.getElementById('source-video').paused")
            # A fresh click on the rebuilt generation is validated and plays normally.
            page.locator(".slot button").first.click()
            page.wait_for_function(
                "() => window.clockEvents.some(event => event.name === 'play')"
                " && document.getElementById('source-video').paused",
                timeout=30000,
            )
            assert page.evaluate("() => document.getElementById('source-video').currentTime") >= (
                end_player - SEEK_TOLERANCE
            )
            assert "ended" not in page.evaluate("() => window.clockEvents.map(event => event.name)")
            assert not requests and not errors
        finally:
            browser.close()


def test_reference_axis_restore_never_writes_the_old_position_into_a_new_generation(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    # Delay the detached probe so the bounded retry is observable, then move the player so the
    # retry takes the restoreTo !== null branch.
    init_script = """(() => {
        const load = HTMLMediaElement.prototype.load;
        HTMLMediaElement.prototype.load = function() {
            if (!this.isConnected) { setTimeout(() => load.call(this), 400); } else { load.call(this); }
        };
    })();"""
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            errors, requests = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda item: (
                    requests.append(item.url)
                    if not item.url.startswith(("file:", "data:", "blob:"))
                    else None
                ),
            )
            page.add_init_script(script=init_script)
            page.goto(case.reference_page.as_uri())
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    window.axisSeekSeen = false;
                    window.blockSeeked = event => event.stopImmediatePropagation();
                    video.addEventListener('seeked', window.blockSeeked, true);
                    video.addEventListener('seeking', () => {
                        if (Math.abs(video.currentTime) <= 0.01) window.axisSeekSeen = true;
                    });
                    video.currentTime = 0.5; // first validation must stay pending/manual
                }"""
            )
            page.wait_for_function(
                "() => document.getElementById('clock-state').textContent"
                ".includes('尚未确认，正在等待播放器空闲后重新核对')",
                timeout=15000,
            )
            # Wait until the idle retry's axis seek is in flight (its `seeked` is blocked), then
            # reload the media. The late event must not restore the old 0.5 s into the new load.
            page.wait_for_function("() => window.axisSeekSeen === true", timeout=20000)
            # The retry is now suspended on its axis `seeked`: the player was moved to 0.5 s
            # (restoreTo !== null) and the probe has moved it to the axis start, so the old
            # position is still waiting to be restored - exactly the branch under test.
            pending_position = page.evaluate(
                "() => document.getElementById('source-video').currentTime"
            )
            assert pending_position <= 0.05
            page.evaluate(
                """() => {
                    const video = document.getElementById('source-video');
                    video.load();
                    video.removeEventListener('seeked', window.blockSeeked, true);
                    video.dispatchEvent(new Event('seeked')); // late event for the old request
                }"""
            )
            page.wait_for_timeout(1500)
            position = page.evaluate("() => document.getElementById('source-video').currentTime")
            assert position <= 0.05, (
                f"old restore position leaked into the new generation: {position}"
            )
            # The rebuilt generation validates normally and allows capture; the positive
            # same-generation restore path is covered by the moved-player test above.
            wait_capture_ready(page)
            present_at(page, 0.25)
            page.locator("#capture-start").click()
            playwright.expect(page.locator("#start-seconds")).to_have_value("0.250000")
            assert not requests and not errors
        finally:
            browser.close()
