"""Saved task progress and costs are readable without media/model work or recovery."""

import asyncio
import hashlib
import json
from dataclasses import replace
from decimal import Decimal

import pytest
from test_sqlite_store import bundle_fixture

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.providers import CostStatus, InvocationMetadata, ProviderUsage
from gamingcreator.application.storage import (
    InvocationStatus,
    RunConfiguration,
    RunStatus,
    RunTaskSnapshot,
    StageCheckpoint,
    StageStatus,
    StoredInvocation,
    StoredRun,
)
from gamingcreator.application.tasks import task_payload, tasks_payload
from gamingcreator.cli.main import execute_tasks
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import sqlite_store
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

PIPELINE = "phase0-analyze-v2"
CONFIG = RunConfiguration(
    AnalysisConfig("deepseek", "deepseek-flash", 50, 100, 2, "deepseek-flash-cny-2026-10-04"),
    Decimal(5),
    PIPELINE,
    hashlib.sha256(PIPELINE.encode()).hexdigest(),
    ("media", "asr", "vision"),
)


def snapshot_fixture(
    tmp_path,
    *,
    status=RunStatus.PENDING,
    stages=(("media", StageStatus.COMPLETED),),
    invocations=(),
    images=13,
):
    bundle = bundle_fixture(tmp_path)
    run = StoredRun("run-1", bundle.asset, CONFIG, "f" * 64, status, None)
    checkpoints = tuple(
        StageCheckpoint(
            run.run_id,
            name,
            value,
            bundle.asset.sha256,
            bundle.asset.sha256 if value == StageStatus.COMPLETED else None,
            1,
            None,
        )
        for name, value in stages
    )
    return RunTaskSnapshot(run, checkpoints, invocations, images, 0, 0, 0)


def invocation(
    identifier="attempt-1",
    *,
    cost=None,
    price="price-v1",
    status=InvocationStatus.INTERRUPTED,
    stage="vision-000001",
    details=None,
    provider="deepseek",
):
    usage = (
        ProviderUsage()
        if cost is None
        else ProviderUsage(
            original_cost=cost, currency="CNY", cost_cny=cost, cost_status=CostStatus.ESTIMATED
        )
    )
    metadata = InvocationMetadata(
        provider,
        "model",
        None,
        None,
        "prompt",
        "schema",
        1,
        usage,
        price_version=price,
        execution_details=json.dumps({"inputFrames": 5, "reservationCny": "2"})
        if details is None
        else details,
    )
    return StoredInvocation(identifier, "run-1", stage, identifier, status, metadata, None)


@pytest.mark.parametrize(
    "status,stages,phase,action",
    [
        (RunStatus.PENDING, (), "preparation_incomplete", "prepare_media"),
        (
            RunStatus.FAILED,
            (("media", StageStatus.FAILED),),
            "preparation_incomplete",
            "prepare_media",
        ),
        (
            RunStatus.CANCELLED,
            (("media", StageStatus.CANCELLED),),
            "preparation_incomplete",
            "prepare_media",
        ),
        (RunStatus.PENDING, (("media", StageStatus.COMPLETED),), "media_prepared", "analyze"),
        (RunStatus.RUNNING, (("media", StageStatus.COMPLETED),), "media_prepared", "analyze"),
        (
            RunStatus.INTERRUPTED,
            (("media", StageStatus.COMPLETED), ("asr", StageStatus.INTERRUPTED)),
            "analysis_incomplete",
            "analyze",
        ),
        (
            RunStatus.COMPLETED,
            (
                ("media", StageStatus.COMPLETED),
                ("asr", StageStatus.COMPLETED),
                ("vision", StageStatus.COMPLETED),
            ),
            "completed",
            None,
        ),
    ],
)
def test_phase_and_next_action_follow_saved_checkpoints(tmp_path, status, stages, phase, action):
    snapshot = snapshot_fixture(tmp_path, status=status, stages=stages)
    payload = task_payload(snapshot)
    assert payload["phase"] == phase and payload["nextAction"] == action
    assert payload["runStatus"] == status and payload["integrityCheck"] == "not_requested"
    assert payload["configuration"]["maxCostCny"] == "5" and payload["configHash"] == "f" * 64
    assert payload["humanQualityGate"] is None


