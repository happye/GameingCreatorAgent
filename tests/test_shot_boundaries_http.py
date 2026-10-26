"""Workbench shot reports: explicit local scan, cache outside the project, no pass claims."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_detail_query import snapshot
from test_inspection_http import get, workspace
from test_material_tasks import seed_tasks
from test_shot_boundaries import FakeDetector

from gamingcreator.application.shot_boundaries import ShotDetectorIdentity
from gamingcreator.cli.shot_boundaries import execute_detect_shots
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.shots import shot_cache_path

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"


def post(base: str, path: str, document: object) -> tuple[int, dict, bytes]:
    return get(
        base,
        path,
        data=json.dumps(document, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def test_scan_is_explicit_cached_outside_the_project_and_tied_to_identity(tmp_path, monkeypatch):
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    reference = project.relative_to(tmp_path).as_posix()
    fake = FakeDetector()
    monkeypatch.setattr("gamingcreator.ui.server.FfmpegShotDetector", lambda repository: fake)
    before = snapshot(project)
    query = "/api/shot-boundaries?" + urlencode({"project": reference, "run": "run-000"})
    with workspace(tmp_path) as base:
        status, _, raw = get(base, query)
        assert status == 200 and json.loads(raw)["available"] is False and fake.calls == 0
        status, _, raw = post(base, "/api/detect-shots", {"project": reference, "run": "run-000"})
        scanned = json.loads(raw)
        assert status == 200 and fake.calls == 1
        assert scanned["available"] is True and scanned["project"] == reference
        assert scanned["summary"]["cuts"] == 1 and scanned["readOnly"] is True
        assert scanned["paidRequests"] == 0 and scanned["humanReviewed"] is False
        cache = shot_cache_path(tmp_path, project, "run-000")
        assert cache.is_file() and project not in cache.parents
        status, _, raw = get(base, query)
        cached = json.loads(raw)
        assert status == 200 and cached == scanned and fake.calls == 1
        # A different detector identity no longer matches the saved report.
        fake.identity = ShotDetectorIdentity("other", "other-filter", 10, "0.10")
        assert json.loads(get(base, query)[2])["available"] is False
        for bad in (
            {"project": reference},
            {"project": reference, "run": ""},
            {"project": reference, "run": "run-000", "extra": 1},
        ):
            assert post(base, "/api/detect-shots", bad)[0] == 400
        missing = post(base, "/api/detect-shots", {"project": reference, "run": "nope"})
        assert missing[0] == 404
    assert snapshot(project) == before


def test_cached_report_goes_stale_when_the_analysis_moves_on(tmp_path, monkeypatch):
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    reference = project.relative_to(tmp_path).as_posix()
    fake = FakeDetector()
    monkeypatch.setattr("gamingcreator.ui.server.FfmpegShotDetector", lambda repository: fake)
    query = "/api/shot-boundaries?" + urlencode({"project": reference, "run": "run-000"})
    with workspace(tmp_path) as base:
        post(base, "/api/detect-shots", {"project": reference, "run": "run-000"})
        assert json.loads(get(base, query)[2])["available"] is True

        async def advance():
            store = await SqliteTimelineStore.open(project)
            try:
                await store.begin_stage("run-000", "vision-000000", "c" * 64)
            finally:
                await store.close()

        asyncio.run(advance())
        assert json.loads(get(base, query)[2])["available"] is False


def test_report_is_refused_when_the_target_appears_during_the_scan(tmp_path):
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    output = tmp_path / "reports" / "late.json"

    class LateWriter(FakeDetector):
        async def samples(self, media, context):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("someone else", encoding="utf-8")
            return await super().samples(media, context)

    with pytest.raises(AppError, match="新的文件"):
        asyncio.run(execute_detect_shots(project, "run-000", output, LateWriter()))
    assert output.read_text(encoding="utf-8") == "someone else"
    assert [item.name for item in output.parent.iterdir()] == ["late.json"]


def test_workbench_static_requests_scan_only_on_click():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "shot-boundaries-v1" in js and "/api/detect-shots" in js
    assert 'id="detect-shots"' in html and 'id="shot-summary"' in html
    # Loading a run only reads the cached report; scanning needs the button.
    assert js.count('"/api/detect-shots"') == 1
