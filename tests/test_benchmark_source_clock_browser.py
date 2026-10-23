"""Real synthetic source clocks through both builders and local Chromium.

Every clip is generated on the spot with project FFmpeg and contains no user footage,
database, annotation or model output. The pages are produced by the real builders, and
the browser checks stay manual-side for special clocks; nothing here is human acceptance.
"""

import asyncio
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_benchmark import document
from test_benchmark_preparation import plan_fixture
from test_material_tasks import CONFIG

from gamingcreator.application.benchmark import BenchmarkHit, parse_manifest, run_benchmark
from gamingcreator.application.benchmark_preparation import loads_plan
from gamingcreator.application.benchmark_reference_review import (
    build_reference_context,
    validate_reference_record,
)
from gamingcreator.application.benchmark_review import build_review_context, validate_review
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.media import MediaAsset
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.ui.benchmark_reference_review import render_reference_review
from gamingcreator.ui.benchmark_review import render_benchmark_review

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
PREPARED_AT = "2026-10-23T10:00:00+08:00"
START_US, END_US = 300_000, 700_000
# Explicit tolerances for the zero-origin playback evidence: the seek is deterministic
# (0.3 s), the play event may trail it slightly, and a stop near the interval end must
# stay far below the 2 s clip end.
SEEK_TOLERANCE = 0.02
START_TOLERANCE = 0.1
PAUSE_SLACK = 0.5
CASES = (("zero", True), ("nonzero", False), ("async", False))


@dataclass(frozen=True)
class ClockCase:
    kind: str
    automatic: bool
    asset: MediaAsset
    assets: dict[str, MediaAsset]
    candidate: tuple[dict[str, object], dict[str, object]]
    reference: tuple[dict[str, object], dict[str, object]]
    candidate_page: Path
    reference_page: Path


def synthesize(path: Path, kind: str) -> None:
    assert FFMPEG.is_file(), "Project-local FFmpeg is required for source-clock fixtures."
    inputs = ["-f", "lavfi", "-i", "testsrc2=size=160x96:rate=30:duration=2"]
    if kind == "async":
        inputs += ["-itsoffset", "0.5"]
    tail = ["-output_ts_offset", "2.5"] if kind == "nonzero" else []
    subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-v",
            "error",
            *inputs,
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            *tail,
            str(path),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def probe_source(path: Path) -> MediaAsset:
    return asyncio.run(
        FfmpegMediaProcessor(ROOT).probe(path, CancellationContext("source-clock", 30))
    )


def candidate_review(asset: MediaAsset) -> tuple[dict[str, object], dict[str, object]]:
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
    identifiers = ("event-0", "event-1")
    hits = tuple(
        BenchmarkHit(identifier, START_US, END_US, position)
        for position, identifier in enumerate(identifiers, 1)
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
            "start_us": START_US,
            "end_us": END_US,
            "evidence_ids": ["synthetic-source-clock:image"],
        }
        for position, identifier in enumerate(identifiers, 1)
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
    asset: MediaAsset, directory: Path
) -> tuple[tuple[dict[str, object], dict[str, object]], dict[str, MediaAsset]]:
    raw, _ = plan_fixture(directory)
    raw["sources"][0]["path"] = str(asset.source_path)
    assets = {"source-0": asset}
    return build_reference_context(loads_plan(json.dumps(raw)), assets, PREPARED_AT), assets


def clock_case(tmp_path: Path, kind: str, automatic: bool) -> ClockCase:
    source = tmp_path / f"{kind} 源 空格.mp4"
    synthesize(source, kind)
    asset = probe_source(source)
    candidate = candidate_review(asset)
    reference, assets = reference_review(asset, tmp_path)
    candidate_page = tmp_path / f"{kind}-candidate.html"
    candidate_page.write_text(render_benchmark_review(*candidate), encoding="utf-8")
    reference_page = tmp_path / f"{kind}-reference.html"
    reference_page.write_text(render_reference_review(*reference), encoding="utf-8")
    return ClockCase(
        kind, automatic, asset, assets, candidate, reference, candidate_page, reference_page
    )


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


