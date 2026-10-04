from dataclasses import replace
from decimal import Decimal

import pytest

from gamingcreator.application.budget import BudgetLedger
from gamingcreator.domain.errors import AppError, ExitCode


@pytest.mark.parametrize(
    "amount", [Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity"), 1]
)
def test_budget_requires_positive_finite_decimal(amount: object) -> None:
    with pytest.raises(ValueError):
        BudgetLedger(amount, 2, 10)  # type: ignore[arg-type]


@pytest.mark.parametrize("requests,frames", [(True, 10), (1, False), (0, 10), (1, -1), (1.5, 10)])
def test_budget_limits_reject_boolean_and_nonpositive_integer(
    requests: object, frames: object
) -> None:
    with pytest.raises(ValueError):
        BudgetLedger(Decimal(1), requests, frames)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "amount", [None, Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")]
)
def test_unknown_or_invalid_estimate_stops_before_consuming_budget(amount: Decimal | None) -> None:
    ledger = BudgetLedger(Decimal(1), 2, 10)
    with pytest.raises(AppError) as captured:
        ledger.reserve(5, amount)
    assert captured.value.exit_code == ExitCode.BUDGET
    assert ledger.requests == ledger.frames == 0
    assert ledger.committed_cny == 0


@pytest.mark.parametrize("frames", [True, -1, 0.5])
def test_frame_usage_is_not_coerced(frames: object) -> None:
    with pytest.raises(ValueError):
        BudgetLedger(Decimal(1), 2, 10).reserve(frames, Decimal("0.1"))  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", ["requests", "frames", "cost"])
def test_each_hard_limit_stops_atomically(limit: str) -> None:
    ledger = BudgetLedger(
        Decimal("0.2") if limit == "cost" else Decimal(1),
        1 if limit == "requests" else 3,
        5 if limit == "frames" else 15,
    )
    ledger.reserve(5, Decimal("0.2"))
    with pytest.raises(AppError, match="已达到"):
        ledger.reserve(5, Decimal("0.2"))
    assert ledger.requests == 1
    assert ledger.frames == 5
    assert ledger.reserved_cny == Decimal("0.2")


def test_unknown_cost_keeps_reservation_and_cannot_be_settled_twice() -> None:
    ledger = BudgetLedger(Decimal("0.4"), 3, 15)
    reservation = ledger.reserve(5, Decimal("0.3"))
    ledger.settle(reservation, None)
    assert ledger.known_cost_cny == 0
    assert ledger.committed_cny == ledger.reserved_cny == Decimal("0.3")
    assert ledger.unresolved_attempts == 1
    with pytest.raises(AppError):
        ledger.reserve(5, Decimal("0.2"))
    with pytest.raises(ValueError):
        ledger.settle(reservation, Decimal(0))


def test_known_charge_replaces_reservation_and_zero_requires_explicit_evidence() -> None:
    ledger = BudgetLedger(Decimal(1), 3, 15)
    first = ledger.reserve(5, Decimal("0.8"))
    ledger.settle(first, Decimal("0.2"))
    second = ledger.reserve(5, Decimal("0.8"))
    ledger.settle(second, Decimal(0))
    assert ledger.known_cost_cny == ledger.committed_cny == Decimal("0.2")
    assert ledger.reserved_cny == 0
    assert ledger.unresolved_attempts == 0
    assert ledger.requests == 2 and ledger.frames == 10


def test_underestimated_charge_is_recorded_in_full_and_stops_next_attempt() -> None:
    ledger = BudgetLedger(Decimal(1), 3, 15)
    reservation = ledger.reserve(5, Decimal("0.5"))
    ledger.settle(reservation, Decimal("1.2"))
    assert ledger.known_cost_cny == ledger.committed_cny == Decimal("1.2")
    with pytest.raises(AppError):
        ledger.reserve(5, Decimal("0.01"))


def test_forged_reservation_and_invalid_charge_cannot_mutate_budget() -> None:
    ledger = BudgetLedger(Decimal(1), 3, 15)
    reservation = ledger.reserve(5, Decimal("0.5"))
    with pytest.raises(ValueError):
        ledger.settle(replace(reservation, reservation_cny=Decimal("0.1")), Decimal(0))
    with pytest.raises(ValueError):
        ledger.settle(reservation, Decimal("NaN"))
    assert ledger.reserved_cny == Decimal("0.5")
    ledger.settle(reservation, Decimal("0.3"))
