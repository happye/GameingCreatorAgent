# ruff: noqa: F811 -- pytest fixtures are imported for discovery, then injected by name.

import asyncio
from decimal import Decimal

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401
from test_creation_planner import brief as planner_brief
from test_plan_proposals import timelines

from gamingcreator.application.ai_budget import Spend, decide
from gamingcreator.application.brief_reasoning import brief_snapshot
from gamingcreator.application.plan_proposals import create_plan_snapshot, with_knowledge
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.creation_work_store import CreationWorkStore
from gamingcreator.ui.creation_budget_scope import request_digest, resolve_budget_key
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.creation_reasoning_http import reasoning_post
from gamingcreator.ui.creation_reasoning_service import (
    CONFIRMATION_SCHEMA,
    PREPARED_SCHEMA,
    RESULT_SCHEMA,
    CreationReasoningService,
    _digest,
    _write,
)
from gamingcreator.ui.plan_reasoning_jobs import adoption_request

PROJECT = "artifacts/project"
A = "a" * 32
B = "b" * 32


def _reasoning(jobs: CreationJobs) -> CreationReasoningService:
    return CreationReasoningService(jobs, price_snapshot=DEEPSEEK_FLASH_20261004)


def _work(jobs: CreationJobs, work_id: str = A) -> None:
    CreationWorkStore(jobs.root / "works").create(PROJECT, work_id)


def _job(jobs: CreationJobs, job_id: str, kind: str, request: dict[str, object]) -> None:
    directory = jobs.jobs / job_id
    directory.mkdir(exist_ok=True)
    jobs.save(directory / "status.json", {"kind": kind, "projectId": PROJECT})
    jobs.save(
        directory / "request.json",
        {"request": request, "digest": request_digest(kind, request)},
    )


def test_brief_two_roots_adoption_revision_render_share_work(service: CreationJobs) -> None:
    _work(service)
    reasoning = _reasoning(service)
    brief = reasoning.prepare_brief("展示玩法", [], PROJECT, A)
    assert reasoning._prepared(brief["preparedHash"])["budgetKey"] == "work:" + A
    roots = ["1" * 32, "2" * 32]
    for root in roots:
        _job(service, root, "plan", {"projectId": PROJECT, "workId": A})
        assert resolve_budget_key(service, root, PROJECT, reasoning._prepared) == "work:" + A
    prepared = reasoning._prepare(
        create_plan_snapshot(planner_brief(), timelines(), 30), PROJECT, roots[0], "", "", "plan"
    )
    record = reasoning._prepared(prepared["preparedHash"])
    assert record["budgetKey"] == "work:" + A
    adopted, revision, render = "3" * 32, "4" * 32, "5" * 32
    original = {"projectId": PROJECT, "workId": A, "requestId": "0" * 32}
    _job(service, adopted, "plan", adoption_request(original, prepared["preparedHash"]))
    _job(service, revision, "revision", {"parentJobId": adopted})
    _job(service, render, "render", {"revisionJobId": revision})
    for job_id in (adopted, revision, render):
        assert resolve_budget_key(service, job_id, PROJECT, reasoning._prepared) == "work:" + A


def test_work_caps_independent_with_shared_month_and_unknown_spend() -> None:
    rows = [Spend("2026-10", "work:" + A, Decimal("0.99"))]
    assert not decide(rows, "work:" + A, "2026-11", Decimal("0.02")).allowed
    assert decide(rows, "work:" + B, "2026-11", Decimal("0.02")).allowed
    rows.append(Spend("2026-11", "brief-unassigned", Decimal("29.99")))
    assert not decide(rows, "work:" + B, "2026-11", Decimal("0.02")).allowed
    unknown = [Spend("2026-10", "?", Decimal("0.99"))]
    for key in ("work:" + A, "legacy-root", "brief-unassigned"):
        assert not decide(unknown, key, "2026-11", Decimal("0.02")).allowed
    brief = [Spend("2026-11", "brief-unassigned", Decimal("0.99"))]
    assert decide(brief, "work:" + B, "2026-11", Decimal("0.02")).allowed
    assert not decide(brief, "legacy-root", "2026-11", Decimal("0.02")).allowed


