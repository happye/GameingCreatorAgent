"""C09: project search attaches a screen-text group only when explicitly requested."""

from __future__ import annotations

import asyncio
import json

from test_inspection_http import workspace
from test_project_search_workspace import body, guard, pool, post
from test_screen_text_reports import _frame_text_report, _snapshot

from gamingcreator.application.search_detail_query import search_snapshot_sha256
from gamingcreator.cli.local_reports import load_saved_timeline
from gamingcreator.cli.shot_boundaries import saved_frames
from gamingcreator.infrastructure.project_search_files import read_project_search
from gamingcreator.ui.frame_text import frame_text_cache_path, frames_digest, scanned_frames


def _plant_cache(repository, project, run_id, text):
    timeline = asyncio.run(load_saved_timeline(project, run_id))
    saved = saved_frames(timeline)
    assert saved, "fixture run must have registered frames to bind screen text"
    asset = timeline.run.asset
    chosen = scanned_frames(saved, 1)
    document = _frame_text_report(
        saved,
        runId=run_id,
        sourceSha256=asset.sha256,
        durationUs=asset.duration_us,
    )
    document["frames"] = [
        {"timeUs": time_us, "lines": [{"text": text, "likelyText": True}]} for _, time_us in chosen
    ]
    document["framesDigest"] = frames_digest(chosen)
    path = frame_text_cache_path(repository, project, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path, chosen[0]


def test_screen_text_option_is_explicit_and_does_not_change_old_candidates(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("search must not start a new OCR task")

    monkeypatch.setattr("gamingcreator.cli.ocr_frames.build_run_ocr_report", boom)
    monkeypatch.setattr("gamingcreator.ui.frame_text.scan_frame_text_payload", boom)
    project, _bundles = pool(tmp_path)
    guard(monkeypatch)
    cache, first = _plant_cache(tmp_path, project, "run-0", "建造营地")
    before = _snapshot(cache)

    with workspace(tmp_path) as base:
        status, _, raw = post(base, body(project))
        assert status == 200
        original = json.loads(raw)
        assert "screenTextMatches" not in original
        assert "screenTextPrepared" not in original
        assert "screenTextNotice" not in original

        bad = post(base, body(project, includeScreenText="yes"))
        assert bad[0] == 400

        status, _, raw = post(base, body(project, includeScreenText=True))
        assert status == 200
        enabled = json.loads(raw)
        assert enabled["candidates"] == original["candidates"]
        assert enabled.get("qualityGate") == original.get("qualityGate")
        assert enabled["modelAnalysisCalls"] == original["modelAnalysisCalls"]
        matches = enabled["screenTextMatches"]
        assert matches
        assert matches[0]["runId"] == "run-0"
        assert matches[0]["text"] == "建造营地"
        assert matches[0]["evidenceId"] == first[0]
        assert matches[0]["timeUs"] == first[1]
        assert "建造营地" not in json.dumps(enabled["candidates"], ensure_ascii=False)
        saved = read_project_search(project, enabled["searchId"])
        assert "screenTextMatches" not in saved
        assert "screenTextPrepared" not in saved
        assert "screenTextNotice" not in saved
        assert enabled["searchSha256"] == search_snapshot_sha256(saved)
        official = {
            key: value
            for key, value in enabled.items()
            if key
            not in {
                "project",
                "searchSha256",
                "screenTextMatches",
                "screenTextPrepared",
                "screenTextNotice",
                "screenTextDiagnostics",
            }
        }
        assert official == saved
        assert enabled["searchSha256"] == search_snapshot_sha256(official)

        status, _, raw = post(base, body(project, includeScreenText=True, query="没有这句屏幕字"))
        assert status == 200
        empty_hits = json.loads(raw)
        assert empty_hits["screenTextPrepared"] is True
        assert empty_hits["screenTextMatches"] == []

    assert _snapshot(cache) == before


def test_missing_cache_stays_empty_and_does_not_start_ocr(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("search must not start a new OCR task")

    monkeypatch.setattr("gamingcreator.cli.ocr_frames.build_run_ocr_report", boom)
    monkeypatch.setattr("gamingcreator.ui.frame_text.scan_frame_text_payload", boom)
    project, _bundles = pool(tmp_path)
    guard(monkeypatch)
    with workspace(tmp_path) as base:
        status, _, raw = post(base, body(project, includeScreenText=False))
        assert status == 200
        disabled = json.loads(raw)
        assert "screenTextMatches" not in disabled

        status, _, raw = post(base, body(project, includeScreenText=True))
        assert status == 200
        enabled = json.loads(raw)
        assert enabled["candidates"] == disabled["candidates"]
        assert enabled.get("qualityGate") == disabled.get("qualityGate")
        assert enabled["modelAnalysisCalls"] == disabled["modelAnalysisCalls"]
        assert enabled["screenTextMatches"] == []
        assert enabled["screenTextPrepared"] is False
        assert enabled["screenTextNotice"] == "尚未准备屏幕文字，未开始新的识别任务。"
        assert enabled["screenTextDiagnostics"] == []
        saved = read_project_search(project, enabled["searchId"])
        assert "screenTextMatches" not in saved
        official = {
            key: value
            for key, value in enabled.items()
            if key
            not in {
                "project",
                "searchSha256",
                "screenTextMatches",
                "screenTextPrepared",
                "screenTextNotice",
                "screenTextDiagnostics",
            }
        }
        assert official == saved
        assert enabled["searchSha256"] == search_snapshot_sha256(official)
