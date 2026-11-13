"""Saved-version AI narration uses the existing budget, evidence and recovery path."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_reasoning_service import Transport
from test_creation_revision_jobs import revisions  # noqa: F401

from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.domain.errors import AppError
from gamingcreator.ui import creation_reasoning_service as module
from gamingcreator.ui.creation_reasoning_http import reasoning_post
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService


@pytest.fixture
def context(revisions, monkeypatch):  # noqa: F811
    jobs, root, _ = revisions
    entries = [
        {
            "entryId": "entry",
            "text": "能量等待恢复",
            "title": "角色手册",
            "source": {"kind": "manual", "label": "登记出处"},
        }
    ]
    monkeypatch.setattr(module, "planning_knowledge", lambda *args: entries)
    transport = Transport({})
    reasoning = CreationReasoningService(
        jobs,
        price_snapshot=DEEPSEEK_FLASH_20261004,
        transport=transport,
    )
    prepared = reasoning_post(
        reasoning,
        {
            "action": "prepare_narration",
            "jobId": root,
            "planId": "hook-first",
        },
    )
    frozen = json.loads(prepared["payloadPreview"]["user"])["snapshot"]
    clip = next(row for row in frozen["clips"] if row["scriptDraft"].strip())
    transport.content = {
        "schemaVersion": "narration-understanding-v1",
        "snapshotFingerprint": prepared["snapshotFingerprint"],
        "lines": [
            {
                "clipId": clip["clipId"],
                "text": "一起出发",
                "observationQuote": clip["scriptDraft"][:20],
                "knowledgeUses": [{"entryId": "entry", "quote": "等待恢复"}],
            }
        ],
    }
    return SimpleNamespace(
        jobs=jobs,
        root=root,
        service=reasoning,
        transport=transport,
        prepared=prepared,
        frozen=frozen,
        entries=entries,
    )


def execute(context):
    return asyncio.run(
        context.service.execute_within_budget(
            context.prepared["preparedHash"],
            context.prepared["snapshotFingerprint"],
        )
    )


def test_real_saved_chain_prepare_auto_budget_script_and_recovery(context):
    prepared = context.prepared
    assert prepared["purpose"] == "narration" and prepared["budget"]["eligible"]
    assert prepared["maxOutputTokens"] == 8192
    assert prepared["payloadSummary"]["clipCount"] == len(context.frozen["clips"])
    assert "sourcePath" not in prepared["payloadPreview"]["user"]
    assert "sourceSha256" not in prepared["payloadPreview"]["user"]
    assert prepared["maxCostCny"] == str(
        DEEPSEEK_FLASH_20261004.reservation_cny(
            DEEPSEEK_FLASH_20261004.context_limit_tokens,
            8192,
        )
    )
    result = execute(context)
    assert result["status"] == "completed", result
    assert result["purpose"] == "narration"
    assert result["script"]["text"] == "一起出发。"
    assert context.transport.calls[0]["max_tokens"] == 8192
    before = context.service.read_provider_output(prepared["preparedHash"])
    restarted = CreationReasoningService(
        context.jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=context.transport
    )
    assert restarted.read_result(prepared["preparedHash"]) == result
    context.service = restarted
    assert execute(context) == result
    assert len(context.transport.calls) == 1
    assert restarted.read_provider_output(prepared["preparedHash"]) == before
    with pytest.raises(ValueError):
        restarted.revision_for_application(prepared["preparedHash"])


def test_prepared_knowledge_is_frozen_even_if_catalog_changes(context):
    context.entries[0]["text"] = "新版本不再相同"
    context.entries[0]["source"]["label"] = "新出处"
    result = execute(context)
    assert result["status"] == "completed", result
    assert result["script"]["citations"] == [
        {
            "entryId": "entry",
            "text": "能量等待恢复",
            "citation": "角色手册 · 登记出处 · entry",
        }
    ]
    sent = json.loads(context.transport.calls[0]["messages"][1]["content"])["snapshot"]
    assert sent["knowledge"] == context.frozen["knowledge"]


def test_changed_saved_source_rejected_before_send(context):
    source = context.jobs.directory(context.root) / "plans.json"
    source.write_text("{}", encoding="utf-8")
    with pytest.raises((ValueError, AppError)):
        execute(context)
    assert context.transport.calls == []


def test_changed_budget_scope_rejected_before_send(context, monkeypatch):
    monkeypatch.setattr(context.service, "_scope_key", lambda *args: "work:changed")
    with pytest.raises(ValueError, match="预算"):
        execute(context)
    assert context.transport.calls == []


@pytest.mark.parametrize("invalid", ["unknown_clip", "over_budget"])
def test_invalid_output_is_retained_and_never_automatically_retried(context, invalid):
    if invalid == "unknown_clip":
        context.transport.content["lines"][0]["clipId"] = "not-in-saved-version"
    else:
        context.transport.content["lines"][0]["text"] = "字" * (
            context.frozen["budgetCharacters"] + 1
        )
    result = execute(context)
    assert result["status"] == "failed"
    assert result["failureStage"] == "validate_proposal"
    saved = context.service.read_provider_output(context.prepared["preparedHash"])
    assert saved["output"] == context.transport.content
    assert context.service.read_result(context.prepared["preparedHash"]) == result
    with pytest.raises(ValueError, match="consumed"):
        execute(context)
    assert len(context.transport.calls) == 1


def test_existing_template_remains_readable_after_ai_narration(context):
    old = context.jobs.narration_script(context.root, "hook-first")
    assert old["generator"] == "offline-template-v2"
    assert old["schemaVersion"] == "creation-narration-script-v1"
    result = execute(context)
    assert result["status"] == "completed", result
    assert context.jobs.narration_script(context.root, "hook-first") == old
    assert set(old) <= set(result["script"])


@pytest.mark.parametrize("extra", [{"path": "private"}, {"instruction": "extra"}])
def test_prepare_http_rejects_unagreed_fields(context, extra):
    with pytest.raises(ValueError, match="fields"):
        reasoning_post(
            context.service,
            {"action": "prepare_narration", "jobId": context.root, "planId": "hook-first", **extra},
        )
