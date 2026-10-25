"""TD005: one workbench open hashes every artifact exactly once, and still every time."""

import asyncio
import os
from collections import Counter
from dataclasses import replace

import pytest
from test_detail_inspection import refuse_sends, seed_project

from gamingcreator.cli.main import execute_search
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import sqlite_store
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.service import inspect_run


@pytest.fixture
def hashed(monkeypatch):
    counts: Counter[str] = Counter()
    original = sqlite_store._hash

    def counting(path):
        counts[str(path)] += 1
        return original(path)

    monkeypatch.setattr(sqlite_store, "_hash", counting)
    return counts


@pytest.mark.parametrize("query", ["", "白色"])
def test_one_open_hashes_each_artifact_once(tmp_path, monkeypatch, hashed, query):
    project, _, _ = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    hashed.clear()  # seeding hashes too; count only the open itself
    asyncio.run(inspect_run(project, "run-1", query, tmp_path, mode="lexical"))
    assert hashed and set(hashed.values()) == {1}  # was 3 per file with a query


def test_every_open_still_detects_a_same_size_rewrite_with_restored_time(
    tmp_path, monkeypatch, hashed
):
    project, _, timeline = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    asyncio.run(inspect_run(project, "run-1", "白色", tmp_path, mode="lexical"))
    evidence = next(iter(timeline.evidence)).artifact_path
    status = evidence.stat()
    data = bytearray(evidence.read_bytes())
    data[-1] ^= 0xFF
    evidence.write_bytes(bytes(data))
    os.utime(evidence, ns=(status.st_atime_ns, status.st_mtime_ns))
    for query in ("", "白色"):
        with pytest.raises(AppError) as refused:
            asyncio.run(inspect_run(project, "run-1", query, tmp_path, mode="lexical"))
        assert refused.value.code == "storage.integrity"


def test_reuse_requires_the_identical_completed_run_record(tmp_path, monkeypatch, hashed):
    project, _, _ = seed_project(tmp_path)
    refuse_sends(monkeypatch)

    async def verified():
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await store.load_timeline("run-1")
        finally:
            await store.close()

    timeline = asyncio.run(verified())
    hashed.clear()
    asyncio.run(
        execute_search(
            project, "run-1", "白色", tmp_path, mode="lexical", verified_timeline=timeline
        )
    )
    assert not hashed  # identical record: the just-verified timeline is reused
    stale = replace(timeline, run=replace(timeline.run, config_hash="0" * 64))
    asyncio.run(
        execute_search(project, "run-1", "白色", tmp_path, mode="lexical", verified_timeline=stale)
    )
    assert hashed and set(hashed.values()) == {1}  # mismatch: full load re-verifies


def test_evidence_references_use_the_paths_that_were_hashed(tmp_path, hashed):
    project, _, _ = seed_project(tmp_path)

    async def load():
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await store.load_timeline("run-1")
        finally:
            await store.close()

    hashed.clear()
    timeline = asyncio.run(load())
    assert {str(item.artifact_path) for item in timeline.evidence} <= set(hashed)
