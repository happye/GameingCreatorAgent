"""Read-only refinement attempts and project-local commitment, never invoices."""

import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from gamingcreator.application.detail_refinement import (
    RefinementIdentity,
    RefinementSettings,
)
from gamingcreator.application.detail_refinement_budget import (
    BudgetCharge,
    canonical_detail_json,
    detail_from_canonical,
)
from gamingcreator.application.detail_refinement_records import (
    ATTEMPT_SCHEMA_VERSION,
    metadata_from_payload,
)
from gamingcreator.application.providers import InvocationMetadata
from gamingcreator.domain.actor_details import DetailEvidence
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar

HISTORY_SCHEMA_VERSION = "detail-refinement-cost-history-v1"
_MAX_ATTEMPTS = 10_000
_MAX_DISPLAY_ATTEMPTS = 200
_LEDGER_FIELDS = {
    "attempt",
    "requestHash",
    "runId",
    "reservationCny",
    "frames",
    "costCny",
    "revision",
}


def _money(value: object, *, positive: bool = False) -> Decimal:
    if type(value) is not str or len(value) > 64:
        raise ValueError("Money must be a bounded decimal string.")
    amount = sidecar._decimal(value)
    exponent = amount.as_tuple().exponent
    if (
        amount < 0
        or (positive and amount == 0)
        or amount > Decimal("1000000000")
        or type(exponent) is not int
        or exponent < -18
    ):
        raise ValueError("Money is outside the bounded report range.")
    return amount


def _validate_ledgers(root: Path) -> None:
    """Accept append-only settlement and identical repeats, reject conflicting charges."""
    base = sidecar._confined(root, root / "detail-refinement-budgets")
    if not base.exists():
        return
    seen: dict[tuple[str, int], tuple[str, dict[str, object]]] = {}
    lines = 0
    for directory in sorted(base.iterdir()):
        if directory.name.startswith("."):
            continue
        sidecar._confined(root, directory)
        sidecar._identity(directory.name, sidecar._BUDGET_ID, "refinement.path")
        if not directory.is_dir():
            raise ValueError("Budget entry is not a directory.")
        ledger = sidecar._confined(root, directory / "ledger.jsonl")
        if not ledger.exists():
            continue
        for line in sidecar._read_bytes(ledger, root).splitlines():
            if not line.strip():
                continue
            lines += 1
            if lines > _MAX_ATTEMPTS * 3:
                raise sidecar._fail("refinement.too_large", "精分析费用历史记录过多。")
            value = sidecar._strict_json(line)
            if type(value) is not dict or set(value) != _LEDGER_FIELDS:
                raise ValueError("Invalid budget fields.")
            digest = sidecar._identity(value["requestHash"], sidecar._HASH, "refinement.damaged")
            number = sidecar._positive_int(value["attempt"])
            sidecar._identity(value["runId"], sidecar._RUN_ID, "refinement.damaged")
            if not 1 <= sidecar._positive_int(value["frames"]) <= 9:
                raise ValueError("Invalid frame count.")
            _money(value["reservationCny"], positive=True)
            if value["costCny"] is not None:
                _money(value["costCny"])
            revision = value["revision"]
            if revision is not None and (
                type(revision) is not str or not 1 <= len(revision) <= 256
            ):
                raise ValueError("Invalid model revision.")
            key = digest, number
            if key in seen:
                budget, previous = seen[key]
                unchanged = _LEDGER_FIELDS - {"costCny", "revision"}
                if budget != directory.name or any(
                    previous[name] != value[name] for name in unchanged
                ):
                    raise ValueError("Duplicate attempt has conflicting budget identity.")
                if previous["costCny"] is not None and previous != value:
                    raise ValueError("Settled cost cannot change or become unknown.")
                if previous["revision"] is not None and previous["revision"] != revision:
                    raise ValueError("Model revision cannot change.")
            seen[key] = directory.name, value


