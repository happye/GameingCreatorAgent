"""Read-only, bounded projections of failed vision invocations for offline diagnosis."""

from __future__ import annotations

import json
from typing import Any

from gamingcreator.application.storage import InvocationStatus, StoredInvocation

MAX_FAILURE_ROWS = 64
_DIAGNOSTIC_KEYS = (
    "schemaError",
    "schemaDetail",
    "schemaProjection",
    "httpStatus",
    "httpErrorProjection",
)


def _safe_details(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _clip_diagnostics(details: dict[str, Any]) -> dict[str, Any]:
    clipped: dict[str, Any] = {}
    for key in _DIAGNOSTIC_KEYS:
        if key not in details:
            continue
        value = details[key]
        if key == "schemaDetail" and isinstance(value, str):
            clipped[key] = value[:500]
        elif key == "httpErrorProjection" and isinstance(value, dict):
            projection = {
                name: value[name]
                for name in (
                    "responseSha256",
                    "responseBytes",
                    "bodyKind",
                    "errorMessage",
                    "errorType",
                )
                if name in value
            }
            if isinstance(projection.get("errorMessage"), str):
                projection["errorMessage"] = projection["errorMessage"][:500]
            clipped[key] = projection
        elif key == "schemaProjection" and isinstance(value, dict):
            clipped[key] = {
                name: value[name] for name in ("responseSha256", "responseBytes") if name in value
            }
        elif key in {"schemaError", "httpStatus"}:
            clipped[key] = value
    return clipped


def invocation_failure_diagnostics(
    invocations: tuple[StoredInvocation, ...],
    *,
    limit: int = MAX_FAILURE_ROWS,
) -> list[dict[str, object]]:
    """Summarize failed invocations with offline-safe diagnostic projections only."""
    if type(limit) is not int or not 1 <= limit <= MAX_FAILURE_ROWS:
        limit = MAX_FAILURE_ROWS
    rows: list[dict[str, object]] = []
    for item in invocations:
        if item.status != InvocationStatus.FAILED or not item.error_code:
            continue
        details = _safe_details(item.metadata.execution_details)
        rows.append(
            {
                "invocationId": item.invocation_id,
                "stageId": item.stage_id,
                "logicalRequestId": item.logical_request_id,
                "errorCode": item.error_code,
                "attempt": item.metadata.attempt,
                "diagnostics": _clip_diagnostics(details),
            }
        )
        if len(rows) >= limit:
            break
    return rows
