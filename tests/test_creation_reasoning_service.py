import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_proposals import SHA, output
from test_creation_render import decision
from test_creation_revision_jobs import revisions  # noqa: F401

from gamingcreator.application.creation_proposals import create_snapshot
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.http_transport import HttpResponse, TransportError
from gamingcreator.ui import creation_reasoning_service as module
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService
from gamingcreator.ui.revision_jobs import load_chain


class Transport:
    def __init__(self, content, failure=None):
        self.content = content
        self.failure = failure
        self.calls = []

    async def post(self, payload, timeout_seconds):
        self.calls.append(payload)
        await asyncio.sleep(0.01)
        if self.failure:
            raise self.failure
        body = {
            "model": "unrecognized-model",
            "id": "req-123",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(self.content)},
                }
            ],
        }
        return HttpResponse(200, json.dumps(body).encode())


@pytest.fixture
def context(tmp_path, monkeypatch):
    jobs = CreationJobs(tmp_path)
    root, _, _ = decision()
    chain = SimpleNamespace(
        plan_id="plan",
        digest="a" * 64,
        root_sha=SHA,
        edl=root,
        project_id="projects/registered",
        manifest=None,
    )
    loads = []

    def load_chain(received_jobs, job_id, plan_id):
        assert received_jobs is jobs and job_id == "job" and plan_id == "plan"
        loads.append(job_id)
        return chain

    monkeypatch.setattr(module, "load_chain", load_chain)
    snapshot = create_snapshot("job", "plan", chain.digest, SHA, root)
    transport = Transport(output(snapshot))
    reasoning = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    return SimpleNamespace(
        jobs=jobs, chain=chain, transport=transport, service=reasoning, loads=loads
    )


def execute(ctx, prepared, amount=None):
    return asyncio.run(
        ctx.service.execute(
            prepared["preparedHash"],
            prepared["snapshotFingerprint"],
            amount or Decimal(prepared["maxCostCny"]),
        )
    )


def test_execute_with_real_saved_chain(revisions):  # noqa: F811
    jobs, root, _ = revisions
    chain = load_chain(jobs, root, "hook-first")
    snapshot = create_snapshot(root, chain.plan_id, chain.digest, chain.root_sha, chain.edl)
    transport = Transport(output(snapshot))
    reasoning = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    prepared = reasoning.prepare(root, "hook-first", "调整节奏")
    result = asyncio.run(
        reasoning.execute(
            prepared["preparedHash"],
            prepared["snapshotFingerprint"],
            Decimal(prepared["maxCostCny"]),
        )
    )
    assert result["status"] == "completed", result
    assert len(transport.calls) == 1
    assert reasoning.read_result(prepared["preparedHash"]) == result
    revised = reasoning.revision_for_application(prepared["preparedHash"])
    assert revised["schemaVersion"] == "edit-decision-revision-v3"


def test_prepare_quote_and_public_text_summary(context):
    prepared = context.service.prepare("job", "plan", "让节奏舒展一些")
    quote = DEEPSEEK_FLASH_20261004.reservation_cny(
        DEEPSEEK_FLASH_20261004.context_limit_tokens, 2048
    )
    assert Decimal(prepared["maxCostCny"]) == quote
    assert prepared["payloadSummary"]["inputFrames"] == 0
    assert prepared["payloadSummary"]["textOnly"] is True
    assert "sourcePath" not in str(prepared) and "projects/registered" not in str(prepared)
    result = execute(context, prepared)
    assert result["status"] == "completed"
    payload = context.transport.calls[0]
    assert "sourcePath" not in str(payload) and "sourceSha256" not in str(payload)
    assert result["billing"]["reservedCny"] == str(quote)
    assert result["billing"]["unresolvedAttempts"] == 1
    revision = context.service.revision_for_application(prepared["preparedHash"])
    assert revision["schemaVersion"] == "edit-decision-revision-v3"
    assert len(context.loads) >= 3


def test_restart_returns_saved_result_without_repay(context):
    prepared = context.service.prepare("job", "plan", "调整")
    first = execute(context, prepared)
    context.service = CreationReasoningService(
        context.jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=context.transport
    )
    assert context.service.read_result(prepared["preparedHash"]) == first
    assert execute(context, prepared) == first
    assert len(context.transport.calls) == 1


def test_concurrent_execute_has_one_sender(context):
    prepared = context.service.prepare("job", "plan", "调整")
    another = CreationReasoningService(
        context.jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=context.transport
    )

    async def run():
        arguments = (
            prepared["preparedHash"],
            prepared["snapshotFingerprint"],
            Decimal(prepared["maxCostCny"]),
        )
        return await asyncio.gather(
            context.service.execute(*arguments), another.execute(*arguments), return_exceptions=True
        )

    results = asyncio.run(run())
    assert sum(isinstance(result, dict) for result in results) == 1
    assert any(isinstance(result, AppError) for result in results)
    assert len(context.transport.calls) == 1


