"""Real job registration/receipts with fake text transport; no cloud calls."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401
from test_creation_reasoning_service import Transport, context  # noqa: F401
from test_plan_proposals import output, timelines

from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.rendering import validate_render_plan
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.creation_reasoning_http import reasoning_post
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService
from gamingcreator.ui.plan_reasoning_jobs import adoption_request, original_snapshot


@pytest.fixture
def planning(service, monkeypatch):  # noqa: F811
    source = service.repository / "footage/source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"original footage fixture")
    timeline = timelines()[0]
    timeline.run.asset = replace(
        timeline.run.asset, source_path=source, sha256=sha256(source.read_bytes()).hexdigest()
    )

    async def completed(run):
        assert run == "run"
        return timeline

    async def load_run(run):
        return timeline.run

    async def close():
        pass

    async def open_store(*args, **kwargs):
        return SimpleNamespace(load_run=load_run, load_completed_timeline=completed, close=close)

    monkeypatch.setattr(SqliteTimelineStore, "open", open_store)
    req = request()
    req["brief"]["targetDuration"] = 6
    root = service.submit("plan", req)["jobId"]
    assert finish(service, root)["status"] == "completed"
    snapshot, _ = original_snapshot(service, root)
    transport = Transport(output(snapshot, ((3, 1),)))
    reasoning = CreationReasoningService(
        service, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    return SimpleNamespace(
        jobs=service,
        root=root,
        timeline=timeline,
        source=source,
        transport=transport,
        reasoning=reasoning,
    )


def prepared(ctx):
    return reasoning_post(ctx.reasoning, {"action": "prepare_plan", "jobId": ctx.root})


def execute(ctx, prep):
    return asyncio.run(
        ctx.reasoning.execute(
            prep["preparedHash"], prep["snapshotFingerprint"], Decimal(prep["maxCostCny"])
        )
    )


def test_prepare_confirm_adopt_real_jobs_and_render_validation(planning):
    ctx = planning
    prep = prepared(ctx)
    assert prep["purpose"] == "plan" and not ctx.transport.calls
    assert prep["originalRequest"]["brief"]["targetDuration"] == 6
    assert "sourcePath" not in json.dumps(prep)
    result = execute(ctx, prep)
    assert result["status"] == "completed"
    assert len(ctx.transport.calls) == 1
    assert result["planPreview"]["plans"][0]["actualFrames"] == 180
    assert "sourcePath" not in json.dumps(result)
    adopted = reasoning_post(
        ctx.reasoning, {"action": "adopt_plan", "preparedHash": prep["preparedHash"]}
    )
    state = finish(ctx.jobs, adopted["jobId"])
    assert state["kind"] == "plan" and state["status"] == "completed"
    repeated = ctx.reasoning.adopt_plan(prep["preparedHash"])
    assert repeated["jobId"] == adopted["jobId"]
    assert len(ctx.transport.calls) == 1
    report = ctx.jobs.plan_report(ctx.jobs.directory(adopted["jobId"]))
    assert report["reasoningProvenance"]["promptVersion"] == "plan-reasoning-prompt-v1"
    render = validate_render_plan(
        select_edit_decision(report, "dynamic-1"), report, (ctx.timeline,)
    )
    assert render.frames == 180


@pytest.mark.parametrize("fault", ["brief", "events", "ranges", "source", "saved-request"])
def test_changed_inputs_rejected_before_send_or_adopt(planning, fault):
    ctx = planning
    prep = prepared(ctx)
    if fault == "source":
        ctx.source.write_bytes(b"changed footage")
    elif fault == "saved-request":
        path = ctx.jobs.directory(ctx.root) / "request.json"
        stored = ctx.jobs.read(path)
        stored["request"]["brief"]["objective"] = "changed"
        ctx.jobs.save(path, stored)
    else:
        _, original = original_snapshot(ctx.jobs, ctx.root)
        adopted = adoption_request(original, prep["preparedHash"])
        if fault == "brief":
            adopted["brief"] = {**adopted["brief"], "objective": "forged"}
        elif fault == "events":
            adopted["eventIds"] = ["run:forged"]
        else:
            adopted["clipRanges"] = [
                {"runId": "run", "eventId": "run:forged", "startUs": 0, "endUs": 1}
            ]
        execute(ctx, prep)
        with pytest.raises((ValueError, AppError)):
            ctx.jobs.submit("plan", adopted)
        assert len(ctx.transport.calls) == 1
        return
    with pytest.raises((ValueError, AppError)):
        execute(ctx, prep)
    assert not ctx.transport.calls
    with pytest.raises((ValueError, AppError)):
        ctx.reasoning.adopt_plan(prep["preparedHash"])


def test_source_mutation_after_success_blocks_adoption(planning):
    prep = prepared(planning)
    execute(planning, prep)
    planning.source.write_bytes(b"changed after model result")
    with pytest.raises(ValueError, match="source bytes"):
        planning.reasoning.adopt_plan(prep["preparedHash"])
    assert len(planning.transport.calls) == 1


def test_edit_result_cannot_adopt_as_plan(context):  # noqa: F811
    prep = context.service.prepare("job", "plan", "调整节奏")
    result = asyncio.run(
        context.service.execute(
            prep["preparedHash"], prep["snapshotFingerprint"], Decimal(prep["maxCostCny"])
        )
    )
    assert result["status"] == "completed"
    with pytest.raises(ValueError, match="edit result"):
        context.service.adopt_plan(prep["preparedHash"])
    assert len(context.transport.calls) == 1


def test_plan_proposal_cannot_enter_edit_application(planning):
    prep = prepared(planning)
    execute(planning, prep)
    with pytest.raises(ValueError, match="cannot edit"):
        planning.reasoning.revision_for_application(prep["preparedHash"])


def test_changed_observation_range_rejects_prepared_snapshot(planning):
    from gamingcreator.domain.time import SourceRange

    prep = prepared(planning)
    event = planning.timeline.events[0]
    planning.timeline.events = (
        replace(event, source_range=SourceRange(0, 2_000_000, 30_000_000)),
        *planning.timeline.events[1:],
    )
    with pytest.raises(ValueError, match="inputs changed"):
        execute(planning, prep)
    assert not planning.transport.calls


def test_worker_rechecks_source_after_registration(planning, monkeypatch):
    import gamingcreator.ui.plan_reasoning_jobs as module
    from gamingcreator.ui.plan_reasoning_jobs import save_plan as real_save

    prep = prepared(planning)
    execute(planning, prep)

    def changed_before_save(jobs, directory, request):
        planning.source.write_bytes(b"mutated between submit and execution")
        real_save(jobs, directory, request)

    monkeypatch.setattr(module, "save_plan", changed_before_save)
    adopted = planning.reasoning.adopt_plan(prep["preparedHash"])
    assert finish(planning.jobs, adopted["jobId"])["status"] == "failed"
    assert len(planning.transport.calls) == 1


@pytest.mark.parametrize(
    "value",
    [
        {"action": "prepare_plan", "jobId": "a", "brief": {}},
        {"action": "adopt_plan", "preparedHash": "a", "jobId": "b"},
    ],
)
def test_plan_http_rejects_extra_fields(planning, value):
    with pytest.raises(ValueError, match="fields"):
        reasoning_post(planning.reasoning, value)
    assert not planning.transport.calls
