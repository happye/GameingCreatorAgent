"""Theme-aware planning keeps paid legacy identities and uses the existing adoption chain."""

import asyncio
from dataclasses import asdict, replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401
from test_plan_proposals import output
from test_plan_reasoning_jobs import planning  # noqa: F401

from gamingcreator.application import ai_budget
from gamingcreator.application.creation_proposals import canonical
from gamingcreator.application.plan_proposals import with_knowledge
from gamingcreator.application.plan_reasoning import plan_reasoning_request
from gamingcreator.ui.plan_reasoning_jobs import original_snapshot


def theme_root(ctx, ranges=False):
    req = request()
    req["requestId"] = "b" * 32
    req["brief"].update(targetDuration=6, mandatoryTopics=["角色介绍", "技能思路"])
    if ranges:
        ctx.timeline.events = tuple(
            replace(e, event_id=f"run:{e.event_id}") for e in ctx.timeline.events
        )
        req.update(
            eventIds=["run:0", "run:2"],
            clipRanges=[
                {"runId": "run", "eventId": "run:0", "startUs": 0, "endUs": 2_000_000},
                {"runId": "run", "eventId": "run:2", "startUs": 6_000_000, "endUs": 8_000_000},
            ],
        )
    ctx.root = ctx.jobs.submit("plan", req)["jobId"]
    assert finish(ctx.jobs, ctx.root)["status"] == "completed"


def send(ctx, prep):
    return asyncio.run(
        ctx.reasoning.execute(
            prep["preparedHash"], prep["snapshotFingerprint"], Decimal(prep["maxCostCny"])
        )
    )


@pytest.mark.parametrize("knowledge", [False, True])
def test_legacy_topics_keep_request_hash_replay_and_adoption(planning, knowledge):  # noqa: F811
    ctx = planning
    theme_root(ctx)
    snapshot, original = original_snapshot(ctx.jobs, ctx.root)
    if knowledge:
        snapshot = with_knowledge(snapshot, [{"entryId": "c" * 64, "text": "registered reference"}])
    legacy = asdict(plan_reasoning_request(snapshot))
    prep = ctx.reasoning._prepare(snapshot, original["projectId"], ctx.root, "", "", "plan")
    record = ctx.reasoning._prepared(prep["preparedHash"])
    assert record["request"] == legacy
    assert record["requestHash"] == sha256(canonical(legacy).encode()).hexdigest()
    assert ctx.reasoning._current(record).fingerprint == snapshot.fingerprint
    value = output(snapshot, ((3, 1),))
    if knowledge:
        value["schemaVersion"] = "plan-proposal-v2"
        value["plans"][0]["knowledgeUses"] = []
    ctx.transport.content = value
    result = send(ctx, prep)
    assert result["status"] == "completed"
    assert send(ctx, prep) == result
    adopted = ctx.reasoning.adopt_plan(prep["preparedHash"])
    assert finish(ctx.jobs, adopted["jobId"])["status"] == "completed"
    report = ctx.jobs.plan_report(ctx.jobs.directory(adopted["jobId"]))
    assert report["reasoningProvenance"]["requestHash"] == record["requestHash"]
    assert "topicCoverage" not in report["plans"][0]
    assert len(ctx.transport.calls) == 1
    assert ctx.transport.calls[0]["max_tokens"] == 2048


def test_v3_knowledge_selected_ranges_adopt_and_read_back(planning, monkeypatch):  # noqa: F811
    ctx = planning
    from gamingcreator.ui import creation_jobs

    fixture_planner = creation_jobs.execute_plan_creation

    async def planner(*args, clip_ranges=None, **kwargs):
        await fixture_planner(*args, **kwargs)

    monkeypatch.setattr(creation_jobs, "execute_plan_creation", planner)
    theme_root(ctx, ranges=True)
    # A registered reference is frozen into the same topic-aware request.
    from gamingcreator.infrastructure.knowledge_store import KnowledgeStore

    KnowledgeStore(ctx.jobs.repository).add(
        {
            "game": "g",
            "title": "角色介绍",
            "text": "角色介绍与技能思路",
            "sourceKind": "wiki",
            "sourceLabel": "registered wiki",
        }
    )
    prep = ctx.reasoning.prepare_plan(ctx.root)
    record = ctx.reasoning._prepared(prep["preparedHash"])
    snapshot = ctx.reasoning._current(record)
    assert record["request"]["prompt_version"] == "plan-reasoning-prompt-v3"
    assert snapshot.payload["knowledge"]
    value = output(snapshot, ((2, 1),))
    value["schemaVersion"] = "plan-proposal-v3"
    value["plans"][0]["knowledgeUses"] = []
    for shot in value["plans"][0]["shots"]:
        candidate = next(
            c for c in snapshot.payload["candidates"] if c["candidateId"] == shot["candidateId"]
        )
        shot["topicUses"] = [
            {
                "topic": "角色介绍",
                "rationale": "用这段画面介绍角色，需预览核对",
                "observationQuote": candidate["facts"][0],
            }
        ]
    ctx.transport.content = value
    result = send(ctx, prep)
    assert result["status"] == "completed", result
    assert "sourcePath" not in canonical(result)
    adopted = ctx.reasoning.adopt_plan(prep["preparedHash"])
    assert finish(ctx.jobs, adopted["jobId"])["status"] == "completed"
    report = ctx.jobs.plan_report(ctx.jobs.directory(adopted["jobId"]))
    plan = report["plans"][0]
    assert plan["topicCoverage"] == result["planPreview"]["plans"][0]["topicCoverage"]
    assert plan["topicCoverage"][1]["status"] == "missing"
    assert report["understandingVerified"] is False and plan["ready"]
    from gamingcreator.application.edit_decision import select_edit_decision
    from gamingcreator.application.rendering import validate_render_plan

    rendered = validate_render_plan(
        select_edit_decision(report, plan["id"]), report, (ctx.timeline,)
    )
    assert rendered.frames == plan["actualFrames"]
    assert [(s["startUs"], s["endUs"]) for s in plan["segments"]] == [
        (6_000_000, 8_000_000),
        (0, 2_000_000),
    ]
    assert len(ctx.transport.calls) == 1
    assert prep["maxOutputTokens"] == ctx.transport.calls[0]["max_tokens"] == 8192


@pytest.mark.parametrize("cap", ["video", "month"])
def test_v3_rechecks_8192_token_ceiling_under_budget_lock(planning, monkeypatch, cap):  # noqa: F811
    ctx = planning
    theme_root(ctx)
    prep = ctx.reasoning.prepare_plan(ctx.root)
    record = ctx.reasoning._prepared(prep["preparedHash"])
    request = record["request"]
    ceiling = ai_budget.call_ceiling_cny(
        ctx.reasoning.price, request["system"] + request["user"], 8192
    )
    assert prep["budget"]["eligible"] and Decimal(prep["budget"]["ceilingCny"]) == ceiling
    limit = ai_budget.PER_VIDEO_CAP_CNY if cap == "video" else ai_budget.MONTHLY_CAP_CNY
    row = ai_budget.Spend(
        datetime.now().astimezone().strftime("%Y-%m"),
        ctx.root if cap == "video" else "other-video",
        limit - ceiling / 2,
    )
    # Another call consumed the remaining allowance after the UI received the quote.
    monkeypatch.setattr(ctx.reasoning, "_spends", lambda: [row])
    with pytest.raises(ValueError, match="单独确认"):
        asyncio.run(
            ctx.reasoning.execute_within_budget(prep["preparedHash"], prep["snapshotFingerprint"])
        )
    assert not ctx.transport.calls
