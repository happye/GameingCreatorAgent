"""Append immutable zero-charge declarations without changing original cost evidence."""

import hashlib
import json
from pathlib import Path

from gamingcreator.application.detail_billing_confirmation import (
    CONFIRMATION_SCHEMA_VERSION,
    validate_confirmation_material,
)
from gamingcreator.application.detail_refinement_budget import BudgetCharge
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar


def _root(project: Path) -> Path:
    absolute = project.absolute()
    if any(sidecar._linked(path) for path in (absolute, *absolute.parents)):
        raise sidecar._fail("refinement.path", "人工费用核对拒绝链接项目路径。")
    return project.resolve()


def _record_path(root: Path, material: dict[str, object]) -> Path:
    budget = str(material["budgetId"])
    name = f"{material['runId']}--{material['requestHash']}--{material['attemptNo']}.json"
    return sidecar._confined(
        root, sidecar.budget_directory(root, budget) / "billing-confirmations" / name
    )


def _target(
    root: Path, material: dict[str, object], charges: tuple[BudgetCharge, ...]
) -> BudgetCharge:
    from gamingcreator.infrastructure import detail_cost_history as history

    if material["projectPath"] != str(root):
        raise ValueError("Confirmation belongs to another project.")
    matched = [
        item
        for item in charges
        if (item.run_id, item.budget_id, item.request_hash, item.attempt)
        == (material["runId"], material["budgetId"], material["requestHash"], material["attemptNo"])
    ]
    if len(matched) != 1:
        raise ValueError("Confirmation has no unique charged attempt.")
    charge = matched[0]
    # Planned-only recovery charges must not be treated as a durable ledger receipt.
    ledger = sidecar.budget_directory(root, charge.budget_id) / "ledger.jsonl"
    found = False
    for line in sidecar._read_bytes(ledger, root).splitlines():
        if line.strip():
            row = sidecar._strict_json(line)
            if type(row) is dict and (row["runId"], row["requestHash"], row["attempt"]) == (
                charge.run_id,
                charge.request_hash,
                charge.attempt,
            ):
                found = True
    if not found:
        raise ValueError("Confirmation is missing original ledger evidence.")
    row = history._attempt(root, charge)
    metadata = row["metadata"]
    if (
        charge.cost_cny is not None
        or row["status"] not in ("completed", "failed", "cancelled")
        or row["legacy"]
        or row["settlementPending"]
        or type(metadata) is not dict
    ):
        raise ValueError("Only ended attempts with unknown provider cost may be confirmed.")
    usage = metadata["usage"]
    if (
        type(usage) is not dict
        or usage["costCny"] is not None
        or usage["originalCost"] is not None
        or usage["costStatus"] != "unverified"
    ):
        raise ValueError("Provider usage already has cost evidence.")
    directory = sidecar.sidecar_directory(root, charge.run_id, charge.request_hash)
    for field, path in (
        ("requestSha256", directory / "request.json"),
        ("plannedSha256", directory / "attempts" / f"{charge.attempt}-planned.json"),
        ("resultSha256", directory / "attempts" / f"{charge.attempt}-result.json"),
    ):
        if hashlib.sha256(sidecar._read_bytes(path, root)).hexdigest() != material[field]:
            raise ValueError("Confirmation original evidence has drifted.")
    return charge


def read_billing_confirmations(
    project: Path, charges: tuple[BudgetCharge, ...]
) -> dict[tuple[str, str, str, int], dict[str, object]]:
    """Validate published records only, without locks, writes or provider calls."""
    root = _root(project)
    base = sidecar._confined(root, root / "detail-refinement-budgets")
    records: dict[tuple[str, str, str, int], dict[str, object]] = {}
    if not base.exists():
        return records
    for budget in base.iterdir():
        sidecar._confined(root, budget)
        if budget.name.startswith("."):
            continue
        directory = sidecar._confined(root, budget / "billing-confirmations")
        if not directory.exists():
            continue
        for path in directory.iterdir():
            sidecar._confined(root, path)
            if path.name.endswith(".json.tmp"):
                continue  # Unpublished interrupted writes never release a reservation.
            record = sidecar._loads(path, root)
            if (
                set(record) != {"schemaVersion", "materialJson", "materialSha256", "reservationCny"}
                or record["schemaVersion"] != CONFIRMATION_SCHEMA_VERSION
                or type(record["materialJson"]) is not str
            ):
                raise ValueError("Invalid billing confirmation record.")
            data = record["materialJson"].encode("utf-8")
            if hashlib.sha256(data).hexdigest() != record["materialSha256"]:
                raise ValueError("Billing confirmation material hash mismatch.")
            material = validate_confirmation_material(sidecar._strict_json(data))
            if path != _record_path(root, material):
                raise ValueError("Billing confirmation path identity mismatch.")
            charge = _target(root, material, charges)
            if record["reservationCny"] != format(charge.reservation_cny, "f"):
                raise ValueError("Billing confirmation reservation drift.")
            key = charge.run_id, charge.budget_id, charge.request_hash, charge.attempt
            if key in records or len(records) >= 10_000:
                raise ValueError("Duplicate or excessive billing confirmations.")
            records[key] = record
    return records


def import_billing_confirmation(
    project: Path,
    *,
    run_id: str,
    budget_id: str,
    request_hash: str,
    attempt_no: int,
    material_path: Path,
) -> dict[str, object]:
    """Import explicit human evidence under the existing budget lock, never settle API usage."""
    from gamingcreator.infrastructure import detail_cost_history as history

    root = _root(project)
    try:
        absolute_material = material_path.absolute()
        if any(sidecar._linked(path) for path in (absolute_material, *absolute_material.parents)):
            raise sidecar._fail("refinement.path", "人工确认材料拒绝链接路径。")
        data = sidecar._read_bytes(material_path.resolve(), material_path.resolve().parent)
        material = validate_confirmation_material(sidecar._strict_json(data))
        if material["projectPath"] != str(root):
            raise ValueError("Confirmation belongs to another project.")
        if type(attempt_no) is not int or (run_id, budget_id, request_hash, attempt_no) != (
            material["runId"],
            material["budgetId"],
            material["requestHash"],
            material["attemptNo"],
        ):
            raise ValueError("Explicit import identity differs from confirmation material.")
        with sidecar.BudgetWriterLock(root):
            # Re-read all source and existing confirmation evidence inside the shared lock.
            history.refinement_cost_history(root, run_id)
            charges = sidecar._charges(root)
            charge = _target(root, material, charges)
            records = read_billing_confirmations(root, charges)
            record: dict[str, object] = {
                "schemaVersion": CONFIRMATION_SCHEMA_VERSION,
                "materialJson": data.decode("utf-8"),
                "materialSha256": hashlib.sha256(data).hexdigest(),
                "reservationCny": format(charge.reservation_cny, "f"),
            }
            key = run_id, budget_id, request_hash, attempt_no
            if key in records:
                if records[key] != record:
                    raise ValueError("Conflicting immutable billing confirmation.")
                return records[key]
            path = _record_path(root, material)
            if path.exists():
                raise ValueError("Confirmation publication would replace an existing record.")
            sidecar._atomic(
                path, json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
            )
            return record
    except (
        KeyError,
        TypeError,
        ValueError,
        ArithmeticError,
        OSError,
        UnicodeError,
        RecursionError,
    ):
        raise sidecar._fail(
            "billing.confirmation_invalid", "人工费用确认无效，原API费用与发送预算保持。", run_id
        ) from None
