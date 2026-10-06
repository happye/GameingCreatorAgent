"""A long synthetic timeline searches atomically across local worker boundaries."""

import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import replace

import pytest
from test_local_embeddings import install_fake
from test_local_embeddings import provider as provider
from test_sqlite_store import CONFIG, bundle_fixture, event_fixture

from gamingcreator.application.media import SamplingParameters
from gamingcreator.cli.main import execute_search
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.local_embeddings import LocalEmbeddingProvider
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


@pytest.mark.parametrize("mode", ["semantic", "hybrid"])
def test_long_search_failure_resume_hot_cache_and_second_process(
    tmp_path, provider, monkeypatch, mode
):
    calls = []

    def fail_second_batch(response):
        if len(calls) == 2:
            response["vectors"][-1] = [0.0] * 384

    install_fake(monkeypatch, calls, malformed=fail_second_batch)
    monkeypatch.setattr(
        LocalEmbeddingProvider, "from_manifest", staticmethod(lambda repository: provider)
    )
    bundle = bundle_fixture(tmp_path)
    bundle = replace(
        bundle,
        images=tuple(
            replace(
                bundle.images[0],
                evidence_id=f"run-1:image-{index:04}",
                pts=1000 + index,
                source_time=SourceInstant(index * 1000, bundle.asset.duration_us),
            )
            for index in range(1280)
        ),
    )
    write_manifest(bundle, SamplingParameters())
    events = tuple(
        replace(
            event_fixture(bundle, event_id=f"event-{index:04}"),
            source_range=SourceRange(index * 1000, index * 1000 + 1000, bundle.asset.duration_us),
            observable_facts=(f"building shelter observation {index}",),
            evidence_ids=(bundle.images[index].evidence_id,),
        )
        for index in range(1280)
    )
    project = tmp_path / "project"

    def counts():
        uri = "file:" + (project / "timeline.sqlite3").resolve().as_posix() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            return tuple(
                connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("embeddings", "retrieval_runs", "semantic_events")
            )

    async def scenario():
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-1", bundle.asset, CONFIG)
            await store.begin_stage("run-1", "media", bundle.asset.sha256)
            await store.persist_media_bundle("run-1", bundle)
            await store.begin_stage("run-1", "vision", bundle.asset.sha256)
            await store.persist_timeline(
                "run-1", "vision", events, (), hashlib.sha256(b"long fixture").hexdigest()
            )
            await store.complete_run("run-1")
        finally:
            await store.close()
        with pytest.raises(AppError) as failed:
            await execute_search(project, "run-1", "building shelter", tmp_path, mode=mode)
        assert failed.value.code == "embedding.response_invalid"
        assert counts() == (0, 0, 1280)
        assert not (project / "runs/run-1/searches").exists()
        assert [len(batch["texts"]) for batch in calls] == [1024, 257]

        install_fake(monkeypatch, calls)
        result = await execute_search(project, "run-1", "building shelter", tmp_path, mode=mode)
        assert counts() == (1280, 1, 1280)
        assert len(calls) == 3 and len(calls[-1]["texts"]) == 257
        assert len(result["candidates"]) == 10
        assert len({item["candidateId"] for item in result["candidates"]}) == 10
        warm = await execute_search(project, "run-1", "building shelter", tmp_path, mode=mode)
        assert warm["candidates"] == result["candidates"] and len(calls) == 3
        assert counts() == (1280, 2, 1280)
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            assert (await store.load_completed_timeline("run-1")).events == events
            reloaded = await store.load_retrieval(result["retrievalId"])
            assert tuple(hit["candidate_id"] for hit in reloaded["hits"]) == tuple(
                item["candidateId"] for item in result["candidates"]
            )
        finally:
            await store.close()

    asyncio.run(scenario())
    script = """
import json, sqlite3, sys
from contextlib import closing
with closing(sqlite3.connect('file:' + sys.argv[1] + '?mode=ro', uri=True)) as db:
    result = {'counts': [db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
        for name in ('embeddings', 'retrieval_runs', 'semantic_events')],
        'foreignKeys': db.execute('PRAGMA foreign_key_check').fetchall(),
        'last': db.execute('SELECT subject_id, text_hash FROM embeddings WHERE subject_id=?',
            ('event-1279',)).fetchone()}
    print(json.dumps(result))
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", script, (project / "timeline.sqlite3").resolve().as_posix()],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    saved = json.loads(child.stdout)
    assert saved["counts"] == [1280, 2, 1280] and saved["foreignKeys"] == []
    assert saved["last"] == [
        "event-1279",
        hashlib.sha256(b"passage: building shelter observation 1279\nfixture-mechanic").hexdigest(),
    ]
