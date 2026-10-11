"""Content isolation uses real SQLite and real parsing with offline HTTP only."""

import asyncio
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_analyze import RUN_ID, ScriptedAsr, asr_metadata, asr_result
from test_analyze_v2 import CONFIG, WindowMedia, window_bundle
from test_deepseek_vision import response_fixture

from gamingcreator.application.analysis import AnalysisPorts, resume_analysis, run_new_analysis
from gamingcreator.application.analysis_reliability import POLICY, POLICY_STAGE
from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.inputs import PreparedAnalyze
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import ProviderStatus
from gamingcreator.application.storage import RunStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.deepseek_vision import (
    DeepSeekVisionProvider,
    vision_prompt_fingerprint,
)
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


class Transport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    async def post(self, payload, timeout_seconds):
        self.calls += 1
        return self.replies.pop(0)


@pytest.mark.parametrize(
    "resume,retry,policy,accepted",
    [
        (RUN_ID, False, POLICY, True),
        (None, False, POLICY, False),
        (RUN_ID, True, POLICY, False),
        (RUN_ID, False, "wrong", False),
    ],
)
def test_cli_policy_is_explicit_resume_only(tmp_path, resume, retry, policy, accepted):
    from gamingcreator.application.inputs import AnalyzeInput, prepare_analyze
    from gamingcreator.cli.main import _parser

    class Reader:
        def validate_video(self, path):
            return path

    command = AnalyzeInput(tmp_path / "source.mp4", tmp_path, None, None, resume, retry, policy)
    if accepted:
        prepared = prepare_analyze(command, Reader())
        assert prepared.window_failure_policy == POLICY
        parsed = _parser().parse_args(
            [
                "analyze",
                str(command.video),
                "--project",
                str(tmp_path),
                "--resume",
                RUN_ID,
                "--window-failure-policy",
                POLICY,
            ]
        )
        assert parsed.window_failure_policy == POLICY
    else:
        with pytest.raises(AppError) as refused:
            prepare_analyze(command, Reader())
        assert refused.value.code == "input.window_failure_policy"


def response(*, reject=False, usage=True, end=4):
    return response_fixture(
        events=[
            {
                "startFrameId": "f0",
                "endFrameId": "f0" if reject else f"f{end}",
                "observableFacts": ["角色移动"],
                "mechanicTags": [],
                "evidenceIds": ["f0", f"f{end}"],
                "uncertainty": None,
            }
        ],
        usage={
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "prompt_cache_hit_tokens": 0,
            "total_tokens": 14,
        }
        if usage
        else None,
    )


async def failed_run(tmp_path, *, bad_reply=None, finish_crash=False, frames=5):
    bundle, project, source = window_bundle(tmp_path)
    images = []
    for index, image in enumerate(bundle.images):
        image.path.write_bytes(image.path.read_bytes()[:-2] + bytes([index]) + b"\xff\xd9")
        images.append(replace(image, sha256=hashlib.sha256(image.path.read_bytes()).hexdigest()))
    bundle = replace(bundle, images=tuple(images))
    write_manifest(bundle, SamplingParameters(max_width=512, max_frames=100))
    config = replace(
        CONFIG,
        vision_prompt_version="phase0-vision-v4",
        vision_prompt_hash=vision_prompt_fingerprint("phase0-vision-v4"),
        window_frames=frames,
    )
    store = await SqliteTimelineStore.open(project)
    transport = Transport(
        [
            response(end=frames - 1),
            bad_reply or response(reject=True, end=frames - 1),
            response(end=frames - 1),
        ]
    )
    provider = DeepSeekVisionProvider(
        transport,
        BudgetLedger(Decimal(5), 20, 100),
        None,
        store,
        price_snapshot=DEEPSEEK_FLASH_20261004,
    )
    ports = AnalysisPorts(
        WindowMedia(bundle),
        ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO)),
        provider,
        store,
        lambda request: asr_metadata(),
    )
    original_complete = store.complete_run
    if finish_crash:
        from gamingcreator.domain.errors import ExitCode

        async def interrupted(run_id):
            raise AppError("storage.injected", "offline final commit crash", ExitCode.STORAGE)

        store.complete_run = interrupted
    with pytest.raises(AppError):
        await run_new_analysis(
            PreparedAnalyze(source, project, config, Decimal(5), None),
            ports,
            bundle.asset,
            project,
            run_id=RUN_ID,
        )
    store.complete_run = original_complete
    return bundle, project, source, store, transport, ports