def _request(
    root: Path, charge: BudgetCharge
) -> tuple[dict[str, object], dict[str, object], RefinementIdentity]:
    directory = sidecar.sidecar_directory(root, charge.run_id, charge.request_hash)
    stored = sidecar._loads(directory / "request.json", root)
    canonical = stored.get("canonicalJson")
    if (
        set(stored)
        != {
            "schemaVersion",
            "requestHash",
            "runId",
            "eventFingerprint",
            "canonicalJson",
            "basePromptVersion",
            "basePromptHash",
        }
        or type(stored.get("schemaVersion")) is not int
        or stored["schemaVersion"] != 1
        or type(canonical) is not str
        or hashlib.sha256(canonical.encode("utf-8")).hexdigest() != charge.request_hash
        or stored["requestHash"] != charge.request_hash
        or stored["runId"] != charge.run_id
    ):
        raise ValueError("Invalid frozen request.")
    value = sidecar._strict_json(canonical.encode("utf-8"))
    if type(value) is not dict:
        raise ValueError("Invalid canonical request.")
    interval = value["interval"]
    settings = value["settings"]
    evidence = value["evidence"]
    if type(interval) is not dict or type(settings) is not dict or type(evidence) is not list:
        raise ValueError("Invalid request structures.")
    base_version = stored["basePromptVersion"]
    base_hash = stored["basePromptHash"]
    if type(base_version) is not str or (base_hash is not None and type(base_hash) is not str):
        raise ValueError("Invalid base prompt identity.")
    SourceRange(interval["startUs"], interval["endUs"], interval["durationUs"])
    for item in evidence:
        DetailEvidence(
            item["evidenceId"],
            item["sha256"],
            SourceInstant(item["sourceUs"], item["durationUs"]),
        )
    RefinementSettings(
        settings["maxImages"],
        settings["maxImageWidth"],
        settings["maxImageBytes"],
        settings["imageDetail"],
        settings["timeoutSeconds"],
        settings["maxOutputTokens"],
        settings["version"],
    )
    identity = RefinementIdentity(
        value["promptVersion"],
        value["promptHash"],
        value["schemaVersion"],
        value["provider"],
        value["requestedModel"],
    )
    if (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != canonical
        or value["baseRunId"] != charge.run_id
        or value["eventFingerprint"] != stored["eventFingerprint"]
        or len(evidence) != charge.frames
    ):
        raise ValueError("Frozen request identity drift.")
    return stored, value, identity


def _validate_metadata(value: InvocationMetadata, identity: RefinementIdentity) -> None:
    if (
        value.provider != identity.provider
        or value.requested_model != identity.requested_model
        or value.prompt_version != identity.prompt_version
        or value.schema_version != identity.schema_version
        or type(value.attempt) is not int
        or value.attempt not in (0, 1)
        or (
            value.elapsed_ms is not None
            and (type(value.elapsed_ms) is not int or value.elapsed_ms < 0)
        )
    ):
        raise ValueError("Invocation identity does not match the frozen request.")
    for name in (
        "provider",
        "requested_model",
        "actual_model",
        "model_revision",
        "prompt_version",
        "schema_version",
        "price_version",
        "request_id",
        "execution_details",
    ):
        text = getattr(value, name)
        maximum = 16_384 if name == "execution_details" else 256
        if text is not None and (type(text) is not str or not 1 <= len(text) <= maximum):
            raise ValueError("Invalid bounded invocation metadata.")