@pytest.mark.parametrize("purpose", ["brief", "edit"])
def test_adoption_cannot_inherit_brief_marker_or_edit_preparation(
    service: CreationJobs, purpose: str
) -> None:
    _work(service)
    reasoning = _reasoning(service)
    response = reasoning.prepare_brief("展示玩法", [], PROJECT, A)
    record = reasoning._prepared(response["preparedHash"])
    record["purpose"] = purpose
    prepared_hash = _digest(record)
    if prepared_hash != response["preparedHash"]:
        _write(reasoning._directory(prepared_hash), "prepared.json", record)
    job_id = "1" * 32
    _job(service, job_id, "plan", {"projectId": PROJECT, "reasoningPreparedHash": prepared_hash})
    with pytest.raises(ValueError, match="方案准备"):
        resolve_budget_key(service, job_id, PROJECT, reasoning._prepared)


def test_plan_submit_requires_persisted_same_project_work(service: CreationJobs) -> None:
    value = {**request(), "workId": A}
    with pytest.raises(ValueError):
        service.submit("plan", value)
    assert list(service.jobs.iterdir()) == []
    CreationWorkStore(service.root / "works").create("artifacts/other", A)
    with pytest.raises(ValueError):
        service.submit("plan", value)
    assert list(service.jobs.iterdir()) == []


def test_plan_submit_preserves_work_for_multiple_root_requests(service: CreationJobs) -> None:
    _work(service)
    reasoning = _reasoning(service)
    roots = []
    for request_id in ("1" * 32, "2" * 32):
        value = {**request(), "requestId": request_id, "workId": A}
        submitted = service.submit("plan", value)
        root = submitted["jobId"]
        assert finish(service, root)["status"] == "completed"
        roots.append(root)
        assert resolve_budget_key(service, root, PROJECT, reasoning._prepared) == "work:" + A
    assert roots[0] != roots[1]


@pytest.mark.parametrize("damage", ["work", "digest", "project", "missing", "cycle", "conflict"])
def test_scope_rejects_invalid_ancestry(service: CreationJobs, damage: str) -> None:
    _work(service)
    _work(service, B)
    root, child = "1" * 32, "2" * 32
    _job(service, root, "plan", {"projectId": PROJECT, "workId": A})
    request: dict[str, object] = {"parentJobId": root}
    if damage == "missing":
        request["parentJobId"] = "9" * 32
    elif damage == "cycle":
        request["parentJobId"] = child
    elif damage == "project":
        request["projectId"] = "artifacts/other"
    elif damage == "conflict":
        request["workId"] = B
    _job(service, child, "revision", request)
    if damage in {"work", "digest"}:
        path = service.jobs / root / "request.json"
        document = service.read(path)
        if damage == "work":
            document["request"]["workId"] = B
        else:
            document["digest"] = "0" * 64
        service.save(path, document)
    with pytest.raises((ValueError, KeyError, AppError)):
        resolve_budget_key(service, child, PROJECT, _reasoning(service)._prepared)


@pytest.mark.parametrize("schema", ["plan-proposal-v1", "plan-proposal-v2"])
def test_legacy_prepared_hash_and_bytes_remain_unchanged(
    service: CreationJobs, schema: str
) -> None:
    reasoning = _reasoning(service)
    record = {"schemaVersion": PREPARED_SCHEMA, "request": {"schema_version": schema}}
    prepared_hash = _digest(record)
    directory = reasoning._directory(prepared_hash)
    _write(directory, "prepared.json", record)
    original = (directory / "prepared.json").read_bytes()
    assert reasoning._prepared(prepared_hash) == record
    assert "budgetKey" not in reasoning._prepared(prepared_hash)
    assert (directory / "prepared.json").read_bytes() == original
    root = "1" * 32
    _job(service, root, "plan", {"projectId": PROJECT})
    assert resolve_budget_key(service, root, PROJECT, reasoning._prepared) == root


