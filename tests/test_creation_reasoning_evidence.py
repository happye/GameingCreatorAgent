"""Paid-response retention with fake transports only; no retries or remote calls."""

# ruff: noqa: F811

import json
from hashlib import sha256

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_reasoning_service import context, execute  # noqa: F401
from test_plan_reasoning_jobs import execute as execute_plan
from test_plan_reasoning_jobs import planning, prepared  # noqa: F401

from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.infrastructure.http_transport import HttpResponse
from gamingcreator.ui import creation_reasoning_service as module
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService


def rewrite_record(directory, filename, document):
    """Simulate a coherently rewritten record, beyond a simple damaged file."""
    raw = json.dumps(document, ensure_ascii=False).encode()
    (directory / filename).write_bytes(raw)
    (directory / "receipt.json").write_text(
        json.dumps(
            {"schemaVersion": "creation-receipt-v1", "files": {filename: sha256(raw).hexdigest()}}
        ),
        encoding="utf-8",
    )


def test_invalid_proposal_retained_before_validation_and_restart(context, monkeypatch):
    context.transport.content = {"invalid": "original 中文 output"}
    prep = context.service.prepare("job", "plan", "调整")
    original = module.validate_proposal

    def validate(snapshot, output):
        saved = context.service.read_provider_output(prep["preparedHash"])
        assert saved["output"] == output == context.transport.content
        return original(snapshot, output)

    monkeypatch.setattr(module, "validate_proposal", validate)
    result = execute(context, prep)
    assert result["status"] == "failed" and result["proposal"] is None
    assert result["failureStage"] == "validate_proposal"
    assert result["metadata"]["request_id"] == "req-123"
    assert result["billing"]["unresolvedAttempts"] == 1
    assert "original 中文 output" not in json.dumps(result, ensure_ascii=False)
    context.service = CreationReasoningService(
        context.jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=context.transport
    )
    assert context.service.read_result(prep["preparedHash"]) == result
    assert (
        context.service.read_provider_output(prep["preparedHash"])["output"]
        == context.transport.content
    )
    with pytest.raises(ValueError, match="consumed"):
        execute(context, prep)
    assert len(context.transport.calls) == 1


def test_compile_failure_retains_output_and_controlled_stage(planning, monkeypatch):  # noqa: F811
    prep = prepared(planning)

    def fail_compile(snapshot, proposal):
        saved = planning.reasoning.read_provider_output(prep["preparedHash"])
        assert saved["output"] == planning.transport.content
        raise ValueError("private model text or local path must not enter public diagnostics")

    monkeypatch.setattr(module, "compile_plan_proposal", fail_compile)
    result = execute_plan(planning, prep)
    assert result["status"] == "failed" and result["proposal"] is None
    assert result["failureStage"] == "compile_plan"
    assert "planPreview" not in result and "private model text" not in str(result)
    assert planning.reasoning.read_result(prep["preparedHash"]) == result
    with pytest.raises(ValueError, match="consumed"):
        execute_plan(planning, prep)
    assert len(planning.transport.calls) == 1


@pytest.mark.parametrize("known_usage", [False, True])
def test_evidence_write_failure_blocks_validation_and_preserves_billing(
    context, monkeypatch, known_usage
):
    prep = context.service.prepare("job", "plan", "调整")
    real_write = module._write
    original_post = context.transport.post

    async def known_post(payload, timeout_seconds):
        response = await original_post(payload, timeout_seconds)
        body = json.loads(response.body)
        body.update(
            model="deepseek-flash",
            usage={"prompt_tokens": 20, "completion_tokens": 10, "prompt_cache_hit_tokens": 0},
        )
        return HttpResponse(200, json.dumps(body).encode())

    if known_usage:
        monkeypatch.setattr(context.transport, "post", known_post)

    def fail_output(directory, name, document):
        if name == "output.json":
            raise OSError("private local path")
        real_write(directory, name, document)

    def no_validation(*args):
        pytest.fail("A proposal must not be validated without saved provider evidence")

    monkeypatch.setattr(module, "_write", fail_output)
    monkeypatch.setattr(module, "_validated_output", no_validation)
    result = execute(context, prep)
    assert result["failureStage"] == "persist_output" and result["status"] == "failed"
    assert result["proposal"] is None and "providerOutputSha256" not in result
    assert result["metadata"]["request_id"] == "req-123"
    assert result["billing"]["unresolvedAttempts"] == (0 if known_usage else 1)
    assert (result["billing"]["knownCostCny"] is not None) == known_usage
    assert "private local path" not in str(result)
    assert context.service.read_result(prep["preparedHash"]) == result
    with pytest.raises(ValueError, match="consumed"):
        execute(context, prep)
    assert len(context.transport.calls) == 1


@pytest.mark.parametrize("fault", ["bytes", "identity", "reference", "null-reference"])
def test_evidence_tamper_rejected_without_resend(context, fault):
    prep = context.service.prepare("job", "plan", "调整")
    result = execute(context, prep)
    attempt = context.service._directory(prep["preparedHash"]) / "attempt"
    directory = attempt / "provider-output"
    if fault == "bytes":
        (directory / "output.json").write_text("{}", encoding="utf-8")
    elif fault == "identity":
        document = context.service.read_provider_output(prep["preparedHash"])
        document["preparedHash"] = "0" * 64
        rewrite_record(directory, "output.json", document)
    else:
        result["providerOutputSha256"] = None if fault == "null-reference" else "0" * 64
        rewrite_record(attempt / "result", "result.json", result)
    with pytest.raises(ValueError):
        context.service.read_result(prep["preparedHash"])
    with pytest.raises(ValueError):
        execute(context, prep)
    assert len(context.transport.calls) == 1


def test_legacy_result_without_output_reference_is_readable(context):
    prep = context.service.prepare("job", "plan", "调整")
    result = execute(context, prep)
    result.pop("providerOutputSha256")
    directory = context.service._directory(prep["preparedHash"]) / "attempt/result"
    rewrite_record(directory, "result.json", result)
    assert context.service.read_result(prep["preparedHash"]) == result
    assert execute(context, prep) == result
    assert len(context.transport.calls) == 1


def test_missing_final_result_preserves_offline_evidence_and_blocks_retry(context, monkeypatch):
    prep = context.service.prepare("job", "plan", "调整")
    real_write = module._write

    def interrupt_result(directory, name, document):
        if name == "result.json":
            raise OSError("simulated final disk failure")
        real_write(directory, name, document)

    monkeypatch.setattr(module, "_write", interrupt_result)
    with pytest.raises(OSError, match="final disk failure"):
        execute(context, prep)
    saved = context.service.read_provider_output(prep["preparedHash"])
    assert saved["output"] == context.transport.content
    with pytest.raises(ValueError, match="无法读取"):
        context.service.read_result(prep["preparedHash"])
    with pytest.raises(ValueError, match="consumed"):
        execute(context, prep)
    assert len(context.transport.calls) == 1
