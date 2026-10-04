"""Conservative per-attempt reservations and durable invocation callbacks."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from gamingcreator.application.providers import InvocationMetadata
from gamingcreator.application.storage import InvocationStatus
from gamingcreator.domain.errors import AppError, ExitCode


class InvocationRecorder(Protocol):
    async def begin_invocation(
        self,
        invocation_id: str,
        run_id: str,
        stage_id: str,
        logical_request_id: str,
        metadata: InvocationMetadata,
    ) -> None: ...

    async def finish_invocation(
        self,
        invocation_id: str,
        status: InvocationStatus,
        metadata: InvocationMetadata,
        error_code: str | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    reservation_id: str
    frames: int
    reservation_cny: Decimal


def _amount(value: Decimal, *, positive: bool) -> None:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or (positive and value == 0)
    ):
        raise ValueError("Budget amounts must be finite Decimal values in the allowed range.")


class BudgetLedger:
    """One run, owned by one application event loop; reservations contain no I/O."""

    def __init__(self, max_cost_cny: Decimal, max_requests: int, max_frames: int) -> None:
        _amount(max_cost_cny, positive=True)
        if any(type(v) is not int or v <= 0 for v in (max_requests, max_frames)):
            raise ValueError("Budget limits must be positive integers.")
        self.max_cost_cny = max_cost_cny
        self.max_requests = max_requests
        self.max_frames = max_frames
        self.requests = 0
        self.frames = 0
        self.known_cost_cny = Decimal(0)
        self._reservations: dict[str, BudgetReservation] = {}
        self._settled: set[str] = set()

    @property
    def reserved_cny(self) -> Decimal:
        return sum((r.reservation_cny for r in self._reservations.values()), Decimal(0))

    @property
    def committed_cny(self) -> Decimal:
        return self.known_cost_cny + self.reserved_cny

    @property
    def unresolved_attempts(self) -> int:
        return len(self._reservations)

    def reserve(self, frames: int, reservation_cny: Decimal | None) -> BudgetReservation:
        if type(frames) is not int or frames < 0:
            raise ValueError("Frame usage must be a nonnegative integer.")
        if reservation_cny is None:
            raise AppError(
                "budget.estimate_missing", "缺少请求费用上界，已停止发送。", ExitCode.BUDGET
            )
        try:
            _amount(reservation_cny, positive=True)
        except ValueError:
            raise AppError(
                "budget.estimate_invalid", "请求费用上界无效。", ExitCode.BUDGET
            ) from None
        if (
            self.requests + 1 > self.max_requests
            or self.frames + frames > self.max_frames
            or self.committed_cny + reservation_cny > self.max_cost_cny
        ):
            raise AppError("budget.exhausted", "已达到请求、图片或费用上限。", ExitCode.BUDGET)
        reservation = BudgetReservation(uuid4().hex, frames, reservation_cny)
        self._reservations[reservation.reservation_id] = reservation
        self.requests += 1
        self.frames += frames
        return reservation

    def settle(self, reservation: BudgetReservation, cost_cny: Decimal | None) -> None:
        if (
            reservation.reservation_id in self._settled
            or self._reservations.get(reservation.reservation_id) != reservation
        ):
            raise ValueError("Unknown or already settled reservation.")
        if cost_cny is not None:
            _amount(cost_cny, positive=False)
            self.known_cost_cny += cost_cny
            del self._reservations[reservation.reservation_id]
        # Unknown billing keeps its original reservation even after failure or cancellation.
        self._settled.add(reservation.reservation_id)
