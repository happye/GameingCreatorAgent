"""Batch continuation keeps allocated tasks and never enters model work."""

import asyncio
import hashlib
import json
import os
import pickle
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from test_analyze import asr_metadata
from test_analyze_v2 import window_bundle

from gamingcreator.cli import main as cli
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.media_batch_files import MediaBatchFiles
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


class CopyMedia:
    def __init__(self, bundles):
        self.bundles = bundles
        self.probes = []
        self.extractions = []
        self.bad = set()
        self.cancel = set()
        self.probe_delay = 0

    async def probe(self, source, context):
        self.probes.append(source)
        await asyncio.sleep(self.probe_delay)
        if source in self.bad:
            raise AppError("input.media_decode", "测试坏录像。", ExitCode.INPUT)
        return self.bundles[source].asset

    async def preprocess(self, source, output, parameters, context):
        self.extractions.append(source)
        if source in self.cancel:
            raise asyncio.CancelledError
        original = self.bundles[source]
        output.mkdir(parents=True, exist_ok=True)
        images = []
        for index, old in enumerate(original.images):
            path = output / f"frame-{index:06d}.jpg"
            path.write_bytes(old.path.read_bytes())
            images.append(
                replace(
                    old,
                    path=path,
                    evidence_id=f"{context.run_id}:{original.asset.media_id}:image:{index:06d}",
                )
            )
        bundle = replace(
            original, images=tuple(images), manifest_path=output / "media-manifest.json"
        )
        write_manifest(bundle, parameters)
        return bundle


def forbidden(*args, **kwargs):
    pytest.fail("Offline preparation must not enter models, search or budgeting.")


@pytest.fixture
def batch(tmp_path, monkeypatch):
    bundles = {}
    for index in range(3):
        root = tmp_path / f"录像 {index}"
        root.mkdir()
        bundle, _, source = window_bundle(root)
        source.write_bytes(f"source-{index}".encode())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        bundles[source.resolve()] = replace(
            bundle, asset=replace(bundle.asset, media_id=digest, sha256=digest)
        )
    input_path = tmp_path / "录像清单.json"
    input_path.write_text(
        json.dumps(
            {
                "schemaVersion": "media-batch-input-v1",
                "items": [
                    {"id": f"录像{index}", "path": str(path.relative_to(tmp_path))}
                    for index, path in enumerate(bundles)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )
    config_path = tmp_path / "配置.json"
    config_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "vision": {
                    "provider": "deepseek",
                    "model": "deepseek-flash",
                    "priceVersion": "deepseek-flash-cny-2026-10-04",
                    "maxOutputTokens": 768,
                },
                "limits": {"maxRequests": 20, "maxInputFrames": 100},
                "sampling": {"intervalMs": 1000, "windowFrames": 5, "windowOverlap": 1},
                "asr": {"language": "zh"},
            }
        ),
        encoding="utf-8",
    )
    media = CopyMedia(bundles)
    monkeypatch.setattr(cli, "FfmpegMediaProcessor", lambda repository: media)
    for name in ("LocalAsrProvider", "HttpxVisionTransport", "execute_search", "BudgetLedger"):
        monkeypatch.setattr(cli, name, forbidden)
    project = tmp_path / "批次项目"

    async def execute(*, resume=None, **kwargs):
        if resume is None:
            kwargs = (
                dict(input_path=input_path, config_path=config_path, max_cost_cny="1.25") | kwargs
            )
        return await cli.execute_prepare_media_batch(project, tmp_path, resume=resume, **kwargs)

    return project, input_path, config_path, media, execute


async def task_snapshot(project, rows):
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        return tuple(
            [
                (
                    await store.load_run(row["runId"]),
                    await store.load_checkpoints(row["runId"]),
                    await store.load_invocations(row["runId"]),
                )
                for row in rows
            ]
        )
    finally:
        await store.close()


