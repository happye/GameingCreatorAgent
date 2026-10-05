"""Read-only cost history keeps unknown commitments and validates durable attempts."""

import json
import subprocess
from dataclasses import replace
from decimal import Decimal

import pytest
from test_detail_budget_sidecar import EVENT, OTHER, RUN, _detail, timeline

from gamingcreator.application.detail_refinement import (
    prepare_refinement,
    registered_candidate_id,
    request_hash,
)
from gamingcreator.application.providers import (
    CostStatus,
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar
from gamingcreator.infrastructure.detail_cost_history import refinement_cost_history


def plan(project, event=EVENT, *, budget="budget-a", reservation="2", run=RUN, retry=False):
    request = prepare_refinement(timeline(), event).request
    assert request is not None
    if run != RUN:
        event_id = request.event_id.replace(RUN + ":", run + ":")
        request = replace(
            request,
            run_id=run,
            event_id=event_id,
            candidate_id=registered_candidate_id(run, event_id),
            evidence=tuple(
                replace(item, evidence_id=item.evidence_id.replace(RUN + ":", run + ":"))
                for item in request.evidence
            ),
        )
    number = sidecar.begin_attempt(
        project,
        request,
        budget_id=budget,
        ceiling=Decimal("1000"),
        reservation=Decimal(reservation),
        retry=retry,
    )
    return request, number


def finish(
    project, request, number, *, cost="0.015", status=ProviderStatus.COMPLETED, details=None
):
    usage = (
        ProviderUsage()
        if cost is None
        else ProviderUsage(120, 40, 20, Decimal(cost), "CNY", Decimal(cost), CostStatus.ESTIMATED)
    )
    result = ProviderResult(
        status,
        _detail(request) if status == ProviderStatus.COMPLETED else None,
        InvocationMetadata(
            request.identity.provider,
            request.identity.requested_model,
            "deepseek-flash",
            None,
            request.identity.prompt_version,
            request.identity.schema_version,
            1,
            usage,
            234,
            "price-fixture-v1",
            "request-fixture-1",
            details,
        ),
        None if status == ProviderStatus.COMPLETED else ProviderFailure("provider.network", True),
    )
    sidecar.finish_attempt(
        project, request, number, budget_id="budget-a", reservation=Decimal("2"), result=result
    )


def paths(project, request, number=1):
    directory = sidecar.sidecar_directory(project, request.run_id, request_hash(request))
    return (
        directory,
        directory / f"attempts/{number}-planned.json",
        directory / f"attempts/{number}-result.json",
    )


def snapshot(project):
    return {
        path.relative_to(project).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in project.rglob("*")
        if path.is_file()
    }


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, body):
    path.write_text(json.dumps(body), encoding="utf-8")


def ledger_path(project, budget="budget-a"):
    return project / "detail-refinement-budgets" / budget / "ledger.jsonl"


def test_missing_history_is_empty_and_creates_no_project_directory(tmp_path):
    project = tmp_path / "missing"
    report = refinement_cost_history(project, RUN)
    assert report["summary"] == {
        "knownEstimatedCostCny": "0",
        "unknownCostCount": 0,
        "unknownReservedCny": "0",
        "commitmentCny": "0",
        "attemptCount": 0,
    }
    assert report["attempts"] == [] and report["attemptsTruncated"] is False
    assert not project.exists()


@pytest.mark.parametrize(
    "status", [ProviderStatus.COMPLETED, ProviderStatus.FAILED, ProviderStatus.CANCELLED]
)
def test_unknown_usage_and_all_terminal_statuses_remain_reserved_without_writes(
    tmp_path, status, monkeypatch
):
    request, number = plan(tmp_path)
    finish(tmp_path, request, number, cost=None, status=status)
    before = snapshot(tmp_path)
    for name in ("_atomic", "_append_charge", "_publish", "_recover_refinement"):
        monkeypatch.setattr(sidecar, name, lambda *args: pytest.fail("Reader attempted a write"))
    monkeypatch.setattr(
        sidecar.BudgetWriterLock, "acquire", lambda *args: pytest.fail("Reader acquired a lock")
    )
    report = refinement_cost_history(tmp_path, RUN)
    assert report["summary"]["unknownCostCount"] == 1
    assert report["summary"]["unknownReservedCny"] == "2"
    assert report["summary"]["knownEstimatedCostCny"] == "0"
    attempt = report["attempts"][0]
    assert attempt["status"] == status.value and attempt["estimatedCostCny"] is None
    assert attempt["metadata"]["usage"]["inputTokens"] is None
    assert attempt["metadata"]["usage"]["costCny"] is None
    assert snapshot(tmp_path) == before


