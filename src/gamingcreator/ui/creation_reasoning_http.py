"""Exact, text-only HTTP contract for the separately confirmed reasoning service."""

import asyncio
import os
from decimal import Decimal, InvalidOperation
from typing import Any

from gamingcreator.infrastructure.creation_reasoning_provider import MODEL
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService


def reasoning_config() -> dict[str, Any]:
    return {
        "available": bool(os.environ.get("DEEPSEEK_API_KEY", "").strip()),
        "provider": "deepseek",
        "requestedModel": MODEL,
    }


def reasoning_post(service: CreationReasoningService, value: Any) -> dict[str, Any]:
    fields = {
        "prepare_plan": {"action", "jobId"},
        "adopt_plan": {"action", "preparedHash"},
        "prepare": {"action", "jobId", "planId", "instruction"},
        "execute": {"action", "preparedHash", "snapshotFingerprint", "confirmedMaxCny"},
        "validate": {"action", "preparedHash", "jobId", "planId", "expectedParentReceiptSha256"},
        "result": {"action", "preparedHash"},
    }
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("action"), str)
        or value["action"] not in fields
        or set(value) != fields[value["action"]]
        or any(not isinstance(item, str) or not item for item in value.values())
    ):
        raise ValueError("Invalid reasoning request fields.")
    action = value["action"]
    if action == "prepare_plan":
        return service.prepare_plan(value["jobId"])
    if action == "adopt_plan":
        return service.adopt_plan(value["preparedHash"])
    if action == "prepare":
        return service.prepare(value["jobId"], value["planId"], value["instruction"])
    if action == "result":
        return service.read_result(value["preparedHash"])
    if action == "validate":
        return service.proposal_for_editor(
            value["preparedHash"],
            value["jobId"],
            value["planId"],
            value["expectedParentReceiptSha256"],
        )
    try:
        amount = Decimal(value["confirmedMaxCny"])
    except InvalidOperation as error:
        raise ValueError("Invalid confirmation amount.") from error
    if not amount.is_finite():
        raise ValueError("Confirmation amount must be finite.")
    return asyncio.run(service.execute(value["preparedHash"], value["snapshotFingerprint"], amount))