def test_frozen_spend_identity_and_unknown_cost_survive_changed_chain(
    service: CreationJobs,
) -> None:
    _work(service)
    _work(service, B)
    root = "1" * 32
    _job(service, root, "plan", {"projectId": PROJECT, "workId": A})
    reasoning = _reasoning(service)
    prepared = reasoning._prepare(brief_snapshot("展示玩法", []), PROJECT, root, "", "", "brief")
    prepared_hash = prepared["preparedHash"]
    attempt = reasoning._directory(prepared_hash) / "attempt"
    _write(
        attempt / "planned",
        "confirmation.json",
        {
            "schemaVersion": CONFIRMATION_SCHEMA,
            "confirmedAt": "2026-11-13T00:00:00+08:00",
            "budgetCeilingCny": "0.25",
        },
    )
    _write(
        attempt / "result",
        "result.json",
        {
            "schemaVersion": RESULT_SCHEMA,
            "preparedHash": prepared_hash,
            "status": "failed",
            "billing": {"knownCostCny": None},
        },
    )
    original = (attempt / "result/result.json").read_bytes()
    _job(service, root, "plan", {"projectId": PROJECT, "workId": B})
    (row,) = reasoning._spends()
    assert row.job_id == "work:" + A and row.cny == Decimal("0.25")
    assert (attempt / "result/result.json").read_bytes() == original
    assert reasoning.read_result(prepared_hash)["billing"]["knownCostCny"] is None


@pytest.mark.parametrize("automatic", [True, False])
def test_scope_change_refuses_send_before_consuming_attempt(
    service: CreationJobs, automatic: bool
) -> None:
    _work(service)
    _work(service, B)
    root = "1" * 32
    _job(service, root, "plan", {"projectId": PROJECT, "workId": A})
    reasoning = _reasoning(service)
    prepared = reasoning._prepare(brief_snapshot("展示玩法", []), PROJECT, root, "", "", "brief")
    _job(service, root, "plan", {"projectId": PROJECT, "workId": B})
    with pytest.raises(ValueError, match="预算来源"):
        operation = (
            reasoning.execute_within_budget(
                prepared["preparedHash"], prepared["snapshotFingerprint"]
            )
            if automatic
            else reasoning.execute(
                prepared["preparedHash"],
                prepared["snapshotFingerprint"],
                Decimal(prepared["maxCostCny"]),
            )
        )
        asyncio.run(operation)
    assert not (reasoning._directory(prepared["preparedHash"]) / "attempt").exists()


def test_corrupt_prepared_identity_blocks_new_work_auto_allowance(service: CreationJobs) -> None:
    _work(service)
    _work(service, B)
    reasoning = _reasoning(service)
    prepared = reasoning.prepare_brief("展示玩法", [], PROJECT, A)
    directory = reasoning._directory(prepared["preparedHash"])
    _write(
        directory / "attempt/planned",
        "confirmation.json",
        {
            "schemaVersion": CONFIRMATION_SCHEMA,
            "budgetCeilingCny": "0.1",
        },
    )
    path = directory / "prepared.json"
    path.write_bytes(b"{}")
    (row,) = reasoning._spends()
    assert row.job_id == "?" and row.cny > 0
    other = reasoning.prepare_brief("展示玩法", [], PROJECT, B)
    assert other["budget"]["eligible"] is False
    with pytest.raises(ValueError, match="单条"):
        asyncio.run(
            reasoning.execute_within_budget(other["preparedHash"], other["snapshotFingerprint"])
        )
    assert path.read_bytes() == b"{}"