def test_bad_middle_item_continues_and_repaired_item_reuses_frozen_batch(batch, monkeypatch):
    project, input_path, config_path, media, execute = batch

    async def scenario():
        sources = list(media.bundles)
        media.bad.add(sources[1])
        first = await execute()
        assert first["status"] == "partial" and first["exitCode"] == 2
        assert [row["status"] for row in first["items"]] == ["prepared", "failed", "prepared"]
        files = MediaBatchFiles(project, first["batchId"])
        plan, state, _ = files.load()
        assert [item.run_id for item in plan.items] == [row["runId"] for row in first["items"]]
        assert state["items"] == first["items"]
        assert plan.max_cost_cny.as_tuple().digits == (1, 2, 5)
        input_path.unlink()
        config_path.unlink()
        media.bad.clear()
        resumed = await execute(resume=first["batchId"])
        assert resumed["status"] == "finished" and resumed["exitCode"] == 0
        assert [row["runId"] for row in resumed["items"]] == [
            row["runId"] for row in first["items"]
        ]
        assert resumed["reusedPreparedTasks"] == 2
        assert media.extractions == [sources[0], sources[2], sources[1]]
        before = await task_snapshot(project, resumed["items"])
        monkeypatch.setattr(media, "probe", forbidden)
        monkeypatch.setattr(media, "preprocess", forbidden)
        final = await execute(resume=first["batchId"])
        assert final["reusedPreparedTasks"] == 3
        assert before == await task_snapshot(project, final["items"])
        assert all(
            str(run.status) == "pending" and not invocations for run, _, invocations in before
        )
        assert all(run.configuration.analysis == plan.config for run, _, _ in before)
        assert all(run.configuration.max_cost_cny == plan.max_cost_cny for run, _, _ in before)
        assert all(len(stages) == 1 and stages[0].attempt == 1 for _, stages, _ in before)
        assert final["modelInvocations"] == final["newReservations"] == 0

    asyncio.run(scenario())


def test_crash_between_task_commit_and_batch_checkpoint_does_not_duplicate_task(batch, monkeypatch):
    project, _, _, media, execute = batch
    original = MediaBatchFiles.save

    def interrupt(self, state, plan, digest):
        if state["items"][0]["status"] == "prepared":
            raise SystemExit("simulated process loss after task commit")
        return original(self, state, plan, digest)

    async def scenario():
        monkeypatch.setattr(MediaBatchFiles, "save", interrupt)
        with pytest.raises(SystemExit):
            await execute()
        directory = next((project / "media-batches").iterdir())
        files = MediaBatchFiles(project, directory.name)
        plan, state, _ = files.load()
        assert state["items"][0]["status"] == "running"
        monkeypatch.setattr(MediaBatchFiles, "save", original)
        result = await execute(resume=directory.name)
        assert result["reusedPreparedTasks"] == 1 and result["exitCode"] == 0
        assert [row["runId"] for row in result["items"]] == [item.run_id for item in plan.items]
        assert len(media.extractions) == 3
        assert all(
            not invocations for _, _, invocations in await task_snapshot(project, result["items"])
        )

    asyncio.run(scenario())


def test_cancel_stops_remaining_items_and_explicit_resume_keeps_ids(batch):
    project, _, _, media, execute = batch

    async def scenario():
        media.cancel.add(list(media.bundles)[1])
        first = await execute()
        assert first["exitCode"] == 130
        assert [row["status"] for row in first["items"]] == ["prepared", "cancelled", "pending"]
        media.cancel.clear()
        result = await execute(resume=first["batchId"])
        assert result["exitCode"] == 0 and result["reusedPreparedTasks"] == 1
        assert [row["runId"] for row in result["items"]] == [row["runId"] for row in first["items"]]
        assert [
            stages[0].attempt for _, stages, _ in await task_snapshot(project, result["items"])
        ] == [1, 2, 1]

    asyncio.run(scenario())