@pytest.mark.parametrize("kind,automatic", CASES)
def test_synthetic_clock_probe_matches_both_builder_flags(tmp_path, kind, automatic):
    case = clock_case(tmp_path, kind, automatic)
    asset = case.asset
    starts = {stream.kind: float(stream.start_seconds) for stream in asset.streams}
    assert set(starts) == {"video", "audio"}
    assert asset.origin_seconds == min(stream.start_seconds for stream in asset.streams)
    assert 1_900_000 <= asset.duration_us <= 2_100_000
    if kind == "zero":
        assert float(asset.origin_seconds) == 0 and set(starts.values()) == {0.0}
    elif kind == "nonzero":
        assert float(asset.origin_seconds) > 2.4 and min(starts.values()) > 2.4
    else:
        assert float(asset.origin_seconds) == 0 and starts["video"] == 0
        assert 0.4 < starts["audio"] < 0.6
    review, template = case.candidate
    reference, _ = case.reference
    row = review["media"][0]
    assert row["automaticPlaybackSupported"] is automatic
    assert reference["media"][0]["automaticTimeCapture"] is automatic
    assert set(row) == {
        "runId",
        "name",
        "path",
        "durationUs",
        "originSeconds",
        "automaticPlaybackSupported",
    }
    assert row["originSeconds"] == str(asset.origin_seconds)
    assert all(slot["grade"] is None for slot in template["queries"][0]["slots"])
    assert template["reviewed"] is False


