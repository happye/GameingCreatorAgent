"""Bounded human declarations; these are not provider invoices or send permission."""

import re
from datetime import datetime, timedelta
from decimal import Decimal

MATERIAL_SCHEMA_VERSION = "detail-billing-zero-confirmation-material-v1"
CONFIRMATION_SCHEMA_VERSION = "detail-billing-zero-confirmation-v1"
_FIELDS = {
    "schemaVersion",
    "projectPath",
    "runId",
    "budgetId",
    "requestHash",
    "attemptNo",
    "requestSha256",
    "plannedSha256",
    "resultSha256",
    "confirmedCostCny",
    "statement",
    "source",
    "confirmedAtUtc",
}


def validate_confirmation_material(value: object) -> dict[str, object]:
    """Require explicit identity, original statement, provenance, UTC and zero CNY."""
    if type(value) is not dict or set(value) != _FIELDS:
        raise ValueError("Invalid confirmation material fields.")
    if value["schemaVersion"] != MATERIAL_SCHEMA_VERSION:
        raise ValueError("Unsupported confirmation material version.")
    for name, pattern in (
        ("runId", r"[A-Za-z0-9_-]{1,128}"),
        ("budgetId", r"[A-Za-z0-9_-]{1,64}"),
        *(
            (name, r"[0-9a-f]{64}")
            for name in ("requestHash", "requestSha256", "plannedSha256", "resultSha256")
        ),
    ):
        if type(value[name]) is not str or re.fullmatch(pattern, value[name]) is None:
            raise ValueError("Invalid confirmation identity.")
    if type(value["attemptNo"]) is not int or not 1 <= value["attemptNo"] <= 10_000:
        raise ValueError("Invalid confirmation attempt.")
    for name, maximum in (("projectPath", 4096), ("statement", 16_384), ("source", 4096)):
        if (
            type(value[name]) is not str
            or not value[name].strip()
            or len(value[name]) > maximum
            or "\x00" in value[name]
        ):
            raise ValueError("Invalid confirmation text.")
    amount = value["confirmedCostCny"]
    if type(amount) is not str or re.fullmatch(r"0(?:\.0{1,18})?", amount) is None:
        raise ValueError("Only explicit finite zero CNY confirmations are supported.")
    timestamp = value["confirmedAtUtc"]
    if type(timestamp) is not str or len(timestamp) > 64:
        raise ValueError("Invalid confirmation timestamp.")
    if datetime.fromisoformat(timestamp).utcoffset() != timedelta(0):
        raise ValueError("Confirmation time must specify UTC.")
    return dict(value)


def reconciled_summary(
    original_commitment: Decimal, reservations: tuple[Decimal, ...], ceiling_cny: Decimal | None
) -> dict[str, object]:
    """A display projection only; a released reservation never authorizes requests."""
    released = sum(reservations, Decimal(0))
    commitment = original_commitment - released
    result: dict[str, object] = {
        "confirmedNoChargeCount": len(reservations),
        "releasedReservationCny": format(released, "f"),
        "reconciledCommitmentCny": format(commitment, "f"),
    }
    if ceiling_cny is not None:
        if type(ceiling_cny) is not Decimal:
            raise ValueError("An explicit Decimal CNY ceiling is required.")
        exponent = ceiling_cny.as_tuple().exponent
        if (
            not ceiling_cny.is_finite()
            or ceiling_cny < 0
            or ceiling_cny > Decimal("1000000000")
            or type(exponent) is not int
            or exponent < -18
        ):
            raise ValueError("An explicit bounded CNY ceiling is required.")
        result["ceilingCny"] = format(ceiling_cny, "f")
        result["remainingCny"] = format(ceiling_cny - commitment, "f")
    return result