def test_known_estimate_preserves_identity_usage_time_and_filters_raw_execution(tmp_path):
    request, number = plan(tmp_path)
    finish(
        tmp_path,
        request,
        number,
        details=json.dumps(
            {
                "requestedAtUtc": "2026-10-06T01:02:03+00:00",
                "period": "peak",
                "periodBasis": "weekday_peak_or_holiday_unknown_conservative",
                "rawResponse": "secret fixture",
                "apiKey": "secret fixture",
            }
        ),
    )
    report = refinement_cost_history(tmp_path, RUN)
    assert report["summary"]["commitmentCny"] == "0.015"
    assert report["summary"]["unknownCostCount"] == 0
    attempt = report["attempts"][0]
    assert attempt["requestHash"] == request_hash(request) and attempt["attemptNo"] == 1
    assert attempt["metadata"]["actualModel"] == "deepseek-flash"
    assert attempt["metadata"]["modelRevision"] is None
    assert attempt["metadata"]["requestId"] == "request-fixture-1"
    assert attempt["metadata"]["elapsedMs"] == 234
    assert attempt["metadata"]["requestedAtUtc"] == "2026-10-06T01:02:03+00:00"
    assert attempt["metadata"]["usage"] == {
        "inputTokens": 120,
        "outputTokens": 40,
        "cachedInputTokens": 20,
        "originalCost": "0.015",
        "currency": "CNY",
        "costCny": "0.015",
        "costStatus": "estimated",
    }
    assert "secret fixture" not in json.dumps(report) and "payloadJson" not in json.dumps(report)


def test_planned_record_without_ledger_still_reserves_and_never_repairs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sidecar, "_append_charge", lambda *args: (_ for _ in ()).throw(OSError("fixture crash"))
    )
    with pytest.raises(OSError):
        plan(tmp_path)
    before = snapshot(tmp_path)
    report = refinement_cost_history(tmp_path, RUN)
    assert report["summary"]["commitmentCny"] == "2"
    assert report["attempts"][0]["status"] == "planned"
    assert report["attempts"][0]["metadata"] is None
    assert not ledger_path(tmp_path).exists() and snapshot(tmp_path) == before


def test_completed_result_before_settlement_keeps_conservative_commitment(tmp_path, monkeypatch):
    request, number = plan(tmp_path)
    monkeypatch.setattr(
        sidecar, "_settle_record", lambda *args: (_ for _ in ()).throw(OSError("fixture crash"))
    )
    with pytest.raises(OSError):
        finish(tmp_path, request, number)
    before = snapshot(tmp_path)
    report = refinement_cost_history(tmp_path, RUN)
    assert report["summary"]["knownEstimatedCostCny"] == "0"
    assert report["summary"]["unknownReservedCny"] == "2"
    assert report["attempts"][0]["metadata"]["usage"]["costCny"] == "0.015"
    assert report["attempts"][0]["settlementPending"] is True
    assert not (paths(tmp_path, request)[0] / "result.json").exists()
    assert snapshot(tmp_path) == before


def test_multiple_budgets_runs_and_retry_are_shared_without_repeated_settlement_charges(tmp_path):
    request, number = plan(tmp_path)
    finish(tmp_path, request, number, status=ProviderStatus.FAILED)
    plan(tmp_path, retry=True)
    plan(tmp_path, OTHER, budget="budget-b", reservation="3", run="run-2")
    settled = ledger_path(tmp_path).read_bytes().splitlines()[-2]  # first result, before retry
    with ledger_path(tmp_path).open("ab") as handle:
        handle.write(settled + b"\n")
    report = refinement_cost_history(tmp_path, RUN)
    assert report["summary"]["attemptCount"] == 2
    assert report["summary"]["commitmentCny"] == "2.015"
    assert report["sharedCommitment"] == {
        "knownEstimatedCostCny": "0.015",
        "unknownCostCount": 2,
        "unknownReservedCny": "5",
        "commitmentCny": "5.015",
        "attemptCount": 3,
        "scope": "project-detail-refinements",
        "runCount": 2,
        "budgetCount": 2,
    }