def test_fresh_success_unknown_model_stops_before_next_send(tmp_path):
    from gamingcreator.infrastructure.http_transport import HttpResponse

    async def scenario():
        bundle, project, source, store, transport, ports = await failed_run(tmp_path, frames=3)
        body = json.loads(response(end=2).body)
        body["model"] = "future-model"
        transport.replies = [HttpResponse(200, json.dumps(body).encode()), response(end=2)]
        try:
            with pytest.raises(AppError) as stopped:
                await resume_analysis(
                    PreparedAnalyze(
                        source, project, None, None, RUN_ID, window_failure_policy=POLICY
                    ),
                    store,
                    project,
                    ports,
                )
            assert stopped.value.code == "analysis.isolation_ineligible"
            assert transport.calls == 3 and len(transport.replies) == 1
            rows = await store.load_checkpoints(RUN_ID)
            assert not any(
                row.stage_id == "vision-000002" and row.status.value == "completed" for row in rows
            )
            assert not any(row.stage_id == "vision-000003" for row in rows)
            attempts = await store.load_invocations(RUN_ID)
            latest = next(item for item in attempts if item.stage_id == "vision-000002")
            assert (
                latest.metadata.actual_model == "future-model"
                and latest.metadata.usage.cost_cny is None
            )
            assert (await store.load_run(RUN_ID)).status == RunStatus.FAILED
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_policy_registration_crash_is_atomic_and_resumable(tmp_path, monkeypatch, point):
    from contextlib import contextmanager

    from gamingcreator.application.analysis_reliability import policy_hash
    from gamingcreator.domain.errors import ExitCode

    async def scenario():
        bundle, project, source, store, transport, ports = await failed_run(tmp_path)
        original = store._transaction

        @contextmanager
        def crashing():
            with original():
                yield
                if point == "before_commit":
                    raise AppError(
                        "storage.injected", "offline transaction crash", ExitCode.STORAGE
                    )
            if point == "after_commit":
                raise AppError("storage.injected", "offline postcommit crash", ExitCode.STORAGE)

        monkeypatch.setattr(store, "_transaction", crashing)
        try:
            with pytest.raises(AppError):
                await store.record_analysis_policy(
                    RUN_ID, policy_hash(await store.load_run(RUN_ID))
                )
            markers = [
                row for row in await store.load_checkpoints(RUN_ID) if row.stage_id == POLICY_STAGE
            ]
            assert len(markers) == (0 if point == "before_commit" else 1)
            assert all(row.status.value == "completed" for row in markers)
            monkeypatch.setattr(store, "_transaction", original)
            with pytest.raises(AppError) as gap:
                await resume_analysis(
                    PreparedAnalyze(
                        source, project, None, None, RUN_ID, window_failure_policy=POLICY
                    ),
                    store,
                    project,
                    ports,
                )
            assert gap.value.code == "analysis.coverage_gap" and transport.calls == 3
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["unknown", "actual_model", "usage"])
def test_saved_completed_window_requires_settled_identity(tmp_path, monkeypatch, change):
    from gamingcreator.application.providers import ProviderUsage

    async def scenario():
        bundle, project, source, store, transport, ports = await failed_run(tmp_path)
        original = store.load_invocations

        async def altered(run_id):
            rows = []
            for row in await original(run_id):
                if row.stage_id == "vision-000000":
                    metadata = row.metadata
                    if change == "unknown":
                        metadata = replace(metadata, usage=ProviderUsage())
                    elif change == "actual_model":
                        metadata = replace(metadata, actual_model="future-model")
                    else:
                        metadata = replace(
                            metadata, usage=replace(metadata.usage, input_tokens=None)
                        )
                    row = replace(row, metadata=metadata)
                rows.append(row)
            return tuple(rows)

        monkeypatch.setattr(store, "load_invocations", altered)
        try:
            with pytest.raises(AppError) as stopped:
                await resume_analysis(
                    PreparedAnalyze(
                        source, project, None, None, RUN_ID, window_failure_policy=POLICY
                    ),
                    store,
                    project,
                    ports,
                )
            assert stopped.value.code == "analysis.isolation_ineligible" and transport.calls == 2
        finally:
            await store.close()

    asyncio.run(scenario())


