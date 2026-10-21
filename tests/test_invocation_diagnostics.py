"""Offline failure diagnostics expose http/schema projections without re-calling models."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from test_sqlite_store import CONFIG, bundle_fixture

from gamingcreator.application.invocation_diagnostics import invocation_failure_diagnostics
from gamingcreator.application.providers import InvocationMetadata, ProviderUsage
from gamingcreator.application.storage import InvocationStatus, RunStatus, StoredInvocation
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.service import inspect_run


def _metadata(**details: object) -> InvocationMetadata:
    return InvocationMetadata(
        "deepseek",
        "deepseek-flash",
        None,
        None,
        "fixture",
        "2",
        1,
        ProviderUsage(),
        execution_details=json.dumps(details, sort_keys=True),
    )


def test_failure_diagnostics_clip_http_and_schema_projections():
    failed = StoredInvocation(
        "inv-1",
        "run-1",
        "vision-000021",
        "logical-1",
        InvocationStatus.FAILED,
        _metadata(
            schemaError="event_frame_boundaries",
            schemaDetail="start and end map to the same source frame",
            schemaProjection={"responseSha256": "a" * 64, "responseBytes": 12, "secret": "drop"},
            httpStatus=400,
            httpErrorProjection={
                "responseSha256": "b" * 64,
                "responseBytes": 40,
                "bodyKind": "json_object",
                "errorMessage": "Messages with JSON mode must instruct JSON.",
                "errorType": "invalid_request_error",
                "raw": "drop-me",
            },
            reservationCny="0.01",
        ),
        "provider.schema",
    )
    ok = StoredInvocation(
        "inv-2",
        "run-1",
        "vision-000000",
        "logical-2",
        InvocationStatus.COMPLETED,
        _metadata(ok=True),
        None,
    )
    rows = invocation_failure_diagnostics((failed, ok))
    assert len(rows) == 1
    row = rows[0]
    assert row["stageId"] == "vision-000021"
    assert row["errorCode"] == "provider.schema"
    diagnostics = row["diagnostics"]
    assert diagnostics["schemaError"] == "event_frame_boundaries"
    assert "same source frame" in diagnostics["schemaDetail"]
    assert diagnostics["schemaProjection"] == {
        "responseSha256": "a" * 64,
        "responseBytes": 12,
    }
    assert "secret" not in diagnostics["schemaProjection"]
    assert diagnostics["httpStatus"] == 400
    assert diagnostics["httpErrorProjection"]["errorType"] == "invalid_request_error"
    assert "raw" not in diagnostics["httpErrorProjection"]
    assert "reservationCny" not in diagnostics


def test_inspect_run_includes_invocation_failures(tmp_path):
    bundle = bundle_fixture(tmp_path, run_id="run-diag")
    project = tmp_path / "project"

    async def build():
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-diag", bundle.asset, CONFIG)
            await store.begin_stage("run-diag", "media", bundle.asset.sha256)
            await store.persist_media_bundle("run-diag", bundle)
            await store.finish_media_preparation("run-diag")
            await store.begin_stage("run-diag", "vision-000021", bundle.asset.sha256)
            opening = InvocationMetadata(
                "deepseek",
                "deepseek-flash",
                None,
                None,
                "fixture",
                "2",
                1,
                ProviderUsage(),
            )
            await store.begin_invocation(
                "attempt-1", "run-diag", "vision-000021", "logical-1", opening
            )
            details = {
                "httpStatus": 400,
                "httpErrorProjection": {
                    "responseSha256": "c" * 64,
                    "responseBytes": 10,
                    "bodyKind": "json_object",
                    "errorMessage": "invalid json mode request",
                    "errorType": "invalid_request_error",
                },
            }
            await store.finish_invocation(
                "attempt-1",
                InvocationStatus.FAILED,
                replace(opening, execution_details=json.dumps(details, sort_keys=True)),
                "provider.http",
            )
            await store.stop_run("run-diag", RunStatus.FAILED, "analysis.coverage_gap")
        finally:
            await store.close()

    asyncio.run(build())

    async def read():
        payload = await inspect_run(project, "run-diag", "", tmp_path, mode="lexical")
        assert payload["searchEligible"] is False
        assert payload["invocationFailures"]
        failure = payload["invocationFailures"][0]
        assert failure["errorCode"] == "provider.http"
        assert failure["diagnostics"]["httpStatus"] == 400
        assert "invalid json mode" in failure["diagnostics"]["httpErrorProjection"]["errorMessage"]

    asyncio.run(read())


def test_app_js_renders_invocation_failure_diagnostics():
    text = Path("src/gamingcreator/ui/static/app.js").read_text(encoding="utf-8")
    assert "invocationFailures" in text
    assert "失败诊断" in text
    assert "httpErrorProjection" in text
