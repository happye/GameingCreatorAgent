"""C18: workbench loop covers isolated, old, stale, and same-time reports."""

from __future__ import annotations

import asyncio
import csv
import json
from io import StringIO
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_project_search_workspace import body, choose_sources, guard, pool, post
from test_screen_text_export_json import MATCH_FIELDS
from test_screen_text_locate_ui import _timecode
from test_screen_text_reports import _frame_text_report, _official_report, _snapshot
from test_screen_text_search_http import _plant_cache

from gamingcreator.cli.local_reports import load_saved_timeline
from gamingcreator.cli.shot_boundaries import saved_frames
from gamingcreator.ui.frame_text import frame_text_cache_path, frames_digest, scanned_frames


def _forbid_ocr(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("search must not start a new OCR task")

    monkeypatch.setattr("gamingcreator.cli.ocr_frames.build_run_ocr_report", boom)
    monkeypatch.setattr("gamingcreator.ui.frame_text.scan_frame_text_payload", boom)


def _plant_official_cache(repository, project, run_id, text):
    timeline = asyncio.run(load_saved_timeline(project, run_id))
    saved = saved_frames(timeline)
    assert saved, "fixture run must have registered frames to bind screen text"
    asset = timeline.run.asset
    document = _official_report(
        saved,
        runId=run_id,
        sourceSha256=asset.sha256,
        durationUs=asset.duration_us,
    )
    document["frames"] = [
        {
            "evidenceId": evidence,
            "timeUs": time_us,
            "status": "text",
            "lines": [{"text": text, "likelyText": True}],
        }
        for evidence, time_us in saved
    ]
    path = frame_text_cache_path(repository, project, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path, saved[0]


def _plant_stale_cache(repository, project, run_id, text):
    timeline = asyncio.run(load_saved_timeline(project, run_id))
    saved = saved_frames(timeline)
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
    document["framesDigest"] = "0" * 64
    path = frame_text_cache_path(repository, project, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _plant_stray_report(repository, text):
    path = (
        repository.resolve() / ".cache" / "workspace" / "frame-text" / "stray-not-a-cache-key.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    document = _frame_text_report((("ghost:image", 100_000),), runId="run-0")
    document["frames"] = [{"timeUs": 100_000, "lines": [{"text": text, "likelyText": True}]}]
    document["framesDigest"] = frames_digest((("ghost:image", 100_000),))
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _plant_foreign_project_cache(repository, project, text):
    foreign = project.parent / "foreign-project"
    path = frame_text_cache_path(repository, foreign, "run-0")
    path.parent.mkdir(parents=True, exist_ok=True)
    document = _frame_text_report((("run-0:image", 100_000),), runId="run-0")
    document["frames"] = [{"timeUs": 100_000, "lines": [{"text": text, "likelyText": True}]}]
    document["framesDigest"] = frames_digest((("run-0:image", 100_000),))
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _prepare_isolated_reports(repository, project):
    official, first = _plant_official_cache(repository, project, "run-0", "建造营地")
    current, second = _plant_cache(repository, project, "run-1", "建造哨塔")
    stale = _plant_stale_cache(repository, project, "run-2", "建造仓库")
    stray = _plant_stray_report(repository, "建造幽灵")
    foreign = _plant_foreign_project_cache(repository, project, "建造外项目")
    paths = (official, current, stale, stray, foreign)
    return {
        "first": first,
        "second": second,
        "paths": paths,
        "before": {path: _snapshot(path) for path in paths},
    }


def _assert_loop_payload(result, first, second, before):
    assert [row["rank"] for row in result["candidates"]] == [1, 2, 3]
    assert {row["runId"] for row in result["candidates"]} == {"run-0", "run-1", "run-2"}
    assert result["modelAnalysisCalls"] == 0
    matches = result["screenTextMatches"]
    assert len(matches) == 2
    assert [row["runId"] for row in matches] == ["run-0", "run-1"]
    assert matches[0]["text"] == "建造营地"
    assert matches[1]["text"] == "建造哨塔"
    assert matches[0]["evidenceId"] == first[0]
    assert matches[1]["evidenceId"] == second[0]
    assert matches[0]["timeUs"] == matches[1]["timeUs"] == first[1] == second[1]
    assert matches[0]["sourceSha256"] != matches[1]["sourceSha256"]
    assert all(row["text"] != "建造仓库" for row in matches)
    assert all("幽灵" not in row["text"] and "外项目" not in row["text"] for row in matches)
    assert result["screenTextPrepared"] is True
    diagnostics = result["screenTextDiagnostics"]
    assert any("画面指纹" in item for item in diagnostics)
    assert all("/" not in item and "\\" not in item for item in diagnostics)
    for path, snap in before.items():
        assert _snapshot(path) == snap
        assert str(path) not in json.dumps(result, ensure_ascii=False)


def test_http_workbench_loop_keeps_old_stale_and_same_time_reports_isolated(tmp_path, monkeypatch):
    _forbid_ocr(monkeypatch)
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    planted = _prepare_isolated_reports(tmp_path, project)
    with workspace(tmp_path) as base:
        status, _, raw = post(base, body(project, includeScreenText=True))
        assert status == 200
        result = json.loads(raw)
        _assert_loop_payload(result, planted["first"], planted["second"], planted["before"])


def test_browser_workbench_loop_locates_and_exports_isolated_reports(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    _forbid_ocr(monkeypatch)
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    planted = _prepare_isolated_reports(tmp_path, project)
    first, second = planted["first"], planted["second"]
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            page.locator("#include-screen-text").check()
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            cards = page.locator(".screen-text-card")
            playwright.expect(cards).to_have_count(2)
            playwright.expect(cards.nth(0)).to_contain_text("run-0")
            playwright.expect(cards.nth(0)).to_contain_text("建造营地")
            playwright.expect(cards.nth(1)).to_contain_text("run-1")
            playwright.expect(cards.nth(1)).to_contain_text("建造哨塔")
            body_text = page.locator("#screen-text-results").inner_text()
            assert "建造仓库" not in body_text
            assert "建造幽灵" not in body_text
            assert "建造外项目" not in body_text
            diagnostics = page.locator("#screen-text-diagnostics")
            playwright.expect(diagnostics).to_be_visible()
            playwright.expect(diagnostics).to_contain_text("画面指纹")
            diag_text = diagnostics.inner_text()
            assert "\\" not in diag_text and "/" not in diag_text

            cards.nth(1).click()
            playwright.expect(page.locator("#run-select")).to_have_value("run-1")
            playwright.expect(page.locator("#active-title")).to_have_text("屏幕文字 · run-1")
            playwright.expect(page.locator("#active-range")).to_have_text(
                f"源时刻 {_timecode(second[1])}"
            )
            playwright.expect(page.locator("#active-facts")).to_have_text("建造哨塔")
            playwright.expect(page.locator("#current-time")).to_have_text(_timecode(second[1]))
            playwright.expect(page.locator(".screen-text-card.active")).to_have_attribute(
                "data-run", "run-1"
            )
            playwright.expect(page.locator(".screen-text-card.active")).to_have_attribute(
                "data-evidence", second[0]
            )

            cards.nth(0).click()
            playwright.expect(page.locator("#run-select")).to_have_value("run-0")
            playwright.expect(page.locator("#active-title")).to_have_text("屏幕文字 · run-0")
            playwright.expect(page.locator("#active-range")).to_have_text(
                f"源时刻 {_timecode(first[1])}"
            )
            playwright.expect(page.locator("#active-facts")).to_have_text("建造营地")
            playwright.expect(page.locator("#current-time")).to_have_text(_timecode(first[1]))
            playwright.expect(page.locator(".screen-text-card.active")).to_have_attribute(
                "data-run", "run-0"
            )
            playwright.expect(page.locator(".screen-text-card.active")).to_have_attribute(
                "data-evidence", first[0]
            )

            with page.expect_download() as pending:
                page.locator("#download-project-search").click()
            payload = json.loads(Path(pending.value.path()).read_text(encoding="utf-8"))
            assert [row["rank"] for row in payload["candidates"]] == [1, 2, 3]
            assert len(payload["screenTextMatches"]) == 2
            assert [row["runId"] for row in payload["screenTextMatches"]] == ["run-0", "run-1"]
            for row, planted_hit, text in zip(
                payload["screenTextMatches"], (first, second), ("建造营地", "建造哨塔"), strict=True
            ):
                assert set(row) == MATCH_FIELDS
                assert row["evidenceId"] == planted_hit[0]
                assert row["timeUs"] == planted_hit[1]
                assert row["text"] == text
            assert (
                payload["screenTextDisclaimer"] == "本机识别出的文字，不是事实，也不是人工验收结果"
            )
            dumped = json.dumps(payload, ensure_ascii=False)
            assert "建造仓库" not in dumped
            assert "新证据" not in dumped

            with page.expect_download() as pending:
                page.locator("#download-project-search-csv").click()
            raw_csv = Path(pending.value.path()).read_text(encoding="utf-8-sig")
            rows = list(csv.DictReader(StringIO(raw_csv)))
            candidates = [row for row in rows if row["rowKind"] == "candidate"]
            screen_rows = [row for row in rows if row["rowKind"] == "screen-text"]
            assert len(candidates) == 3
            assert [row["runId"] for row in screen_rows] == ["run-0", "run-1"]
            assert [row["text"] for row in screen_rows] == ["建造营地", "建造哨塔"]
            assert screen_rows[0]["timeUs"] == screen_rows[1]["timeUs"] == str(first[1])
            assert screen_rows[0]["evidenceId"] == first[0]
            assert screen_rows[1]["evidenceId"] == second[0]
            assert all(row["text"] != "建造仓库" for row in rows)
        finally:
            browser.close()
    for path, snap in planted["before"].items():
        assert _snapshot(path) == snap