@pytest.mark.parametrize("frozen", [True, False])
def test_legacy_child_damage_cannot_reset_sibling_budget(
    service: CreationJobs, frozen: bool
) -> None:
    root, child, sibling = "1" * 32, "2" * 32, "3" * 32
    _job(service, root, "plan", {"projectId": PROJECT})
    for job_id in (child, sibling):
        _job(service, job_id, "revision", {"parentJobId": root})
    reasoning = _reasoning(service)
    snapshot = brief_snapshot("展示玩法", [])
    prepared = reasoning._prepare(snapshot, PROJECT, child, "", "", "brief")
    record = reasoning._prepared(prepared["preparedHash"])
    assert record["budgetKey"] == root
    if not frozen:
        record.pop("budgetKey")
    prepared_hash = _digest(record)
    if prepared_hash != prepared["preparedHash"]:
        _write(reasoning._directory(prepared_hash), "prepared.json", record)
    original_prepared = (reasoning._directory(prepared_hash) / "prepared.json").read_bytes()
    attempt = reasoning._directory(prepared_hash) / "attempt"
    _write(
        attempt / "planned",
        "confirmation.json",
        {
            "schemaVersion": CONFIRMATION_SCHEMA,
            "confirmedAt": "2026-11-13T00:00:00+08:00",
            "budgetCeilingCny": "1",
        },
    )
    _write(
        attempt / "result",
        "result.json",
        {
            "schemaVersion": RESULT_SCHEMA,
            "preparedHash": prepared_hash,
            "status": "completed",
            "billing": {"knownCostCny": "1"},
        },
    )
    original_result = (attempt / "result/result.json").read_bytes()
    sibling_prepared = reasoning._prepare(snapshot, PROJECT, sibling, "", "", "brief")
    path = service.jobs / child / "request.json"
    damaged = service.read(path)
    damaged["digest"] = "0" * 64
    service.save(path, damaged)
    (row,) = reasoning._spends()
    assert row.job_id == (root if frozen else "?")
    assert row.cny == Decimal("1")
    assert not reasoning._budget_decision(
        reasoning._prepared(sibling_prepared["preparedHash"])
    ).allowed
    with pytest.raises(ValueError, match="单条"):
        asyncio.run(
            reasoning.execute_within_budget(
                sibling_prepared["preparedHash"], sibling_prepared["snapshotFingerprint"]
            )
        )
    assert (reasoning._directory(prepared_hash) / "prepared.json").read_bytes() == original_prepared
    assert (attempt / "result/result.json").read_bytes() == original_result
    assert reasoning.read_result(prepared_hash)["status"] == "completed"


@pytest.mark.parametrize("schema", ["plan-proposal-v1", "plan-proposal-v2"])
def test_old_unfrozen_plan_adoption_resolves_legacy_root_without_rewriting(
    service: CreationJobs, schema: str
) -> None:
    reasoning = _reasoning(service)
    root, adopted = "1" * 32, "2" * 32
    original = {"projectId": PROJECT, "requestId": "0" * 32}
    _job(service, root, "plan", original)
    snapshot = create_plan_snapshot(planner_brief(), timelines(), 30)
    if schema == "plan-proposal-v2":
        snapshot = with_knowledge(snapshot, [{"entryId": "c" * 64, "text": "registered reference"}])
    response = reasoning._prepare(snapshot, PROJECT, root, "", "", "plan")
    record = reasoning._prepared(response["preparedHash"])
    assert record["budgetKey"] == root
    request_hash = record["requestHash"]
    record.pop("budgetKey")
    assert record["request"]["schema_version"] == schema
    prepared_hash = _digest(record)
    _write(reasoning._directory(prepared_hash), "prepared.json", record)
    path = reasoning._directory(prepared_hash) / "prepared.json"
    original_bytes = path.read_bytes()
    _job(service, adopted, "plan", adoption_request(original, prepared_hash))
    assert resolve_budget_key(service, adopted, PROJECT, reasoning._prepared) == root
    assert reasoning._record_key(reasoning._prepared(prepared_hash)) == root
    assert reasoning._prepared(prepared_hash)["requestHash"] == request_hash
    assert path.read_bytes() == original_bytes


def test_brief_http_new_scope_and_old_contract(service: CreationJobs) -> None:
    _work(service)
    reasoning = _reasoning(service)
    for extra in ({}, {"projectId": PROJECT, "workId": A}):
        response = reasoning_post(
            reasoning, {"action": "prepare_brief", "text": "展示玩法", "games": [], **extra}
        )
        record = reasoning._prepared(response["preparedHash"])
        assert record.get("budgetKey") == ("work:" + A if extra else None)
    for extra in ({"workId": A}, {"projectId": PROJECT}, {"projectId": None, "workId": None}):
        with pytest.raises(ValueError):
            reasoning_post(
                reasoning, {"action": "prepare_brief", "text": "展示玩法", "games": [], **extra}
            )