def _metadata(value: InvocationMetadata) -> dict[str, object]:
    usage = value.usage
    requested_at = period = period_basis = None
    if value.execution_details is not None:
        try:
            details = sidecar._strict_json(value.execution_details.encode("utf-8"))
            if type(details) is dict:
                raw_time = details.get("requestedAtUtc")
                if type(raw_time) is str and len(raw_time) <= 64:
                    parsed = datetime.fromisoformat(raw_time)
                    if parsed.utcoffset() == timedelta(0):
                        requested_at = parsed.isoformat()
                if details.get("period") in ("peak", "offpeak"):
                    period = details["period"]
                if details.get("periodBasis") in (
                    "china_weekend",
                    "weekday_peak_or_holiday_unknown_conservative",
                    "outside_china_peak_hours",
                ):
                    period_basis = details["periodBasis"]
        except (ValueError, UnicodeError, RecursionError):
            pass  # Older execution_details may be free text; do not expose it.
    return {
        "provider": value.provider,
        "requestedModel": value.requested_model,
        "actualModel": value.actual_model,
        "modelRevision": value.model_revision,
        "promptVersion": value.prompt_version,
        "schemaVersion": value.schema_version,
        "providerAttempt": value.attempt,
        "elapsedMs": value.elapsed_ms,
        "priceVersion": value.price_version,
        "requestId": value.request_id,
        "requestedAtUtc": requested_at,
        "period": period,
        "periodBasis": period_basis,
        "usage": {
            "inputTokens": usage.input_tokens,
            "outputTokens": usage.output_tokens,
            "cachedInputTokens": usage.cached_input_tokens,
            "originalCost": None
            if usage.original_cost is None
            else format(usage.original_cost, "f"),
            "currency": usage.currency,
            "costCny": None if usage.cost_cny is None else format(usage.cost_cny, "f"),
            "costStatus": usage.cost_status.value,
        },
    }


