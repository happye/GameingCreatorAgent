"""Crash boundaries, full invocation records, and explicit retry accounting."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal

import pytest
from test_detail_budget_sidecar import EVENT, OTHER, CountingProvider, timeline
from test_detail_provider import Transport, prepared_fixture, response, visible_detail

from gamingcreator.application.detail_refinement import prepare_refinement, request_hash
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import (
    CancellationContext,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
)
from gamingcreator.application.storage import RunStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar
from gamingcreator.infrastructure.deepseek_detail_refinement import (
    DeepSeekDetailRefinementProvider,
    provider_refinement_identity,
)

OPTIONS = {"budget_id": "budget-a", "ceiling": Decimal("10"), "reservation": Decimal("2")}


def send(project, provider, **kwargs):
    return asyncio.run(
        sidecar.send_refinement(project, timeline(), EVENT, provider, **OPTIONS, **kwargs)
    )


def directory(project):
    prepared = prepare_refinement(timeline(), EVENT)
    return sidecar.sidecar_directory(project, "run-1", prepared.request_hash)


def ledger(project):
    return [
        json.loads(line)
        for line in (project / "detail-refinement-budgets/budget-a/ledger.jsonl")
        .read_text()
        .splitlines()
    ]


@pytest.mark.parametrize("boundary", ["settle", "publish"])
def test_completed_attempt_recovers_without_a_second_provider_call(tmp_path, monkeypatch, boundary):
    provider = CountingProvider()
    name = "_settle_record" if boundary == "settle" else "_publish"
    original = getattr(sidecar, name)

    def interrupted(*args, **kwargs):
        raise OSError("fixture power loss")

    monkeypatch.setattr(sidecar, name, interrupted)
    with pytest.raises(OSError):
        send(tmp_path, provider)
    attempt_path = directory(tmp_path) / "attempts/1-result.json"
    saved = attempt_path.read_bytes()
    assert json.loads(saved)["payloadJson"] is not None
    assert not (directory(tmp_path) / "result.json").exists()
    monkeypatch.setattr(sidecar, name, original)
    recovered = send(tmp_path, provider)
    assert recovered.reused and recovered.detail is not None and provider.calls == 1
    assert attempt_path.read_bytes() == saved
    published = (directory(tmp_path) / "result.json").read_bytes()
    before_ledger = ledger(tmp_path)
    assert send(tmp_path, provider).reused and provider.calls == 1
    assert (directory(tmp_path) / "result.json").read_bytes() == published
    assert ledger(tmp_path) == before_ledger  # Recovery must not count a charge twice.


def test_planned_write_before_ledger_failure_retains_commitment_across_budget_dirs(
    tmp_path, monkeypatch
):
    request = prepare_refinement(timeline(), EVENT).request
    other = prepare_refinement(timeline(), OTHER).request
    original = sidecar._append_charge
    monkeypatch.setattr(
        sidecar,
        "_append_charge",
        lambda *args: (_ for _ in ()).throw(OSError("fixture ledger loss")),
    )
    with pytest.raises(OSError):
        sidecar.begin_attempt(tmp_path, request, retry=False, **OPTIONS)
    monkeypatch.setattr(sidecar, "_append_charge", original)
    with pytest.raises(AppError) as caught:
        sidecar.begin_attempt(
            tmp_path,
            other,
            budget_id="new-budget",
            ceiling=Decimal("3"),
            reservation=Decimal("2"),
            retry=False,
        )
    assert caught.value.code == "budget.exhausted"
    assert not (tmp_path / "detail-refinement-budgets/new-budget/ledger.jsonl").exists()


def test_full_provider_identity_usage_and_cost_are_saved_and_recovered(tmp_path, monkeypatch):
    request, paths = prepared_fixture(tmp_path)
    stored = timeline()
    stored = replace(
        stored,
        evidence=tuple(
            replace(
                item,
                sha256=request.evidence[index].image_sha256,
                artifact_path=paths[item.evidence_id],
            )
            if index < 3
            else item
            for index, item in enumerate(stored.evidence)
        ),
    )
    transport = Transport(response(visible_detail(request)))
    provider = DeepSeekDetailRefinementProvider(
        transport, paths, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    publish = sidecar._publish
    monkeypatch.setattr(
        sidecar, "_publish", lambda *args: (_ for _ in ()).throw(OSError("fixture publish loss"))
    )
    with pytest.raises(OSError):
        asyncio.run(
            sidecar.send_refinement(
                tmp_path,
                stored,
                EVENT,
                provider,
                identity=provider_refinement_identity(),
                **OPTIONS,
            )
        )
    target = sidecar.sidecar_directory(tmp_path, request.run_id, request_hash(request))
    row = json.loads((target / "attempts/1-result.json").read_text())
    metadata = row["metadata"]
    assert row["promptHash"] == request.identity.prompt_hash
    assert metadata["provider"] == "deepseek" and metadata["actual_model"] == "deepseek-flash"
    assert (
        metadata["request_id"] == "refine-request-1"
        and metadata["price_version"] == DEEPSEEK_FLASH_20261004.version
    )
    assert (
        metadata["usage"]["input_tokens"] == 100 and metadata["usage"]["cached_input_tokens"] == 10
    )
    assert (
        metadata["usage"]["cost_status"] == "estimated"
        and metadata["usage"]["cost_cny"] is not None
    )
    assert metadata["model_revision"] is None and metadata["elapsed_ms"] >= 0
    monkeypatch.setattr(sidecar, "_publish", publish)
    recovered = asyncio.run(
        sidecar.send_refinement(
            tmp_path, stored, EVENT, provider, identity=provider_refinement_identity(), **OPTIONS
        )
    )
    assert recovered.reused and len(transport.payloads) == 1
    assert json.loads((target / "result.json").read_text())["metadata"] == metadata
    assert len(ledger(tmp_path)) == 2  # planned null, settled estimate; one distinct attempt.


@pytest.mark.parametrize("status", [ProviderStatus.FAILED, ProviderStatus.CANCELLED])
def test_finished_failure_requires_explicit_retry_and_retains_unknown_reservation(tmp_path, status):
    base = CountingProvider()

    class Failed:
        async def refine(self, request, context):
            success = await base.refine(request, context)
            return ProviderResult(
                status,
                None,
                success.metadata,
                ProviderFailure(
                    "provider.cancelled"
                    if status == ProviderStatus.CANCELLED
                    else "provider.network",
                    True,
                ),
            )

    assert send(tmp_path, Failed()).detail is None
    row = json.loads((directory(tmp_path) / "attempts/1-result.json").read_text())
    assert row["status"] == status.value and row["error"]["code"].startswith("provider.")
    assert row["metadata"]["usage"]["cost_cny"] is None
    with pytest.raises(AppError) as caught:
        send(tmp_path, base)
    assert caught.value.code == "refinement.retry_required" and base.calls == 1
    outcome = send(tmp_path, base, retry=True)
    assert outcome.detail is not None and base.calls == 2
    charges = sidecar._charges(tmp_path)
    assert len(charges) == 2 and sum(charge.reservation_cny for charge in charges) == Decimal("4")


@pytest.mark.parametrize(
    "failure", [RuntimeError("credential must not be recorded"), asyncio.CancelledError()]
)
def test_raised_provider_error_is_sanitized_and_persisted(tmp_path, failure):
    class Raised:
        async def refine(self, request, context):
            raise failure

    if isinstance(failure, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            send(tmp_path, Raised())
    else:
        assert send(tmp_path, Raised()).detail is None
    data = (directory(tmp_path) / "attempts/1-result.json").read_text()
    assert "credential" not in data and 'cost_cny": null' in data
    assert json.loads(data)["status"] == (
        "cancelled" if isinstance(failure, asyncio.CancelledError) else "failed"
    )


@pytest.mark.parametrize(
    "field,value",
    [("promptHash", "f" * 64), ("payloadHash", "f" * 64), ("schemaVersion", "future")],
)
def test_corrupt_recovery_fails_closed_without_sending(tmp_path, monkeypatch, field, value):
    provider = CountingProvider()
    publish = sidecar._publish
    monkeypatch.setattr(
        sidecar, "_publish", lambda *args: (_ for _ in ()).throw(OSError("fixture loss"))
    )
    with pytest.raises(OSError):
        send(tmp_path, provider)
    monkeypatch.setattr(sidecar, "_publish", publish)
    path = directory(tmp_path) / "attempts/1-result.json"
    row = json.loads(path.read_text())
    row[field] = value
    path.write_text(json.dumps(row))
    with pytest.raises(AppError) as caught:
        send(tmp_path, provider, retry=True)
    assert caught.value.code == "refinement.damaged" and provider.calls == 1


def test_retry_cannot_overlap_an_active_key_writer(tmp_path):
    request = prepare_refinement(timeline(), EVENT).request
    provider = CountingProvider()
    with sidecar.RefinementWriterLock(tmp_path, request):
        with pytest.raises(AppError) as caught:
            send(tmp_path, provider, retry=True)
    assert caught.value.code == "storage.writer_busy" and provider.calls == 0


def test_mismatched_typed_output_is_failed_but_returned_usage_is_not_lost(tmp_path):
    base = CountingProvider()

    class Drifted:
        async def refine(self, request, context):
            result = await base.refine(request, context)
            return replace(result, output=replace(result.output, event_fingerprint="f" * 64))

    assert send(tmp_path, Drifted()).detail is None
    row = json.loads((directory(tmp_path) / "attempts/1-result.json").read_text())
    assert row["status"] == "failed" and row["error"]["code"] == "provider.schema"
    assert not (directory(tmp_path) / "result.json").exists()


def test_incomplete_base_run_never_creates_a_plan_or_calls_provider(tmp_path):
    stored = timeline()
    stored = replace(stored, run=replace(stored.run, status=RunStatus.RUNNING))
    provider = CountingProvider()
    with pytest.raises(AppError) as caught:
        asyncio.run(sidecar.send_refinement(tmp_path, stored, EVENT, provider, **OPTIONS))
    assert caught.value.code == "refinement.run_incomplete" and provider.calls == 0
    assert not list(tmp_path.rglob("*-planned.json"))


def test_external_task_cancel_is_persisted_before_propagating(tmp_path):
    request, paths = prepared_fixture(tmp_path)
    stored = timeline()
    stored = replace(
        stored,
        evidence=tuple(
            replace(
                item,
                sha256=request.evidence[index].image_sha256,
                artifact_path=paths[item.evidence_id],
            )
            if index < 3
            else item
            for index, item in enumerate(stored.evidence)
        ),
    )
    entered = asyncio.Event()

    class Waiting:
        async def post(self, payload, timeout_seconds):
            entered.set()
            await asyncio.Future()

    async def run():
        provider = DeepSeekDetailRefinementProvider(Waiting(), paths)
        task = asyncio.create_task(
            sidecar.send_refinement(
                tmp_path,
                stored,
                EVENT,
                provider,
                identity=provider_refinement_identity(),
                **OPTIONS,
            )
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    target = sidecar.sidecar_directory(tmp_path, request.run_id, request_hash(request))
    row = json.loads((target / "attempts/1-result.json").read_text())
    assert row["status"] == "cancelled" and row["metadata"]["attempt"] == 1
    assert row["metadata"]["usage"]["cost_cny"] is None
    assert not (target / "result.json").exists()


def test_pre_cancelled_context_does_not_reserve_or_send(tmp_path):
    provider = CountingProvider()
    context = CancellationContext("run-1", 90)
    context.cancelled.set()
    with pytest.raises(asyncio.CancelledError):
        send(tmp_path, provider, context=context)
    assert provider.calls == 0 and not list(tmp_path.rglob("*-planned.json"))


@pytest.mark.parametrize("damage", ["remove_schema", "duplicate_key", "wrong_planned"])
def test_attempt_records_cannot_be_downgraded_or_reattributed(tmp_path, monkeypatch, damage):
    provider = CountingProvider()
    publish = sidecar._publish
    monkeypatch.setattr(
        sidecar, "_publish", lambda *args: (_ for _ in ()).throw(OSError("fixture loss"))
    )
    with pytest.raises(OSError):
        send(tmp_path, provider)
    monkeypatch.setattr(sidecar, "_publish", publish)
    target = directory(tmp_path) / "attempts/1-result.json"
    row = json.loads(target.read_text())
    if damage == "remove_schema":
        del row["schemaVersion"]
        target.write_text(json.dumps(row))
    elif damage == "duplicate_key":
        target.write_text(json.dumps(row)[:-1] + ',"attempt":1}')
    else:
        target = directory(tmp_path) / "attempts/1-planned.json"
        row = json.loads(target.read_text())
        row["runId"] = "other-run"
        target.write_text(json.dumps(row))
    with pytest.raises(AppError) as caught:
        send(tmp_path, provider, retry=True)
    assert caught.value.code == "refinement.damaged" and provider.calls == 1