def test_child_window_completion_does_not_count_as_complete_parent_stage(tmp_path):
    snapshot = snapshot_fixture(
        tmp_path,
        stages=(
            ("media", StageStatus.COMPLETED),
            ("asr", StageStatus.COMPLETED),
            ("vision", StageStatus.RUNNING),
            ("vision-000000", StageStatus.COMPLETED),
            ("vision-000001", StageStatus.FAILED),
        ),
    )
    progress = task_payload(snapshot)["progress"]
    assert progress == {
        "requiredCompleted": 2,
        "requiredTotal": 3,
        "completedVisionWindows": 1,
        "plannedWindows": 3,
        "plannedUploadFrames": 15,
        "coverageFits": True,
    }
    limited = replace(
        snapshot,
        run=replace(
            snapshot.run,
            configuration=replace(CONFIG, analysis=replace(CONFIG.analysis, max_requests=2)),
        ),
    )
    assert "coverage_limit" in task_payload(limited)["continuationBlockers"]


def test_known_cost_and_unknown_reservation_both_consume_original_budget(tmp_path):
    unknown = invocation()
    settled = invocation("attempt-2", cost=Decimal("0.10"), status=InvocationStatus.COMPLETED)
    snapshot = snapshot_fixture(tmp_path, invocations=(unknown, settled))
    payload = task_payload(snapshot)
    cost = payload["cost"]
    assert cost["knownCny"] == "0.10" and cost["unknownAttempts"] == 1
    assert cost["unknownReservationCny"] == "2" and cost["committedCny"] == "2.10"
    assert cost["remainingCny"] == "2.90" and cost["remoteFrames"] == 10
    assert payload["requiresRetryConfirmation"] is True
    assert "explicit_retry_required" in payload["continuationBlockers"]
    assert unknown.metadata.usage.cost_cny is None


@pytest.mark.parametrize(
    "details",
    [
        "{}",
        "{bad}",
        "[]",
        '{"inputFrames":true,"reservationCny":"2"}',
        '{"inputFrames":5,"reservationCny":2}',
        '{"inputFrames":5,"reservationCny":"NaN"}',
        '{"inputFrames":5,"reservationCny":"-1"}',
    ],
)
def test_missing_or_invalid_old_reservation_never_becomes_zero_balance(tmp_path, details):
    payload = task_payload(
        snapshot_fixture(tmp_path, invocations=(invocation(details=details), invocation("good")))
    )
    assert payload["cost"]["unknownAttempts"] == 2
    assert payload["cost"]["knownUnknownReservationCny"] == "2"
    for name in ("unknownReservationCny", "committedCny", "remainingCny", "remoteFrames"):
        assert payload["cost"][name] is None
    assert payload["cost"]["reservationRecordsComplete"] is False


def test_unpriced_provider_and_missing_price_do_not_become_known_cost(tmp_path):
    payload = task_payload(
        snapshot_fixture(
            tmp_path,
            invocations=(
                invocation(cost=Decimal("0.1"), price=None),
                invocation("local", provider="local-asr"),
            ),
        )
    )
    assert payload["cost"]["knownCny"] == "0" and payload["cost"]["unknownAttempts"] == 2
    assert payload["cost"]["unknownReservationCny"] is None


