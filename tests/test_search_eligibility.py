"""Search refuses coverage-gap and incomplete runs before ranking."""

from __future__ import annotations

import asyncio

import pytest
from test_sqlite_store import CONFIG, bundle_fixture

from gamingcreator.application.retrieval import load_searchable_timeline
from gamingcreator.application.storage import RunStatus
from gamingcreator.cli.main import execute_project_search, execute_search
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


async def _failed_coverage_gap_project(root):
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
    return project


def test_load_searchable_timeline_refuses_coverage_gap(tmp_path):
    async def scenario():
        project = await _failed_coverage_gap_project(tmp_path)
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            with pytest.raises(AppError) as refused:
                await load_searchable_timeline(store, "run-gap")
            assert refused.value.code == "retrieval.coverage_gap"
            assert "覆盖缺口" in refused.value.message
        finally:
            await store.close()

    asyncio.run(scenario())


def test_execute_search_refuses_coverage_gap(tmp_path):
    async def scenario():
        project = await _failed_coverage_gap_project(tmp_path)
        with pytest.raises(AppError) as refused:
            await execute_search(project, "run-gap", "跳跃", tmp_path, mode="lexical")
        assert refused.value.code == "retrieval.coverage_gap"

    asyncio.run(scenario())


def test_execute_project_search_refuses_coverage_gap(tmp_path):
    async def scenario():
        project = await _failed_coverage_gap_project(tmp_path)
        with pytest.raises(AppError) as refused:
            await execute_project_search(project, ["run-gap"], "跳跃", tmp_path, mode="lexical")
        assert refused.value.code == "retrieval.coverage_gap"

    asyncio.run(scenario())


def test_load_searchable_timeline_refuses_pending(tmp_path):
    async def scenario():
        bundle = bundle_fixture(tmp_path, run_id="run-pending")
        project = tmp_path / "project"
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-pending", bundle.asset, CONFIG)
            await store.begin_stage("run-pending", "media", bundle.asset.sha256)
            await store.persist_media_bundle("run-pending", bundle)
            await store.finish_media_preparation("run-pending")
        finally:
            await store.close()
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            with pytest.raises(AppError) as refused:
                await load_searchable_timeline(store, "run-pending")
            assert refused.value.code == "storage.run_incomplete"
            assert "已完成" in refused.value.message
        finally:
            await store.close()

    asyncio.run(scenario())
