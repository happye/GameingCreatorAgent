"""Exact, text-only HTTP contract for the reasoning service (per-call or monthly-budget sends)."""

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
    if isinstance(value, dict) and value.get("action") == "prepare_brief":
        games = value.get("games")
        if (
            set(value)
            not in (
                {"action", "text", "games"},
                {"action", "text", "games", "projectId", "workId"},
            )
            or not isinstance(value["text"], str)
            or not isinstance(games, list)
            or len(games) > 50
            or any(not isinstance(g, str) or len(g) > 200 for g in games)
        ):
            raise ValueError("Invalid reasoning request fields.")
        if "projectId" in value:
            if any(
                not isinstance(value[key], str) or not value[key].strip()
                for key in ("projectId", "workId")
            ):
                raise ValueError("Invalid work identity fields.")
            return service.prepare_brief(value["text"], games, value["projectId"], value["workId"])
        return service.prepare_brief(value["text"], games)
    fields = {
        "prepare_plan": {"action", "jobId"},
        "prepare_copy": {"action", "jobId"},
        "prepare_narration": {"action", "jobId", "planId"},
        "adopt_plan": {"action", "preparedHash"},
        "prepare": {"action", "jobId", "planId", "instruction"},
        "execute": {"action", "preparedHash", "snapshotFingerprint", "confirmedMaxCny"},
        "execute_budget": {"action", "preparedHash", "snapshotFingerprint"},
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
    if action in ("prepare_plan", "prepare_copy"):
        prepare = {"prepare_plan": service.prepare_plan, "prepare_copy": service.prepare_copy}
        return prepare[action](value["jobId"])
    if action == "prepare_narration":
        return service.prepare_narration(value["jobId"], value["planId"])
    if action == "adopt_plan":
        return service.adopt_plan(value["preparedHash"])
    if action == "prepare":
        return service.prepare(value["jobId"], value["planId"], value["instruction"])
    if action == "execute_budget":
        return asyncio.run(
            service.execute_within_budget(value["preparedHash"], value["snapshotFingerprint"])
        )
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