@pytest.mark.parametrize("parent_complete,attempt_complete", [(True, False), (False, True)])
def test_committed_checkpoints_do_not_require_replaying_finished_remote_work(
    tmp_path, parent_complete, attempt_complete
):
    stages = [("media", StageStatus.COMPLETED), ("asr", StageStatus.COMPLETED)]
    stages.append(("vision" if parent_complete else "vision-000001", StageStatus.COMPLETED))
    snapshot = snapshot_fixture(tmp_path, stages=stages, invocations=(invocation(),))
    assert task_payload(snapshot)["requiresRetryConfirmation"] is False
    assert task_payload(snapshot)["cost"]["unknownReservationCny"] == "2"


def test_legacy_stopped_and_damaged_material_are_not_offered_as_safe_replay(tmp_path):
    snapshot = snapshot_fixture(tmp_path, status=RunStatus.FAILED)
    legacy = replace(
        snapshot,
        run=replace(
            snapshot.run,
            configuration=replace(CONFIG, analysis=replace(CONFIG.analysis, schema_version=1)),
        ),
    )
    assert "legacy_stopped" in task_payload(legacy)["continuationBlockers"]
    damaged = replace(snapshot, run=replace(snapshot.run, error_code="storage.integrity"))
    assert "material_integrity" in task_payload(damaged)["continuationBlockers"]


def seed_tasks(root, count=3):
    root.mkdir(parents=True, exist_ok=True)
    bundles = [bundle_fixture(root, run_id=f"run-{index:03d}") for index in range(count)]
    project = root / "project"

    async def build():
        store = await SqliteTimelineStore.open(project)
        try:
            for index, bundle in enumerate(bundles):
                run_id = f"run-{index:03d}"
                await store.create_run(run_id, bundle.asset, CONFIG)
                await store.begin_stage(run_id, "media", bundle.asset.sha256)
                await store.persist_media_bundle(run_id, bundle)
                await store.finish_media_preparation(run_id)
        finally:
            await store.close()

    asyncio.run(build())
    return project, bundles


def test_metadata_pages_and_single_task_read_do_not_hash_load_recover_or_write(
    tmp_path, monkeypatch
):
    project, bundles = seed_tasks(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Task inventory performed media/model/recovery work")

    for name in ("_hash",):
        monkeypatch.setattr(sqlite_store, name, forbidden)
    for name in ("_integrity", "load_media_bundle", "load_timeline", "recover", "prepare_resume"):
        monkeypatch.setattr(SqliteTimelineStore, name, forbidden)
    before = (project / "timeline.sqlite3").read_bytes()

    async def read():
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            first = await tasks_payload(store, limit=2)
            last = await tasks_payload(store, limit=2, offset=2)
            assert first["total"] == last["total"] == 3 and first["hasMore"] and not last["hasMore"]
            assert [row["runId"] for row in first["tasks"] + last["tasks"]] == [
                "run-002",
                "run-001",
                "run-000",
            ]
            single = await tasks_payload(store, run_id="run-000")
            assert single["total"] == 1 and single["tasks"][0]["imageCount"] == 1
            assert not single["hasMore"]
        finally:
            await store.close()
        output = await execute_tasks(project, run_id="run-000")
        assert output["tasks"][0]["nextCommand"][-2:] == ["--resume", "run-000"]
        assert output["tasks"][0]["nextCommand"][1] == "analyze"

    asyncio.run(read())
    assert (project / "timeline.sqlite3").read_bytes() == before
    assert bundles[0].asset.source_path.read_bytes() == b"not a real video: storage fixture"


@pytest.mark.parametrize(
    "parameters",
    [
        {"limit": 0},
        {"limit": 201},
        {"limit": True},
        {"offset": -1},
        {"offset": 1000001},
        {"run_id": ""},
        {"run_id": "run-000", "offset": 1},
    ],
)
def test_invalid_paging_is_rejected_before_any_store_call(parameters):
    class UnusedStore:
        async def load_task_page(self, **kwargs):
            raise AssertionError("Invalid task query reached storage")

    with pytest.raises(AppError) as refused:
        asyncio.run(tasks_payload(UnusedStore(), **parameters))
    assert refused.value.code == "input.tasks"
