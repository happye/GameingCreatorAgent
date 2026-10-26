"""Workbench on-screen text: explicit local scan, cache outside the project, texts only."""

from __future__ import annotations

import asyncio
import json
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_detail_query import snapshot
from test_inspection_http import get, workspace
from test_material_tasks import seed_tasks
from test_ocr_frames import FakeEngine, FakeFrames, asset
from test_shot_boundaries_http import post

from gamingcreator.application.ocr_frames import OcrEngineIdentity, matched_frames
from gamingcreator.domain.errors import AppError
from gamingcreator.ui import frame_text
from gamingcreator.ui.frame_text import (
    density_every,
    frame_text_cache_path,
    frames_digest,
    scan_frame_text_payload,
    scanned_frames,
)

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"


def fakes(monkeypatch) -> tuple[FakeFrames, FakeEngine]:
    frames, engine = FakeFrames(), FakeEngine()
    calls = {"frames": 0}

    def make_frames(repository):
        calls["frames"] += 1
        return frames

    monkeypatch.setattr("gamingcreator.ui.server.FfmpegFullResolutionFrames", make_frames)
    monkeypatch.setattr("gamingcreator.ui.server.WindowsOcrEngine", lambda scratch: engine)
    return frames, engine


def test_scan_is_explicit_cached_outside_the_project_and_returns_texts_only(tmp_path, monkeypatch):
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    reference = project.relative_to(tmp_path).as_posix()
    frames, engine = fakes(monkeypatch)
    before = snapshot(project)
    query = "/api/frame-text?" + urlencode({"project": reference, "run": "run-000"})
    request = {"project": reference, "run": "run-000", "density": "quick"}
    with workspace(tmp_path) as base:
        health = json.loads(get(base, "/api/health")[2])
        assert "frame-text-v1" in health["capabilities"]
        status, _, raw = get(base, query)
        assert status == 200 and json.loads(raw)["available"] is False and engine.seen == []
        status, _, raw = post(base, "/api/ocr-frames", request)
        scanned = json.loads(raw)
        assert status == 200 and len(engine.seen) == 1
        assert scanned["available"] is True and scanned["project"] == reference
        assert scanned["schemaVersion"] == "frame-text-v1" and scanned["density"] == "quick"
        assert scanned["recurringTexts"][0]["text"] == "游戏科学"
        assert scanned["frames"] == [
            {"timeUs": 100_000, "lines": [{"text": "游戏科学", "likelyText": True}]}
        ]
        assert (scanned["readOnly"], scanned["paidRequests"], scanned["humanReviewed"]) == (
            True,
            0,
            False,
        )
        # Word boxes and file paths never reach the page.
        assert '"words"' not in raw.decode() and "evidenceId" not in raw.decode()
        assert ".cache" not in raw.decode() and "frame-000001" not in raw.decode()
        cache = frame_text_cache_path(tmp_path, project, "run-000")
        assert cache.is_file() and project not in cache.parents
        assert frames.output is not None and not frames.output.exists()
        status, _, raw = get(base, query)
        assert status == 200 and json.loads(raw) == scanned and len(engine.seen) == 1
        for bad in (
            {"project": reference, "run": "run-000"},
            {"project": reference, "run": "", "density": "quick"},
            {"project": reference, "run": "run-000", "density": "fast"},
            {"project": reference, "run": "run-000", "density": "quick", "every": 1},
        ):
            assert post(base, "/api/ocr-frames", bad)[0] == 400
        missing = post(base, "/api/ocr-frames", {**request, "run": "nope"})
        assert missing[0] == 404
        # A different OCR engine or Windows build no longer matches the saved report.
        engine.identity = lambda: OcrEngineIdentity("fixture-ocr", "other-build")
        assert json.loads(get(base, query)[2])["available"] is False
    assert snapshot(project) == before


def test_cached_report_goes_stale_when_its_frames_or_source_identity_differ(tmp_path, monkeypatch):
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    reference = project.relative_to(tmp_path).as_posix()
    fakes(monkeypatch)
    query = "/api/frame-text?" + urlencode({"project": reference, "run": "run-000"})
    cache = frame_text_cache_path(tmp_path, project, "run-000")
    with workspace(tmp_path) as base:
        post(base, "/api/ocr-frames", {"project": reference, "run": "run-000", "density": "full"})
        original = cache.read_text(encoding="utf-8")
        assert json.loads(get(base, query)[2])["available"] is True
        for field, value in (
            ("framesDigest", "0" * 64),
            ("sourceSha256", "f" * 64),
            ("durationUs", 1),
            ("every", 0),
            ("runId", "run-001"),
        ):
            document = json.loads(original)
            document[field] = value
            cache.write_text(json.dumps(document), encoding="utf-8")
            assert json.loads(get(base, query)[2])["available"] is False, field
        cache.write_text("not json", encoding="utf-8")
        assert json.loads(get(base, query)[2])["available"] is False


def test_cache_digest_matches_the_frames_a_stepped_scan_reads():
    """A quick scan reads matched_frames(...)[::every]; the cache check must rebuild that list."""
    media = asset()
    saved = [(f"e{index}", index * 500_000) for index in range(7)][::-1]
    extracted = [
        (1000 + index * 500, Fraction(1, 1000), Path(f"{index}.jpg")) for index in range(7)
    ]
    for every in (1, 2, 3, 4, 7, 9):
        read = [(evidence, time) for evidence, time, _ in matched_frames(media, saved, extracted)]
        assert scanned_frames(saved, every) == tuple(read[::every])
        assert frames_digest(scanned_frames(saved, every)) == frames_digest(read[::every])
    assert frames_digest(scanned_frames(saved, 2)) != frames_digest(scanned_frames(saved, 1))


def test_density_steps_and_concurrent_scans_are_refused(tmp_path):
    assert density_every(500, "full") == 1
    assert density_every(500, "quick") == 4
    assert density_every(3000, "quick") == 1
    assert density_every(1500, "quick") == 1
    assert density_every(700, "quick") == 3
    with pytest.raises(AppError):
        density_every(500, "every-frame")
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    target = frame_text_cache_path(tmp_path, project, "run-000")
    frame_text._busy.add(target)
    try:
        with pytest.raises(AppError) as busy:
            asyncio.run(
                scan_frame_text_payload(
                    project,
                    "run-000",
                    tmp_path,
                    FakeFrames(),
                    FakeEngine(),
                    density="quick",
                    project_reference="p",
                )
            )
        assert busy.value.code == "frame_text.busy"
    finally:
        frame_text._busy.discard(target)
    assert not target.exists()


def test_workbench_static_scans_only_on_click_and_renders_text_safely():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "frame-text-v1" in js and js.count('"/api/ocr-frames"') == 1
    assert 'id="frame-text-card"' in html and 'id="scan-frame-text"' in html
    assert 'id="frame-text-query"' in html and 'id="frame-text-results"' in html
    block = js[js.index("function renderFrameText") : js.index("async function loadFrameText")]
    assert "innerHTML" not in block