def test_no_gap_can_complete_without_replaying_and_writer_lock_holds(tmp_path):
    async def scenario():
        bundle, project, source, store, transport, ports = await failed_run(
            tmp_path, bad_reply=response(), finish_crash=True
        )
        try:
            with pytest.raises(AppError):
                await SqliteTimelineStore.open(project)
            result = await resume_analysis(
                PreparedAnalyze(source, project, None, None, RUN_ID, window_failure_policy=POLICY),
                store,
                project,
                ports,
            )
            assert result.run_id == RUN_ID and transport.calls == 3
            assert (await store.load_completed_timeline(RUN_ID)).run.status == RunStatus.COMPLETED
            assert (project / "runs" / RUN_ID / "semantic_timeline.json").is_file()
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["input_hash", "output_hash", "status"])
def test_policy_marker_tampering_refuses_resume(tmp_path, monkeypatch, change):
    async def scenario():
        bundle, project, source, store, transport, ports = await failed_run(tmp_path)
        selected = PreparedAnalyze(
            source, project, None, None, RUN_ID, window_failure_policy=POLICY
        )
        try:
            with pytest.raises(AppError):
                await resume_analysis(selected, store, project, ports)
            original = store.load_checkpoints

            async def corrupted(run_id):
                from gamingcreator.application.storage import StageStatus

                return tuple(
                    replace(
                        row, **{change: StageStatus.INTERRUPTED if change == "status" else "0" * 64}
                    )
                    if row.stage_id == POLICY_STAGE
                    else row
                    for row in await original(run_id)
                )

            monkeypatch.setattr(store, "load_checkpoints", corrupted)
            with pytest.raises(AppError) as refused:
                await resume_analysis(selected, store, project, ports)
            assert refused.value.code == "input.window_failure_policy" and transport.calls == 3
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "corruption",
    [
        "actual_model",
        "request_id",
        "logical_request",
        "prompt",
        "usage",
        "unknown",
        "running",
        "uncommitted_success",
        "schema_usage",
        "schema_identity",
        "schema_object",
        "input_hash",
        "no_attempt",
    ],
)
def test_unsafe_saved_window_never_sends(tmp_path, monkeypatch, corruption):
    from gamingcreator.application.providers import CostStatus, ProviderUsage
    from gamingcreator.application.storage import InvocationStatus

    async def scenario():
        bundle, project, source, store, transport, ports = await failed_run(tmp_path)
        original = store.load_invocations
        original_checkpoints = store.load_checkpoints

        async def mutated(run_id):
            rows = await original(run_id)
            result = []
            for row in rows:
                if row.stage_id != "vision-000001":
                    result.append(row)
                    continue
                metadata = row.metadata
                if corruption == "no_attempt":
                    continue
                if corruption in ("actual_model", "request_id", "prompt"):
                    field = "prompt_version" if corruption == "prompt" else corruption
                    metadata = replace(
                        metadata, **{field: "wrong" if field != "request_id" else None}
                    )
                if corruption == "usage":
                    metadata = replace(metadata, usage=replace(metadata.usage, input_tokens=None))
                if corruption == "unknown":
                    metadata = replace(
                        metadata, usage=ProviderUsage(cost_status=CostStatus.UNVERIFIED)
                    )
                if corruption.startswith("schema_"):
                    details = json.loads(metadata.execution_details)
                    details["schemaError"] = {
                        "schema_usage": "usage_shape",
                        "schema_identity": "response_identity",
                        "schema_object": "object_type",
                    }[corruption]
                    metadata = replace(metadata, execution_details=json.dumps(details))
                row = replace(row, metadata=metadata)
                if corruption == "logical_request":
                    row = replace(
                        row,
                        logical_request_id=next(
                            item.logical_request_id
                            for item in rows
                            if item.stage_id == "vision-000000"
                        ),
                    )
                if corruption in ("running", "uncommitted_success"):
                    row = replace(
                        row,
                        status=InvocationStatus.RUNNING
                        if corruption == "running"
                        else InvocationStatus.COMPLETED,
                    )
                result.append(row)
            return tuple(result)

        async def checkpoints(run_id):
            return tuple(
                replace(row, input_hash="0" * 64)
                if corruption == "input_hash" and row.stage_id == "vision-000001"
                else row
                for row in await original_checkpoints(run_id)
            )

        monkeypatch.setattr(store, "load_invocations", mutated)
        monkeypatch.setattr(store, "load_checkpoints", checkpoints)
        try:
            with pytest.raises(AppError):
                await resume_analysis(
                    PreparedAnalyze(
                        source, project, None, None, RUN_ID, window_failure_policy=POLICY
                    ),
                    store,
                    project,
                    ports,
                )
            assert transport.calls == 2
        finally:
            await store.close()

    asyncio.run(scenario())


