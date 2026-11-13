"""A persisted work survives multiple real job registrations and budgeted fake-model calls."""

import asyncio
from decimal import Decimal

import pytest
from test_brief_reasoning import GAMES, SENTENCE, answer
from test_creation_jobs import finish, request, service  # noqa: F401
from test_creation_reasoning_service import Transport
from test_plan_proposals import output
from test_plan_reasoning_jobs import planning  # noqa: F401

from gamingcreator.application import ai_budget
from gamingcreator.application.brief_reasoning import brief_snapshot
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.infrastructure.creation_work_store import CreationWorkStore
from gamingcreator.ui.creation_budget_scope import resolve_budget_key
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService

PROJECT = "artifacts/project"
WORK = "a" * 32


def auto(reasoning, prepared):
    return asyncio.run(
        reasoning.execute_within_budget(prepared["preparedHash"], prepared["snapshotFingerprint"])
    )


def test_brief_regenerated_roots_adoption_render_and_restart_share_budget(planning):  # noqa: F811
    jobs = planning.jobs
    CreationWorkStore(jobs.root / "works").create(PROJECT, WORK)
    transport = Transport(answer(brief_snapshot(SENTENCE, GAMES)))
    reasoning = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    prepared = reasoning.prepare_brief(SENTENCE, GAMES, PROJECT, WORK)
    assert auto(reasoning, prepared)["status"] == "completed"
    for request_id in ("c" * 32, "d" * 32):
        req = request()
        req.update(requestId=request_id, workId=WORK)
        req["brief"]["targetDuration"] = 6
        root = jobs.submit("plan", req)["jobId"]
        assert finish(jobs, root)["status"] == "completed"
        prepared = reasoning.prepare_plan(root)
        record = reasoning._prepared(prepared["preparedHash"])
        transport.content = output(reasoning._current(record), ((3, 1),))
        assert auto(reasoning, prepared)["status"] == "completed"
    adopted = reasoning.adopt_plan(prepared["preparedHash"])["jobId"]
    assert finish(jobs, adopted)["status"] == "completed"
    render = jobs.submit(
        "render",
        {
            "requestId": "e" * 32,
            "planJobId": adopted,
            "planId": "dynamic-1",
            "width": 64,
            "height": 48,
        },
    )["jobId"]
    assert finish(jobs, render)["status"] == "completed"
    assert resolve_budget_key(jobs, render, PROJECT, reasoning._prepared) == "work:" + WORK
    before = reasoning._spends()
    assert len(before) == len(transport.calls) == 3
    assert {row.job_id for row in before} == {"work:" + WORK}
    restarted_jobs = CreationJobs(jobs.repository)
    restarted = CreationReasoningService(restarted_jobs, price_snapshot=DEEPSEEK_FLASH_20261004)
    assert restarted._spends() == before
    assert (
        resolve_budget_key(restarted_jobs, render, PROJECT, restarted._prepared) == "work:" + WORK
    )
    budget = restarted.prepare_brief(SENTENCE, GAMES, PROJECT, WORK)["budget"]
    assert Decimal(budget["videoSpentCny"]) == sum((row.cny for row in before), Decimal(0))
    assert all(row.cny > 0 for row in before)  # fake model has no usage; keep its ceiling


@pytest.mark.parametrize("cap", ["video", "month"])
def test_concurrent_work_calls_reserve_before_send(service, monkeypatch, cap):  # noqa: F811
    store = CreationWorkStore(service.root / "works")
    store.create(PROJECT, WORK)
    other = "b" * 32 if cap == "month" else WORK
    store.create(PROJECT, other)
    transport = Transport(answer(brief_snapshot(SENTENCE, GAMES)))
    reasoning = CreationReasoningService(
        service, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    prepared = [reasoning.prepare_brief(SENTENCE, GAMES, PROJECT, work) for work in (WORK, other)]
    ceiling = Decimal(prepared[0]["budget"]["ceilingCny"])
    monkeypatch.setattr(
        ai_budget,
        "MONTHLY_CAP_CNY" if cap == "month" else "PER_VIDEO_CAP_CNY",
        ceiling * Decimal("1.5"),
    )

    async def race():
        return await asyncio.gather(
            *(
                reasoning.execute_within_budget(p["preparedHash"], p["snapshotFingerprint"])
                for p in prepared
            ),
            return_exceptions=True,
        )

    results = asyncio.run(race())
    assert len(transport.calls) == 1
    assert (
        sum(isinstance(result, dict) and result["status"] == "completed" for result in results) == 1
    )
    assert sum(isinstance(result, ValueError) for result in results) == 1
    assert sum((row.cny for row in reasoning._spends()), Decimal(0)) == ceiling