def test_started_analysis_is_reported_without_touching_stage_or_unknown_invocation(batch):
    project, _, _, _, execute = batch

    async def scenario():
        first = await execute()
        identifier = first["items"][1]["runId"]
        store = await SqliteTimelineStore.open(project)
        try:
            stored = await store.load_run(identifier)
            await store.begin_stage(identifier, "asr", stored.asset.sha256)
            await store.begin_invocation(
                "unknown-bill",
                identifier,
                "asr",
                "asr-logical",
                replace(asr_metadata(), elapsed_ms=None),
            )
        finally:
            await store.close()
        before = await task_snapshot(project, first["items"])
        result = await execute(resume=first["batchId"])
        assert result["exitCode"] == 0 and result["items"][1]["status"] == "analysis_started"
        assert result["items"][1]["result"]["nextCommand"] is None
        assert before == await task_snapshot(project, first["items"])

    asyncio.run(scenario())


@pytest.mark.parametrize("changed", ["source", "frame"])
def test_changed_registered_bytes_stop_batch_without_recreating_tasks(batch, changed):
    project, _, _, _, execute = batch

    async def scenario():
        first = await execute()
        before = await task_snapshot(project, first["items"])
        if changed == "source":
            path = before[0][0].asset.source_path
        else:
            path = next((project / "runs" / first["items"][0]["runId"]).rglob("frame-*.jpg"))
        path.write_bytes(b"changed")
        result = await execute(resume=first["batchId"])
        assert result["exitCode"] == 5 and result["status"] == "stopped"
        assert result["items"][0]["status"] == "failed"
        assert result["items"][1]["verifiedThisInvocation"] is False
        assert before == await task_snapshot(project, first["items"])

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "changed", ["source-input.json", "analysis-config.json", "plan.json", "state.json"]
)
def test_corrupt_batch_records_refuse_before_media_work(batch, monkeypatch, changed):
    project, _, _, media, execute = batch

    async def scenario():
        first = await execute()
        path = project / "media-batches" / first["batchId"] / changed
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if changed == "state.json":
            data["items"][0]["runId"] = "0" * 32
        else:
            data["tampered"] = True
        path.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(media, "probe", forbidden)
        monkeypatch.setattr(media, "preprocess", forbidden)
        with pytest.raises(AppError) as refused:
            await execute(resume=first["batchId"])
        assert refused.value.exit_code == ExitCode.INPUT

    asyncio.run(scenario())


def test_missing_batch_checkpoint_recovers_committed_tasks_from_frozen_ids(batch):
    project, _, _, media, execute = batch

    async def scenario():
        first = await execute()
        (project / "media-batches" / first["batchId"] / "state.json").unlink()
        result = await execute(resume=first["batchId"])
        assert result["reusedPreparedTasks"] == 3 and len(media.extractions) == 3
        assert [row["runId"] for row in result["items"]] == [row["runId"] for row in first["items"]]

    asyncio.run(scenario())


@pytest.mark.parametrize("override", ["input_path", "config_path", "max_cost_cny"])
def test_resume_cannot_replace_frozen_input_configuration_or_limit(batch, override):
    _, input_path, config_path, _, execute = batch

    async def scenario():
        first = await execute()
        value = {"input_path": input_path, "config_path": config_path, "max_cost_cny": "9"}[
            override
        ]
        with pytest.raises(AppError):
            await execute(resume=first["batchId"], **{override: value})

    asyncio.run(scenario())


def test_coverage_is_reported_without_analysis_command_or_new_budget(batch):
    _, _, config_path, _, execute = batch
    data = json.loads(config_path.read_text())
    data["limits"]["maxRequests"] = 2
    config_path.write_text(json.dumps(data), encoding="utf-8")
    result = asyncio.run(execute())
    assert result["exitCode"] == 2
    assert all(row["status"] == "coverage_blocked" for row in result["items"])
    assert all(row["result"]["nextCommand"] is None for row in result["items"])
    assert result["newReservations"] == result["modelInvocations"] == 0


