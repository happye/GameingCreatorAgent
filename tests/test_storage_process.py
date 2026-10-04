"""Real process crashes and one-thread SQLite queue lifecycle behavior."""

import asyncio
import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from storage_process_helper import RUN_ID, fixture_asset, fixture_configuration

from gamingcreator.application.storage import RunStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

HELPER = Path(__file__).with_name("storage_process_helper.py")


def child(mode: str, project: Path, *, returncode: int = 0) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-X", "utf8", "-W", "error", str(HELPER), mode, str(project)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    assert result.returncode == returncode, result.stderr
    assert not result.stderr
    return json.loads(result.stdout) if result.stdout else {}


def test_completed_timeline_survives_second_process(tmp_path: Path) -> None:
    child("create-completed", tmp_path)
    result = child("read-completed", tmp_path)
    assert result["status"] == "completed"
    assert result["budget"] == "1.2345"
    assert result["pipelineHash"] == "a" * 64
    assert result["eventIds"] == ["event-1"]
    assert result["eventEvidence"] == [result["evidenceIds"]]
    assert result["evidenceHashesValid"] is True
    assert result["transcripts"] == ["fixture transcript"]
    assert result["checkpoints"] == {"media": "completed", "vision": "completed"}
    assert result["invocationId"] == "invocation-1"
    assert result["modelRevision"] == "fixture-revision-1"
    assert result["priceVersion"] == "fixture-prices-v1"
    assert result["actualModel"] == "fixture-resolved-model"
    assert result["cost"] == "0.01234567890123456789"
    assert result["costStatus"] == "confirmed"
    assert result["inputTokens"] == 17
    assert result["requestId"] == "request-1"


def test_process_exit_recovery_preserves_checkpoint_and_unknown_billing(tmp_path: Path) -> None:
    child("create-interrupted", tmp_path, returncode=42)
    result = child("recover", tmp_path)
    assert result["runStatus"] == "interrupted"
    assert result["interruptedRuns"] == [RUN_ID]
    assert result["interruptedStages"] == [[RUN_ID, "vision"]]
    assert result["interruptedInvocations"] == ["invocation-1"]
    assert result["integrityIssues"] == []
    assert result["invocationStatus"] == "interrupted"
    assert result["cost"] is None
    assert result["inputTokens"] is None
    assert result["outputTokens"] is None
    assert result["costStatus"] == "unverified"
    assert result["mediaImages"] == 1
    assert result["timelineError"] == "storage.run_incomplete"


def test_process_exit_rolls_back_uncommitted_sql_transaction(tmp_path: Path) -> None:
    child("create-completed", tmp_path)
    expected = child("read-completed", tmp_path)
    child("crash-transaction", tmp_path, returncode=47)
    assert child("read-completed", tmp_path) == expected


async def wait_until(predicate: Callable[[], bool], *, timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "Storage worker did not reach expected state"
        await asyncio.sleep(0.01)


def test_cancelled_caller_and_close_drain_queue_without_blocking_loop(tmp_path: Path) -> None:
    async def scenario() -> None:
        asset = fixture_asset(tmp_path)
        store = await SqliteTimelineStore.open(tmp_path)
        entered, released = threading.Event(), threading.Event()
        worker_ids: list[int] = []

        def gate() -> None:
            worker_ids.append(threading.get_ident())
            entered.set()
            assert released.wait(5), "Test did not release storage queue"

        blocker = asyncio.create_task(store._call(gate))
        pending: asyncio.Task[object] | None = None
        closer: asyncio.Task[None] | None = None
        try:
            await wait_until(entered.is_set)
            pending = asyncio.create_task(store.create_run(RUN_ID, asset, fixture_configuration()))
            # One event-loop turn submits the transaction behind the worker gate.
            await asyncio.sleep(0)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            closer = asyncio.create_task(store.close())
            await asyncio.sleep(0)
            assert not closer.done()
            # The loop still responds while close awaits an occupied worker.
            await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.2)
            closer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await closer
            with pytest.raises(AppError) as error:
                await store.load_run(RUN_ID)
            assert error.value.code == "storage.closed"
        finally:
            released.set()
            await blocker
            await asyncio.wait_for(store.close(), timeout=3)
        await wait_until(
            lambda: all(thread.ident not in worker_ids for thread in threading.enumerate())
        )
        reopened = await SqliteTimelineStore.open(tmp_path)
        try:
            run = await reopened.load_run(RUN_ID)
            assert run.status == RunStatus.PENDING
            assert run.asset == asset
            assert run.configuration == fixture_configuration()
            await reopened.begin_stage(RUN_ID, "media", asset.sha256)
            assert (await reopened.load_run(RUN_ID)).status == RunStatus.RUNNING
        finally:
            await reopened.close()

    asyncio.run(scenario())


def test_sql_failure_rolls_back_and_worker_accepts_next_request(tmp_path: Path) -> None:
    async def scenario() -> None:
        asset = fixture_asset(tmp_path)
        store = await SqliteTimelineStore.open(tmp_path)
        try:
            await store.create_run(RUN_ID, asset, fixture_configuration())

            def failing_transaction() -> None:
                with store._transaction():
                    store._db.execute(
                        "UPDATE analysis_runs SET status='failed' WHERE run_id=?", (RUN_ID,)
                    )
                    store._db.execute("INSERT INTO absent_failure_probe VALUES (1)")

            with pytest.raises(AppError) as error:
                await store._call(failing_transaction)
            assert error.value.code == "storage.database"
            assert (await store.load_run(RUN_ID)).status == RunStatus.PENDING
            await store.begin_stage(RUN_ID, "media", asset.sha256)
            assert (await store.load_run(RUN_ID)).status == RunStatus.RUNNING
        finally:
            await store.close()

    asyncio.run(scenario())