@pytest.mark.parametrize(
    "fault", ["fingerprint", "amount", "parent", "project", "hash", "parameters"]
)
def test_mismatch_zero_send(context, fault):
    prepared = context.service.prepare("job", "plan", "调整")
    if fault == "fingerprint":
        prepared["snapshotFingerprint"] = "c" * 64
    elif fault == "parent":
        context.chain.digest = "d" * 64
    elif fault == "project":
        context.chain.project_id = "other-project"
    elif fault == "hash":
        prepared["preparedHash"] = "../other"
    elif fault == "parameters":
        path = context.service._directory(prepared["preparedHash"]) / "prepared.json"
        path.write_text(path.read_text(encoding="utf-8").replace("调整", "删除"), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        execute(context, prepared, Decimal("0.01") if fault == "amount" else None)
    assert not context.transport.calls


@pytest.mark.parametrize("mode", ["failed", "cancelled", "invalid_json"])
def test_failed_unknown_not_repaid(context, mode):
    if mode == "failed":
        context.transport.failure = TransportError("provider.network")
    elif mode == "cancelled":
        context.transport.failure = asyncio.CancelledError()
    else:
        context.transport.content = {"invalid": "output"}
    prepared = context.service.prepare("job", "plan", "调整")
    result = execute(context, prepared)
    assert result["status"] in ("failed", "cancelled")
    assert result["billing"]["unresolvedAttempts"] == 1
    with pytest.raises(ValueError, match="consumed"):
        execute(context, prepared)
    assert len(context.transport.calls) == 1
    assert context.service.read_result(prepared["preparedHash"]) == result


def test_planned_interruption_blocks_retry(context):
    prepared = context.service.prepare("job", "plan", "调整")
    directory = context.service._directory(prepared["preparedHash"]) / "attempt/planned"
    directory.mkdir(parents=True)
    with pytest.raises(ValueError, match="consumed"):
        execute(context, prepared)
    assert not context.transport.calls


def test_new_prepare_is_new_intent_not_hidden_retry(context):
    first = context.service.prepare("job", "plan", "调整")
    second = context.service.prepare("job", "plan", "调整")
    assert first["preparedHash"] != second["preparedHash"]
    assert first["requestHash"] == second["requestHash"]
    assert not context.transport.calls


def test_clarification_never_creates_revision(context):
    context.transport.content.update(
        kind="clarification", clips=[], questions=["哪个镜头有 logo？"]
    )
    prepared = context.service.prepare("job", "plan", "删掉 logo")
    result = execute(context, prepared)
    assert result["status"] == "completed"
    assert result["proposal"]["response"]["kind"] == "clarification"
    with pytest.raises(ValueError, match="no edit"):
        context.service.revision_for_application(prepared["preparedHash"])
    context.chain.digest = "e" * 64
    assert execute(context, prepared) == result


def test_apply_reloads_parent(context):
    prepared = context.service.prepare("job", "plan", "调整")
    execute(context, prepared)
    context.chain.digest = "e" * 64
    with pytest.raises(ValueError, match="parent changed"):
        context.service.revision_for_application(prepared["preparedHash"])


def test_no_price_no_execute(context):
    with pytest.raises(ValueError, match="price snapshot"):
        CreationReasoningService(context.jobs, price_snapshot=None)
    assert not context.transport.calls


def test_persisted_confirmation_and_provider_records(context):
    prepared = context.service.prepare("job", "plan", "调整")
    execute(context, prepared)
    directory = context.service._directory(prepared["preparedHash"]) / "attempt"
    confirmation = module._read(
        directory / "planned", "confirmation.json", "creation-reasoning-confirmation-v1"
    )
    assert confirmation["confirmationSource"] == "execute-api-parameters"
    assert confirmation["preparedHash"] == prepared["preparedHash"]
    assert confirmation["confirmedMaxCny"] == prepared["maxCostCny"]
    for phase in ("provider-start", "provider-finish"):
        record = module._read(
            directory / phase, "invocation.json", "creation-reasoning-invocation-v1"
        )
        assert record["metadata"]["provider"] == "deepseek"
        assert record["metadata"]["usage"]["cost_cny"] is None
    assert not (directory / "provider-start/invocation.json").read_bytes().find(b"API_KEY") >= 0


def test_result_corruption_cannot_trigger_repayment(context):
    prepared = context.service.prepare("job", "plan", "调整")
    execute(context, prepared)
    directory = context.service._directory(prepared["preparedHash"]) / "attempt/result"
    (directory / "result.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        execute(context, prepared)
    assert len(context.transport.calls) == 1


def test_service_v4_application_uses_existing_manifest_revision_path(context, monkeypatch):
    from gamingcreator.application.creation_editing import build_revision
    from gamingcreator.application.creation_proposals import clip_rows
    from gamingcreator.application.creation_replacements import (
        build_revision_v4,
        candidate_manifest_sha,
    )

    before = create_snapshot("job", "plan", context.chain.digest, SHA, context.chain.edl)
    parent = build_revision(context.chain.edl, SHA, clip_rows(before))
    manifest = {
        "schemaVersion": "creation-candidates-v1",
        "rootReceiptSha256": SHA,
        "candidates": [],
    }
    parent.update(
        schemaVersion="edit-decision-revision-v4",
        candidateManifestSha256=candidate_manifest_sha(manifest),
        replacements=[],
    )
    context.chain.edl = parent
    context.chain.manifest = manifest
    prepared = context.service.prepare("job", "plan", "调整")
    result = execute(context, prepared)
    assert result["status"] == "completed"
    seen = []

    def prepare_revision(jobs, request, chain):
        assert jobs is context.jobs and chain is context.chain
        assert request["candidateManifestSha256"] == candidate_manifest_sha(manifest)
        assert request["replacements"] == []
        seen.append(request)
        return build_revision_v4(
            parent, SHA, chain.digest, request["clips"], [], manifest
        ), manifest

    monkeypatch.setattr(module, "prepare_revision", prepare_revision)
    revised = context.service.revision_for_application(prepared["preparedHash"])
    assert len(seen) == 1 and revised["schemaVersion"] == "edit-decision-revision-v4"
    assert context.chain.edl == parent


def test_service_rejects_forged_price_snapshot(context):
    from dataclasses import replace

    forged = replace(DEEPSEEK_FLASH_20261004, peak_output_per_million=Decimal(0))
    with pytest.raises(ValueError, match="official pilot price"):
        CreationReasoningService(context.jobs, price_snapshot=forged, transport=context.transport)
    assert not context.transport.calls