def test_per_item_deadline_includes_probe_and_can_be_explicitly_extended(batch):
    _, _, _, media, execute = batch

    async def scenario():
        media.probe_delay = 0.02
        result = await execute(timeout_seconds=0.001)
        assert result["exitCode"] == 2 and not media.extractions
        assert all(row["errorCode"] == "media.timeout" for row in result["items"])
        assert (await execute(resume=result["batchId"], timeout_seconds=5))["exitCode"] == 0

    asyncio.run(scenario())


def test_live_batch_lock_refuses_second_writer(batch):
    project, _, _, _, execute = batch

    async def scenario():
        first = await execute()
        files = MediaBatchFiles(project, first["batchId"])
        files.acquire()
        try:
            with pytest.raises(AppError) as refused:
                await execute(resume=first["batchId"])
            assert refused.value.code == "storage.writer_busy"
        finally:
            files.close()

    asyncio.run(scenario())


def test_killed_preparation_process_resumes_original_running_task(batch, tmp_path):
    project, input_path, config_path, media, execute = batch
    data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    data["items"] = data["items"][:1]
    input_path.write_text(json.dumps(data), encoding="utf-8")
    fixture_path = tmp_path / "child-bundles.pickle"
    fixture_path.write_bytes(pickle.dumps(media.bundles))
    marker = tmp_path / "child-preparing"
    program = """
import asyncio, pickle, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from test_media_batch import CopyMedia, forbidden
from gamingcreator.cli import main as cli
class WaitingMedia(CopyMedia):
    async def preprocess(self, source, output, parameters, context):
        Path(sys.argv[5]).write_text(context.run_id)
        await asyncio.Event().wait()
media = WaitingMedia(pickle.loads(Path(sys.argv[2]).read_bytes()))
cli.FfmpegMediaProcessor = lambda repository: media
cli.LocalAsrProvider = cli.HttpxVisionTransport = cli.BudgetLedger = forbidden
asyncio.run(cli.execute_prepare_media_batch(
    Path(sys.argv[3]), Path.cwd(), input_path=Path(sys.argv[4]),
    config_path=Path(sys.argv[6]), max_cost_cny='1.25'))
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-c",
            program,
            str(Path(__file__).parent),
            str(fixture_path),
            str(project),
            str(input_path),
            str(marker),
            str(config_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ | {"PYTHONUTF8": "1"},
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.025)
        assert marker.exists(), "Owned child did not reach the media stage."
        allocated = marker.read_text()
        process.kill()
        process.wait(timeout=5)
        directory = next((project / "media-batches").iterdir())
        plan, state, _ = MediaBatchFiles(project, directory.name).load()
        assert plan.items[0].run_id == allocated and state["items"][0]["status"] == "running"
        result = asyncio.run(execute(resume=directory.name))
        assert result["exitCode"] == 0 and result["items"][0]["runId"] == allocated
        snapshots = asyncio.run(task_snapshot(project, result["items"]))
        assert len(media.extractions) == 1
        assert [stages[0].attempt for _, stages, _ in snapshots] == [2]
        assert all(
            not invocations and str(run.status) == "pending" for run, _, invocations in snapshots
        )
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


@pytest.mark.parametrize("change", ["same_path", "same_id", "empty", "over_limit", "extra_field"])
def test_invalid_list_refuses_before_creating_project(batch, change):
    project, input_path, _, _, execute = batch
    data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if change == "same_path":
        data["items"][1]["path"] = data["items"][0]["path"]
    elif change == "same_id":
        data["items"][1]["id"] = data["items"][0]["id"]
    elif change == "empty":
        data["items"] = []
    elif change == "over_limit":
        data["items"] = [{"id": str(index), "path": str(index)} for index in range(101)]
    else:
        data["paid"] = True
    input_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AppError):
        asyncio.run(execute())
    assert not project.exists()