def _attempt(root: Path, charge: BudgetCharge) -> dict[str, object]:
    directory = sidecar.sidecar_directory(root, charge.run_id, charge.request_hash)
    planned_path = directory / "attempts" / f"{charge.attempt}-planned.json"
    result_path = directory / "attempts" / f"{charge.attempt}-result.json"
    sidecar._confined(root, planned_path)
    sidecar._confined(root, result_path)
    row: dict[str, object] = {
        "requestHash": charge.request_hash,
        "attemptNo": charge.attempt,
        "budgetId": charge.budget_id,
        "status": "recorded",
        "errorCode": None,
        "reservationCny": format(charge.reservation_cny, "f"),
        "estimatedCostCny": None if charge.cost_cny is None else format(charge.cost_cny, "f"),
        "settlementPending": False,
        "legacy": True,
        "metadata": None,
    }
    if not planned_path.exists():
        if result_path.exists():
            raise ValueError("Orphan result has no planned attempt.")
        return row  # Legacy ledger-only data has cost evidence but no invented metadata.
    stored, frozen, identity = _request(root, charge)
    planned = sidecar._loads(planned_path, root)
    if planned.get("schemaVersion") == ATTEMPT_SCHEMA_VERSION:
        expected: dict[str, object] = {
            "schemaVersion": ATTEMPT_SCHEMA_VERSION,
            "attempt": charge.attempt,
            "requestHash": charge.request_hash,
            "runId": charge.run_id,
            "budgetId": charge.budget_id,
            "frames": charge.frames,
            "promptHash": identity.prompt_hash,
            "reservationCny": planned["reservationCny"],
            "status": "planned",
        }
        if set(planned) != set(expected) or any(
            type(planned[key]) is not type(value) or planned[key] != value
            for key, value in expected.items()
        ):
            raise ValueError("Planned identity drift.")
        row["legacy"] = False
    elif (
        set(planned) != {"attempt", "requestHash", "reservationCny", "status"}
        or type(planned["attempt"]) is not int
        or planned["attempt"] != charge.attempt
        or planned["requestHash"] != charge.request_hash
        or planned["status"] != "planned"
    ):
        raise ValueError("Invalid legacy planned record.")
    if _money(planned["reservationCny"], positive=True) != charge.reservation_cny:
        raise ValueError("Reservation identity drift.")
    row["status"] = "planned"
    if not result_path.exists():
        if charge.cost_cny is not None:
            raise ValueError("Settled attempt is missing its result.")
        return row
    result = sidecar._loads(result_path, root)
    if result.get("schemaVersion") is None:
        recorded_cost = None if result.get("costCny") is None else _money(result["costCny"])
        if (
            not row["legacy"]
            or set(result) != {"attempt", "requestHash", "costCny", "revision", "status"}
            or type(result["attempt"]) is not int
            or result["attempt"] != charge.attempt
            or result["requestHash"] != charge.request_hash
            or result["status"] not in ("completed", "failed")
            or (charge.revision is not None and result["revision"] != charge.revision)
            or (charge.cost_cny is not None and recorded_cost != charge.cost_cny)
            or (
                result["revision"] is not None
                and (type(result["revision"]) is not str or not 1 <= len(result["revision"]) <= 256)
            )
        ):
            raise ValueError("Invalid legacy result.")
        row["status"] = result["status"]
        row["settlementPending"] = charge.cost_cny is None and recorded_cost is not None
        return row
    if (
        set(result)
        != {
            "schemaVersion",
            "attempt",
            "requestHash",
            "promptHash",
            "metadata",
            "status",
            "error",
            "payloadJson",
            "payloadHash",
        }
        or result["schemaVersion"] != ATTEMPT_SCHEMA_VERSION
        or type(result["attempt"]) is not int
        or result["attempt"] != charge.attempt
        or result["requestHash"] != charge.request_hash
        or result["promptHash"] != identity.prompt_hash
        or result["status"] not in ("completed", "failed", "cancelled")
        or row["legacy"]
    ):
        raise ValueError("Invalid result identity.")
    raw_metadata = result["metadata"]
    if type(raw_metadata) is not dict or type(raw_metadata.get("usage")) is not dict:
        raise ValueError("Missing result metadata.")
    for name in ("original_cost", "cost_cny"):
        amount = raw_metadata["usage"].get(name)
        if amount is not None:
            _money(amount)
    metadata = metadata_from_payload(raw_metadata)
    _validate_metadata(metadata, identity)
    for amount in (metadata.usage.original_cost, metadata.usage.cost_cny):
        if amount is not None:
            _money(format(amount, "f"))
    if metadata.usage.currency is not None and (
        type(metadata.usage.currency) is not str or len(metadata.usage.currency) > 16
    ):
        raise ValueError("Invalid currency.")
    if charge.cost_cny is not None and (
        metadata.usage.cost_cny != charge.cost_cny or metadata.model_revision != charge.revision
    ):
        raise ValueError("Result usage conflicts with settled ledger.")
    if result["status"] == "completed":
        payload = result["payloadJson"]
        if type(payload) is not str or result["error"] is not None:
            raise ValueError("Completed result has no typed payload.")
        detail = detail_from_canonical(payload)
        payload_value = sidecar._strict_json(payload.encode("utf-8"))
        if (
            canonical_detail_json(detail) != payload
            or hashlib.sha256(payload.encode("utf-8")).hexdigest() != result["payloadHash"]
            or type(payload_value) is not dict
            or any(
                payload_value[key] != frozen[request_key]
                for key, request_key in (
                    ("runId", "baseRunId"),
                    ("mediaSha256", "mediaSha256"),
                    ("configurationHash", "configurationHash"),
                    ("pipelineVersion", "pipelineVersion"),
                    ("eventFingerprint", "eventFingerprint"),
                    ("candidateId", "candidateId"),
                    ("sourceRange", "interval"),
                    ("evidence", "evidence"),
                )
            )
            or detail.base_prompt_version != stored["basePromptVersion"]
            or detail.base_prompt_hash != stored["basePromptHash"]
            or detail.detail_identity_hash != identity.prompt_hash
        ):
            raise ValueError("Invalid completed payload.")
    else:
        error = result["error"]
        if (
            result["payloadJson"] is not None
            or result["payloadHash"] is not None
            or type(error) is not dict
            or set(error) != {"code", "retryable"}
            or type(error["code"]) is not str
            or not 1 <= len(error["code"]) <= 128
            or re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", error["code"]) is None
            or type(error["retryable"]) is not bool
        ):
            raise ValueError("Invalid failure record.")
        row["errorCode"] = error["code"]
    row["status"] = result["status"]
    row["metadata"] = _metadata(metadata)
    row["settlementPending"] = charge.cost_cny is None and metadata.usage.cost_cny is not None
    return row


def _summary(charges: tuple[BudgetCharge, ...]) -> dict[str, object]:
    known = sum((item.cost_cny for item in charges if item.cost_cny is not None), Decimal(0))
    unknown = tuple(item for item in charges if item.cost_cny is None)
    reserved = sum((item.reservation_cny for item in unknown), Decimal(0))
    return {
        "knownEstimatedCostCny": format(known, "f"),
        "unknownCostCount": len(unknown),
        "unknownReservedCny": format(reserved, "f"),
        "commitmentCny": format(known + reserved, "f"),
        "attemptCount": len(charges),
    }