def test_ended_schema_crash_repaired_without_attempt_change(tmp_path):
    async def scenario():
        bundle, project, source, store, transport, ports = await failed_run(tmp_path)
        # Emulate a crash between durable finish_invocation and local finish_stage.
        await store._call(
            lambda: store._db.execute(
                "UPDATE stage_checkpoints SET status='interrupted',error_code='storage.interrupted' WHERE run_id=? AND stage_id='vision-000001'",
                (RUN_ID,),
            )
        )
        before = next(
            row for row in await store.load_checkpoints(RUN_ID) if row.stage_id == "vision-000001"
        )
        try:
            with pytest.raises(AppError) as gap:
                await resume_analysis(
                    PreparedAnalyze(
                        source, project, None, None, RUN_ID, window_failure_policy=POLICY
                    ),
                    store,
                    project,
                    ports,
                )
            assert gap.value.code == "analysis.coverage_gap" and transport.calls == 3
            after = next(
                row
                for row in await store.load_checkpoints(RUN_ID)
                if row.stage_id == "vision-000001"
            )
            assert (
                after.attempt == before.attempt
                and after.error_code == "provider.schema"
                and after.status.value == "failed"
            )
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["budget", "auth", "storage"])
def test_next_hard_failure_stops_and_records_remaining_coverage(tmp_path, monkeypatch, failure):
    from gamingcreator.domain.errors import ExitCode
    from gamingcreator.infrastructure.http_transport import HttpResponse

    async def scenario():
        bundle, project, source, store, transport, ports = await failed_run(tmp_path)
        if failure == "budget":
            ports.vision._budget = BudgetLedger(Decimal("0.0000001"), 20, 100)
        elif failure == "auth":
            transport.replies = [HttpResponse(401, b"{}")]
        else:
            original = store.persist_timeline

            async def broken(run_id, stage_id, events, transcripts, output_hash):
                if stage_id == "vision-000002":
                    raise AppError("storage.injected", "offline injected", ExitCode.STORAGE)
                return await original(run_id, stage_id, events, transcripts, output_hash)

            monkeypatch.setattr(store, "persist_timeline", broken)
        try:
            with pytest.raises(AppError) as stopped:
                await resume_analysis(
                    PreparedAnalyze(
                        source, project, None, None, RUN_ID, window_failure_policy=POLICY
                    ),
                    store,
                    project,
                    ports,
                )
            assert stopped.value.code.startswith(
                {"budget": "budget.", "auth": "provider.auth", "storage": "storage."}[failure]
            )
            coverage = json.loads(
                (project / "runs" / RUN_ID / "analysis_coverage.json").read_text()
            )
            assert [row["status"] for row in coverage["windows"]] == [
                "completed",
                "rejected",
                "unexecuted",
            ]
            assert not coverage["completedEligible"]
            assert (await store.load_run(RUN_ID)).status == RunStatus.FAILED
        finally:
            await store.close()

    asyncio.run(scenario())