@pytest.mark.parametrize("completed", [False, True])
def test_legacy_attempts_have_no_fabricated_metadata_and_keep_unknown_cost(tmp_path, completed):
    request, number = plan(tmp_path)
    _, planned_path, result_path = paths(tmp_path, request)
    planned = read_json(planned_path)
    write_json(
        planned_path,
        {key: planned[key] for key in ("attempt", "requestHash", "reservationCny", "status")},
    )
    if completed:
        write_json(
            result_path,
            {
                "attempt": number,
                "requestHash": request_hash(request),
                "costCny": None,
                "revision": None,
                "status": "failed",
            },
        )
    before = snapshot(tmp_path)
    report = refinement_cost_history(tmp_path, RUN)
    assert report["summary"]["unknownReservedCny"] == "2"
    assert report["attempts"][0]["metadata"] is None
    assert report["attempts"][0]["legacy"] is True
    assert report["attempts"][0]["status"] == ("failed" if completed else "planned")
    assert snapshot(tmp_path) == before


def test_legacy_incomplete_without_budget_cannot_silently_zero_commitment(tmp_path):
    request, _ = plan(tmp_path)
    _, planned_path, _ = paths(tmp_path, request)
    planned = read_json(planned_path)
    write_json(
        planned_path,
        {key: planned[key] for key in ("attempt", "requestHash", "reservationCny", "status")},
    )
    ledger_path(tmp_path).unlink()
    before = snapshot(tmp_path)
    with pytest.raises(AppError) as caught:
        refinement_cost_history(tmp_path, RUN)
    assert caught.value.code == "budget.interrupted" and snapshot(tmp_path) == before


def test_legacy_result_before_ledger_settlement_keeps_unknown_and_does_not_invent_usage(tmp_path):
    request, number = plan(tmp_path)
    _, planned_path, result_path = paths(tmp_path, request)
    planned = read_json(planned_path)
    write_json(
        planned_path,
        {key: planned[key] for key in ("attempt", "requestHash", "reservationCny", "status")},
    )
    write_json(
        result_path,
        {
            "attempt": number,
            "requestHash": request_hash(request),
            "costCny": "0.015",
            "revision": None,
            "status": "completed",
        },
    )
    before = snapshot(tmp_path)
    report = refinement_cost_history(tmp_path, RUN)
    assert report["summary"]["unknownReservedCny"] == "2"
    assert report["attempts"][0]["settlementPending"] is True
    assert report["attempts"][0]["metadata"] is None
    assert report["attempts"][0]["estimatedCostCny"] is None
    assert snapshot(tmp_path) == before


def test_known_zero_charge_is_distinct_from_unknown_usage(tmp_path):
    request, number = plan(tmp_path)
    finish(tmp_path, request, number, cost="0")
    report = refinement_cost_history(tmp_path, RUN)
    assert report["summary"]["knownEstimatedCostCny"] == "0"
    assert report["summary"]["unknownCostCount"] == 0
    assert report["summary"]["unknownReservedCny"] == "0"
    assert report["attempts"][0]["estimatedCostCny"] == "0"


def test_legacy_ledger_only_and_truncated_history_report_complete_totals(tmp_path):
    ledger = ledger_path(tmp_path)
    ledger.parent.mkdir(parents=True)
    records = [
        {
            "attempt": 1,
            "requestHash": f"{number:064x}",
            "runId": RUN,
            "reservationCny": "2",
            "frames": 1,
            "costCny": "0.1",
            "revision": None,
        }
        for number in range(201)
    ]
    ledger.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
    report = refinement_cost_history(tmp_path, RUN)
    assert report["totalAttemptCount"] == 201 and report["attemptsTruncated"] is True
    assert len(report["attempts"]) == 200
    assert report["summary"]["knownEstimatedCostCny"] == "20.1"
    assert all(
        item["metadata"] is None and item["status"] == "recorded" for item in report["attempts"]
    )


