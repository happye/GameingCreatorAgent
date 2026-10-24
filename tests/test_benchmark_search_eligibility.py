"""Benchmark / bind / detail-match refuse coverage-gap runs like NL search."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from test_sqlite_store import CONFIG, bundle_fixture

from gamingcreator.application.storage import RunStatus
from gamingcreator.cli.main import execute_benchmark, execute_detail_match
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


async def _gap_project(root: Path):
    bundle = bundle_fixture(root, run_id="run-gap")
    project = root / "project"
    store = await SqliteTimelineStore.open(project)
    try:
        await store.create_run("run-gap", bundle.asset, CONFIG)
        await store.begin_stage("run-gap", "media", bundle.asset.sha256)
        await store.persist_media_bundle("run-gap", bundle)
        await store.finish_media_preparation("run-gap")
        await store.stop_run("run-gap", RunStatus.FAILED, "analysis.coverage_gap")
    finally:
        await store.close()
    return project, bundle


def _constraint(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "actor-detail-query-schema-v1",
                "version": "actor-detail-query-v1",
                "vocabularyVersion": "actor-detail-vocabulary-v1",
                "actorAll": [{"kind": "hair_color", "value": "white", "partGroup": "hair"}],
                "environmentAll": [],
            }
        ),
        encoding="utf-8",
    )


def test_execute_detail_match_refuses_coverage_gap(tmp_path: Path):
    async def scenario():
        project, _ = await _gap_project(tmp_path)
        constraint = tmp_path / "constraint.json"
        _constraint(constraint)
        with pytest.raises(AppError) as refused:
            await execute_detail_match(project, "run-gap", "event-1", constraint)
        assert refused.value.code == "retrieval.coverage_gap"
        assert "覆盖缺口" in refused.value.message

    asyncio.run(scenario())


def test_execute_benchmark_refuses_coverage_gap(tmp_path: Path):
    from test_benchmark import document

    async def scenario():
        project, bundle = await _gap_project(tmp_path)
        asset = bundle.asset
        raw = document()
        raw["media"] = [
            {
                "mediaId": asset.media_id,
                "runId": "run-gap",
                "sha256": asset.sha256,
                "durationUs": asset.duration_us,
            }
        ]
        raw["queries"][0]["mediaId"] = asset.media_id
        raw["queries"][0]["runId"] = "run-gap"
        input_path = tmp_path / "benchmark.json"
        output_path = tmp_path / "out.json"
        input_path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(AppError) as refused:
            await execute_benchmark(project, input_path, output_path, tmp_path, mode="lexical")
        assert refused.value.code == "retrieval.coverage_gap"
        assert "覆盖缺口" in refused.value.message

    asyncio.run(scenario())


def test_cli_benchmark_bind_detail_paths_use_searchable_gate():
    source = Path("src/gamingcreator/cli/main.py").read_text(encoding="utf-8")
    marker = chr(10) + "async def "
    for name in ("execute_benchmark", "execute_bind_benchmark", "execute_detail_match"):
        start = source.find(f"async def {name}")
        end = source.find(marker, start + 10)
        chunk = source[start:end]
        assert "load_searchable_timeline(store," in chunk
        assert "store.load_completed_timeline" not in chunk