def test_isolation_keeps_fees_and_resumes_without_replays(tmp_path: Path):
    async def scenario():
        bundle, project, source = window_bundle(tmp_path)
        images = []
        for index, image in enumerate(bundle.images):
            image.path.write_bytes(image.path.read_bytes()[:-2] + bytes([index]) + b"\xff\xd9")
            images.append(
                replace(image, sha256=hashlib.sha256(image.path.read_bytes()).hexdigest())
            )
        bundle = replace(bundle, images=tuple(images))
        write_manifest(bundle, SamplingParameters(max_width=512, max_frames=100))
        config = replace(
            CONFIG,
            vision_prompt_version="phase0-vision-v4",
            vision_prompt_hash=vision_prompt_fingerprint("phase0-vision-v4"),
        )
        store = await SqliteTimelineStore.open(project)
        transport = Transport([response(), response(reject=True), response()])
        provider = DeepSeekVisionProvider(
            transport,
            BudgetLedger(Decimal(5), 20, 100),
            None,
            store,
            price_snapshot=DEEPSEEK_FLASH_20261004,
        )
        ports = AnalysisPorts(
            WindowMedia(bundle),
            ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO)),
            provider,
            store,
            lambda request: asr_metadata(),
        )
        try:
            with pytest.raises(AppError) as stopped:
                await run_new_analysis(
                    PreparedAnalyze(source, project, config, Decimal(5), None),
                    ports,
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                )
            assert stopped.value.code == "provider.schema"
            assert transport.calls == 2
            original = await store.load_run(RUN_ID)
            attempts = await store.load_invocations(RUN_ID)
            charged = [
                item.metadata.usage.cost_cny
                for item in attempts
                if item.stage_id.startswith("vision-")
            ]
            assert all(value is not None and value > 0 for value in charged)
            rejected = [item for item in attempts if item.error_code == "provider.schema"][0]
            details = json.loads(rejected.metadata.execution_details)
            projection = details["schemaProjection"]
            assert (
                projection["events"][0]["startFrameId"]
                == projection["events"][0]["endFrameId"]
                == "f0"
            )
            assert "角色移动" not in json.dumps(projection, ensure_ascii=False)
            assert len(json.dumps(projection).encode()) < 8192
            selected = PreparedAnalyze(
                source, project, None, None, RUN_ID, window_failure_policy=POLICY
            )
            with pytest.raises(AppError) as gap:
                await resume_analysis(selected, store, project, ports)
            assert gap.value.code == "analysis.coverage_gap"
            assert transport.calls == 3
            coverage = json.loads(
                (project / "runs" / RUN_ID / "analysis_coverage.json").read_text()
            )
            assert [item["status"] for item in coverage["windows"]] == [
                "completed",
                "rejected",
                "completed",
            ]
            assert not coverage["completedEligible"]
            assert not (project / "runs" / RUN_ID / "semantic_timeline.json").exists()
            current = await store.load_run(RUN_ID)
            assert (
                current.config_hash == original.config_hash
                and current.configuration == original.configuration
            )
            assert current.status == RunStatus.FAILED
            with pytest.raises(AppError):
                await store.load_completed_timeline(RUN_ID)
            with pytest.raises(AppError) as gap:
                await resume_analysis(selected, store, project, ports)
            assert gap.value.code == "analysis.coverage_gap" and transport.calls == 3
            assert (await store.load_invocations(RUN_ID))[: len(attempts)] == attempts
            with pytest.raises(AppError) as mismatch:
                await resume_analysis(
                    replace(selected, window_failure_policy="stop-v1"), store, project, ports
                )
            assert mismatch.value.code == "input.window_failure_policy"
            marker = next(
                row for row in await store.load_checkpoints(RUN_ID) if row.stage_id == POLICY_STAGE
            )
            assert marker.input_hash == marker.output_hash
        finally:
            await store.close()

    asyncio.run(scenario())