@pytest.mark.parametrize(
    "damage",
    [
        "missing_field",
        "duplicate_json_key",
        "settlement_conflict",
        "cost_downgrade",
        "cross_budget",
        "negative_cost",
        "huge_exponent",
        "bad_revision",
        "bool_attempt",
    ],
)
def test_damaged_ledgers_fail_explicitly_and_without_writes(tmp_path, damage):
    request, number = plan(tmp_path)
    finish(tmp_path, request, number)
    ledger = ledger_path(tmp_path)
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    row = dict(rows[-1])
    if damage == "missing_field":
        del row["frames"]
    elif damage == "duplicate_json_key":
        ledger.write_text(json.dumps(row)[:-1] + ',"attempt":1}', encoding="utf-8")
    elif damage == "settlement_conflict":
        row["costCny"] = "0.1"
    elif damage == "cost_downgrade":
        row["costCny"] = None
    elif damage == "cross_budget":
        ledger = ledger_path(tmp_path, "budget-b")
        ledger.parent.mkdir()
    elif damage == "negative_cost":
        row["costCny"] = "-1"
    elif damage == "huge_exponent":
        row["reservationCny"] = "1e99999999"
    elif damage == "bad_revision":
        row["revision"] = 42
    elif damage == "bool_attempt":
        row["attempt"] = True
    if damage != "duplicate_json_key":
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    before = snapshot(tmp_path)
    with pytest.raises(AppError) as caught:
        refinement_cost_history(tmp_path, RUN)
    assert caught.value.code == "refinement.damaged" and snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "damage",
    [
        "bad_status",
        "result_request",
        "metadata_usage",
        "payload_hash",
        "unsafe_error",
        "planned_run",
        "request_hash",
        "request_missing",
        "orphan_result",
        "negative_planned_reservation",
    ],
)
def test_damaged_attempts_fail_without_recovery_or_publication(tmp_path, damage):
    request, number = plan(tmp_path)
    finish(
        tmp_path,
        request,
        number,
        status=ProviderStatus.FAILED if damage == "unsafe_error" else ProviderStatus.COMPLETED,
    )
    directory, planned_path, result_path = paths(tmp_path, request)
    target = result_path
    row = read_json(target)
    if damage == "bad_status":
        row["status"] = "future-status"
    elif damage == "result_request":
        row["requestHash"] = "f" * 64
    elif damage == "metadata_usage":
        row["metadata"]["usage"]["cost_cny"] = "0.1"
    elif damage == "payload_hash":
        row["payloadHash"] = "f" * 64
    elif damage == "unsafe_error":
        row["error"]["code"] = "Bearer secret fixture"
    elif damage in ("planned_run", "negative_planned_reservation"):
        target = planned_path
        row = read_json(target)
        row["runId" if damage == "planned_run" else "reservationCny"] = (
            "other" if damage == "planned_run" else "-2"
        )
    elif damage in ("request_hash", "request_missing"):
        target = directory / "request.json"
        row = read_json(target)
        row["requestHash"] = "f" * 64
        if damage == "request_missing":
            target.unlink()
    elif damage == "orphan_result":
        planned_path.unlink()
    if damage not in ("request_missing", "orphan_result"):
        write_json(target, row)
    before = snapshot(tmp_path)
    with pytest.raises(AppError) as caught:
        refinement_cost_history(tmp_path, RUN)
    assert caught.value.code == "refinement.damaged" and snapshot(tmp_path) == before


def test_corrupt_other_run_cannot_hide_shared_commitment(tmp_path):
    plan(tmp_path, OTHER, run="run-2", budget="budget-b")
    row = read_json(next((tmp_path / "runs/run-2").rglob("*-planned.json")))
    row["status"] = "forged"
    write_json(next((tmp_path / "runs/run-2").rglob("*-planned.json")), row)
    with pytest.raises(AppError) as caught:
        refinement_cost_history(tmp_path, RUN)
    assert caught.value.code == "refinement.damaged"


@pytest.mark.parametrize("run_id", ["../escape", "..\\escape", "", "bad/id"])
def test_run_identity_cannot_escape_project(tmp_path, run_id):
    with pytest.raises(AppError) as caught:
        refinement_cost_history(tmp_path, run_id)
    assert caught.value.code == "refinement.path" and not list(tmp_path.iterdir())


def test_budget_directory_junction_is_refused_without_touching_target(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    linked = project / "detail-refinement-budgets"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(linked), str(outside)], capture_output=True
    )
    if result.returncode:
        pytest.skip("Windows junction unavailable")
    try:
        with pytest.raises(AppError) as caught:
            refinement_cost_history(project, RUN)
        assert caught.value.code == "refinement.path" and not list(outside.iterdir())
    finally:
        linked.rmdir()


def test_response_limit_is_explicit_and_preserves_data(tmp_path, monkeypatch):
    request, number = plan(tmp_path)
    finish(tmp_path, request, number)
    monkeypatch.setattr(sidecar, "_MAX_JSON_BYTES", 1024)
    # Raise only the response bound, keeping normal immutable reads available.
    original = sidecar._read_bytes
    monkeypatch.setattr(sidecar, "_read_bytes", lambda path, root: path.read_bytes())
    before = snapshot(tmp_path)
    with pytest.raises(AppError) as caught:
        refinement_cost_history(tmp_path, RUN)
    assert caught.value.code == "refinement.too_large" and snapshot(tmp_path) == before
    monkeypatch.setattr(sidecar, "_read_bytes", original)