def _validate_attempt_files(root: Path) -> None:
    runs = sidecar._confined(root, root / "runs")
    if not runs.exists():
        return
    count = 0
    for run in runs.iterdir():
        details = sidecar._confined(root, run / "detail-refinements")
        if not details.exists():
            continue
        sidecar._identity(run.name, sidecar._RUN_ID, "refinement.path")
        for directory in details.iterdir():
            attempts = sidecar._confined(root, directory / "attempts")
            if not attempts.exists():
                continue
            for path in attempts.iterdir():
                sidecar._confined(root, path)
                count += 1
                if count > _MAX_ATTEMPTS * 3:
                    raise sidecar._fail("refinement.too_large", "精分析尝试记录过多。")
                if re.fullmatch(r"[1-9][0-9]*-planned.json", path.name):
                    planned = sidecar._loads(path, root)
                    _money(planned.get("reservationCny"), positive=True)
                match = re.fullmatch(r"([1-9][0-9]*)-result.json", path.name)
                if match is not None and not (attempts / f"{match[1]}-planned.json").is_file():
                    raise ValueError("Orphan result has no planned attempt.")


def refinement_cost_history(project: Path, run_id: str) -> dict[str, object]:
    """Inspect all commitment without locks, publication, settlement, or provider calls."""
    root = project.resolve()
    sidecar._identity(run_id, sidecar._RUN_ID, "refinement.path")
    try:
        if any(sidecar._linked(path) for path in (project, *project.parents)):
            raise sidecar._fail("refinement.path", "费用历史拒绝链接项目路径。", run_id)
        _validate_ledgers(root)
        _validate_attempt_files(root)
        charges = sidecar._charges(root)
        if len(charges) > _MAX_ATTEMPTS:
            raise sidecar._fail("refinement.too_large", "精分析费用历史记录过多。", run_id)
        current = tuple(
            sorted(
                (item for item in charges if item.run_id == run_id),
                key=lambda item: (item.request_hash, item.attempt),
            )
        )
        attempts = []
        for charge in sorted(charges, key=lambda item: (item.request_hash, item.attempt)):
            sidecar._identity(charge.run_id, sidecar._RUN_ID, "refinement.damaged")
            sidecar._identity(charge.budget_id, sidecar._BUDGET_ID, "refinement.damaged")
            sidecar._identity(charge.request_hash, sidecar._HASH, "refinement.damaged")
            _money(format(charge.reservation_cny, "f"), positive=True)
            if charge.cost_cny is not None:
                _money(format(charge.cost_cny, "f"))
            if not 1 <= sidecar._positive_int(charge.frames) <= 9:
                raise ValueError("Invalid charged frame count.")
            attempt = _attempt(root, charge)
            if charge.run_id == run_id:
                attempts.append(attempt)
        shared = _summary(charges)
        shared.update(
            {
                "scope": "project-detail-refinements",
                "runCount": len({item.run_id for item in charges}),
                "budgetCount": len({item.budget_id for item in charges}),
            }
        )
        document: dict[str, object] = {
            "schemaVersion": HISTORY_SCHEMA_VERSION,
            "runId": run_id,
            "currency": "CNY",
            "summary": _summary(current),
            "sharedCommitment": shared,
            "attempts": attempts[-_MAX_DISPLAY_ATTEMPTS:],
            "totalAttemptCount": len(attempts),
            "attemptsTruncated": len(attempts) > _MAX_DISPLAY_ATTEMPTS,
        }
        if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > sidecar._MAX_JSON_BYTES:
            raise sidecar._fail("refinement.too_large", "精分析费用历史响应超过 1MiB。", run_id)
        return document
    except (
        KeyError,
        TypeError,
        ValueError,
        ArithmeticError,
        AttributeError,
        OSError,
        RecursionError,
    ):
        raise sidecar._fail(
            "refinement.damaged", "精分析费用历史损坏，未改写任何记录。", run_id
        ) from None