@pytest.mark.parametrize("kind", ["nonzero", "async"])
def test_special_clock_pages_keep_manual_notice_source_link_and_manual_interval(tmp_path, kind):
    from playwright.sync_api import expect, sync_playwright

    case = clock_case(tmp_path, kind, False)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            expect(page.locator(".slot")).to_have_count(10)
            page.locator(".slot button").first.click()
            expect(page.locator("#play-state")).to_have_text(
                "这段原片的时钟尚未联调，请手动核对原区间。"
            )
            link = page.locator("#open-source")
            expect(link).to_be_visible()
            assert link.get_attribute("href") == case.asset.source_path.as_uri()
            assert page.locator("#source-video").evaluate("video => video.paused")
            assert page.locator("#source-video").evaluate("video => video.currentSrc") == ""
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            blank = Path(pending.value.path()).read_bytes()
            assert json.loads(blank) == case.candidate[1]
            record = validate_review(blank, case.candidate[1], case.candidate[0])
            assert all(
                slot["grade"] is None for query in record["queries"] for slot in query["slots"]
            )

            page.goto(case.reference_page.as_uri())
            page.wait_for_function("() => document.getElementById('source-video').readyState >= 1")
            expect(page.locator("#clock-state")).to_have_text(
                "此录像起始时间特殊，请手填规范源时间；不自动采用播放器位置。"
            )
            assert page.locator("#capture-start").is_disabled()
            assert page.locator("#capture-end").is_disabled()
            page.locator("#start-seconds").fill("0.250000")
            page.locator("#end-seconds").fill("1.000000")
            page.locator("#event-id").fill("fixture-action")
            page.locator("#event-group").fill("fixture-same-action")
            page.locator("#reason").fill("Synthetic clock fixture, not human acceptance.")
            page.locator("#add-reference").click()
            expect(page.locator(".slot")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            saved = Path(pending.value.path()).read_bytes()
            reference = validate_reference_record(saved, case.reference[0], case.assets)
            events = reference["plan"]["queries"][0]["referenceEvents"]
            assert [(event["humanEventId"], event["usableRanges"]) for event in events] == [
                ("fixture-action", [{"startUs": 250_000, "endUs": 1_000_000}])
            ]
            assert reference["plan"]["humanReferences"] == {
                "confirmed": False,
                "reviewed": False,
                "annotators": [],
            }
            assert not page.locator("#confirmed").is_checked()
            assert not requests and not errors
        finally:
            browser.close()


def test_zero_origin_candidate_seeks_plays_and_pauses_while_reference_captures_position(tmp_path):
    from playwright.sync_api import expect, sync_playwright

    case = clock_case(tmp_path, "zero", True)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page, requests, errors = open_page(browser, case.candidate_page)
            expect(page.locator(".slot")).to_have_count(10)
            assert page.locator("#open-source").is_hidden()
            page.evaluate("""() => {
                const video = document.getElementById('source-video');
                window.clockEvents = [];
                for (const name of ['seeking', 'seeked', 'play', 'playing', 'pause', 'ended']) {
                    video.addEventListener(name, () => window.clockEvents.push({
                        name,
                        at: performance.now(),
                        currentTime: video.currentTime,
                        ended: video.ended,
                    }));
                }
            }""")
            page.locator(".slot button").first.click()
            page.wait_for_function(
                "() => { const video = document.getElementById('source-video');"
                " return !video.paused && video.currentTime >= 0.29; }",
                timeout=15000,
            )
            start_seconds = START_US / 1_000_000
            end_seconds = END_US / 1_000_000
            expect(page.locator("#play-state")).to_contain_text("第1位")
            expect(page.locator("#play-state")).to_contain_text(
                f"{start_seconds:.3f}–{end_seconds:.3f}秒"
            )
            source_url = case.asset.source_path.as_uri()
            assert page.locator("#open-source").get_attribute("href") == source_url
            page.wait_for_function(
                "() => { const video = document.getElementById('source-video');"
                " return video.paused && video.currentTime >= 0.68; }",
                timeout=20000,
            )
            # The paused getter flips before the queued pause event runs; wait for the
            # recorded event so the assertions below never read a stale log.
            page.wait_for_function("() => window.clockEvents.some(row => row.name === 'pause')")
            media = page.locator("#source-video")
            events = page.evaluate("() => window.clockEvents")
            names = [event["name"] for event in events]
            starts = [event for event in events if event["name"] in ("seeking", "seeked")]
            plays = [event for event in events if event["name"] == "play"]
            pauses = [event for event in events if event["name"] == "pause"]
            assert starts, "no automatic seek was recorded before playback"
            assert plays, "no play event was recorded"
            assert pauses, "no pause event was recorded"
            assert "ended" not in names
            assert any(
                abs(event["currentTime"] - start_seconds) <= SEEK_TOLERANCE for event in starts
            )
            assert abs(plays[0]["currentTime"] - start_seconds) <= START_TOLERANCE
            final_pause = pauses[-1]
            assert final_pause["at"] > max(event["at"] for event in starts + plays)
            assert final_pause["ended"] is False
            assert final_pause["currentTime"] >= end_seconds - SEEK_TOLERANCE
            assert final_pause["currentTime"] < end_seconds + PAUSE_SLACK
            current_time = media.evaluate("video => video.currentTime")
            assert not media.evaluate("video => video.ended")
            assert current_time >= end_seconds - SEEK_TOLERANCE
            assert current_time < end_seconds + PAUSE_SLACK
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            blank = Path(pending.value.path()).read_bytes()
            assert json.loads(blank) == case.candidate[1]
            validate_review(blank, case.candidate[1], case.candidate[0])

            page.goto(case.reference_page.as_uri())
            page.wait_for_function("() => document.getElementById('source-video').readyState >= 1")
            expect(page.locator("#clock-state")).to_have_text(
                "可用播放器位置标记；保存前请核对完整动作与区间。"
            )
            assert not page.locator("#capture-start").is_disabled()
            page.locator("#source-video").evaluate("video => { video.currentTime = 0.25; }")
            page.wait_for_function(
                "() => Math.abs(document.getElementById('source-video').currentTime - 0.25) < 0.01"
            )
            page.locator("#capture-start").click()
            captured = page.locator("#start-seconds").input_value()
            whole, _, fraction = captured.partition(".")
            assert whole.isdigit() and len(fraction) == 6 and abs(float(captured) - 0.25) < 0.02
            page.locator("#end-seconds").fill("1.000000")
            page.locator("#event-id").fill("fixture-action")
            page.locator("#event-group").fill("fixture-same-action")
            page.locator("#reason").fill("Synthetic clock fixture, not human acceptance.")
            page.locator("#add-reference").click()
            expect(page.locator(".slot")).to_have_count(1)
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            saved = Path(pending.value.path()).read_bytes()
            reference = validate_reference_record(saved, case.reference[0], case.assets)
            ranges = reference["plan"]["queries"][0]["referenceEvents"][0]["usableRanges"]
            assert len(ranges) == 1 and ranges[0]["endUs"] == 1_000_000
            assert abs(ranges[0]["startUs"] - 250_000) <= 20_000
            assert reference["plan"]["humanReferences"]["confirmed"] is False
            assert not requests and not errors
        finally:
            browser.close()
