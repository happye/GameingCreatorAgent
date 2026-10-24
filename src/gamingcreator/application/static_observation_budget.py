"""Independent static-generation budget policy and durable attempt state contracts."""

from __future__ import annotations

import re
from contextlib import AbstractContextManager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from gamingcreator.application.providers import InvocationMetadata
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.static_observations import MAX_STATIC_OBSERVATION_ACTORS, StaticActor

if TYPE_CHECKING:
    from gamingcreator.application.static_observation_generation import (
        StaticGenerationAuthorization,
        StaticGenerationProposal,
    )

ResultStatus = Literal["observed", "no_observations", "failed", "cancelled"]
ChargeStatus = Literal["known", "unknown"]
ConsistencyVerdict = Literal["consistent", "reconstruct_row", "settle_from_file", "fail_closed"]

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DIAGNOSTIC = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z"
)


def _budget_error(code: str, message: str) -> AppError:
    return AppError(code, message, ExitCode.BUDGET)


@dataclass(frozen=True, slots=True)
class StaticAttemptResult:
    """One durable outcome; unknown billing is represented by missing usage, never zero."""

    status: ResultStatus
    actors: tuple[StaticActor, ...]
    metadata: InvocationMetadata
    response_sha256: str | None
    response_bytes: int
    content_bytes: int | None
    http_status: int | None
    diagnostics: tuple[str, ...]
    recorded_at: str

    def __post_init__(self) -> None:
        if self.status not in ("observed", "no_observations", "failed", "cancelled"):
            raise ValueError("Unknown static generation attempt result status.")
        if type(self.actors) is not tuple or len(self.actors) > MAX_STATIC_OBSERVATION_ACTORS:
            raise ValueError("Static generation result actors are not bounded.")
        if any(type(actor) is not StaticActor for actor in self.actors):
            raise ValueError("Static generation result requires typed actors.")
        if self.status == "observed" and not self.actors:
            raise ValueError("An observed result needs at least one typed actor.")
        if self.status in ("no_observations", "failed", "cancelled") and self.actors:
            raise ValueError("Empty or failed results cannot carry actors.")
        if type(self.metadata) is not InvocationMetadata:
            raise ValueError("Static generation result needs invocation metadata.")
        if self.response_sha256 is not None and (
            type(self.response_sha256) is not str or not _HASH.fullmatch(self.response_sha256)
        ):
            raise ValueError("Static generation response digest is invalid.")
        if type(self.response_bytes) is not int or self.response_bytes < 0:
            raise ValueError("Static generation response bytes are invalid.")
        if self.content_bytes is not None and (
            type(self.content_bytes) is not int or self.content_bytes < 0
        ):
            raise ValueError("Static generation content bytes are invalid.")
        if self.http_status is not None and (
            type(self.http_status) is not int or not 100 <= self.http_status <= 599
        ):
            raise ValueError("Static generation HTTP status is invalid.")
        if type(self.diagnostics) is not tuple or any(
            type(item) is not str or not _DIAGNOSTIC.fullmatch(item) for item in self.diagnostics
        ):
            raise ValueError("Static generation diagnostics are not whitelisted codes.")
        if self.status in ("observed", "no_observations"):
            if self.diagnostics:
                raise ValueError("Successful generation results cannot carry failure codes.")
        elif not self.diagnostics:
            raise ValueError("Failed or cancelled generation results need one whitelist code.")
        if type(self.recorded_at) is not str or not _TIMESTAMP.fullmatch(self.recorded_at):
            raise ValueError("Static generation recorded time is invalid.")

    @property
    def cost_cny(self) -> Decimal | None:
        return self.metadata.usage.cost_cny


@dataclass(frozen=True, slots=True)
class StaticAttemptState:
    """Ledger row reconciled with its immutable attempt file."""

    attempt_id: str
    request_key: str
    authorization_id: str
    authorization_sha256: str
    proposal_sha256: str
    run_id: str
    collection_id: str
    reservation_cny: Decimal
    currency: str
    planned_at: str
    revision: int
    input_frames: int
    published: bool
    result: StaticAttemptResult | None
    charge_cny: Decimal | None
    charge_status: ChargeStatus

    def __post_init__(self) -> None:
        for value, label in (
            (self.attempt_id, "attempt"),
            (self.request_key, "request"),
            (self.authorization_id, "authorization"),
            (self.run_id, "run"),
            (self.collection_id, "collection"),
        ):
            if type(value) is not str or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"Invalid static generation {label} identity.")
        for value in (self.authorization_sha256, self.proposal_sha256):
            if type(value) is not str or not _HASH.fullmatch(value):
                raise ValueError("Invalid static generation identity hash.")
        if (
            not isinstance(self.reservation_cny, Decimal)
            or not self.reservation_cny.is_finite()
            or self.reservation_cny <= 0
        ):
            raise ValueError("Static generation reservations must be positive decimals.")
        if self.currency != "CNY":
            raise ValueError("Static generation currency must be CNY.")
        if type(self.planned_at) is not str or not _TIMESTAMP.fullmatch(self.planned_at):
            raise ValueError("Invalid static generation planned time.")
        if self.revision not in (1, 2):
            raise ValueError("Unknown static generation attempt revision.")
        if self.revision == 1 and self.result is not None:
            raise ValueError("A planned attempt cannot already have a result.")
        if self.revision == 2 and self.result is None:
            raise ValueError("A recorded attempt must carry its result.")
        if type(self.input_frames) is not int or self.input_frames != 1:
            raise ValueError("Static generation attempts use exactly one input frame.")
        if self.charge_status not in ("known", "unknown"):
            raise ValueError("Unknown static generation charge status.")
        if (self.charge_cny is None) != (self.charge_status == "unknown"):
            raise ValueError("Charge status and amount must be consistent.")
        if self.charge_cny is not None and (
            not isinstance(self.charge_cny, Decimal)
            or not self.charge_cny.is_finite()
            or self.charge_cny < 0
        ):
            raise ValueError("Known charges must be finite nonnegative decimals.")
        if self.published and (
            self.result is None
            or self.result.status
            not in (
                "observed",
                "no_observations",
            )
        ):
            raise ValueError("Only a successful recorded result can be published.")

    @property
    def settled(self) -> bool:
        return self.result is not None


@dataclass(frozen=True, slots=True)
class StaticBudgetUsage:
    requests: int
    input_frames: int
    known_cost_cny: Decimal
    reserved_cny: Decimal

    @property
    def committed_cny(self) -> Decimal:
        return self.known_cost_cny + self.reserved_cny


def attempt_charge(result: StaticAttemptResult) -> tuple[Decimal | None, ChargeStatus]:
    """A missing or malformed usage stays unknown; known actual cost is never clipped."""
    cost = result.cost_cny
    if cost is None:
        return None, "unknown"
    if not isinstance(cost, Decimal) or not cost.is_finite() or cost < 0:
        return None, "unknown"
    return cost, "known"


def budget_usage(attempts: tuple[StaticAttemptState, ...]) -> StaticBudgetUsage:
    known = Decimal(0)
    reserved = Decimal(0)
    frames = 0
    for attempt in attempts:
        frames += attempt.input_frames
        if attempt.charge_status == "unknown":
            reserved += attempt.reservation_cny
        elif attempt.charge_cny is not None:
            known += attempt.charge_cny
    return StaticBudgetUsage(len(attempts), frames, known, reserved)


def ensure_plan_allowed(
    attempts: tuple[StaticAttemptState, ...],
    *,
    reservation_cny: Decimal,
    currency: str,
    max_cost_cny: Decimal,
    max_requests: int,
    max_input_frames: int,
) -> None:
    """One request per authorization; unknown attempts keep their reservation and counts."""
    if currency != "CNY":
        raise _budget_error("static_generation.currency_conflict", "静态生成授权货币与账本不一致。")
    if max_requests != 1 or max_input_frames != 1:
        raise _budget_error(
            "static_generation.authorization_limit",
            "静态生成授权必须固定 maxRequests=1 与 maxInputFrames=1。",
        )
    usage = budget_usage(attempts)
    if usage.requests + 1 > max_requests:
        raise _budget_error("static_generation.budget_exhausted", "该静态生成授权已使用请求次数。")
    if usage.input_frames + 1 > max_input_frames:
        raise _budget_error("static_generation.budget_exhausted", "该静态生成授权已使用图片张数。")
    if usage.committed_cny + reservation_cny > max_cost_cny:
        raise _budget_error(
            "static_generation.budget_exhausted", "静态生成授权金额不足以覆盖保守预留。"
        )


def consistency_verdict(
    *,
    row_present: bool,
    file_present: bool,
    row_revision: int,
    file_revision: int,
    row_sha256: str,
    file_sha256: str,
) -> ConsistencyVerdict:
    """Define the explicit attempt-file-then-ledger order and its conservative recovery.

    The attempt file is written first. A recorded file with a still-planned row is a crash
    between those writes and is settled from the file; every other disagreement fails closed.
    """
    if not row_present and not file_present:
        return "consistent"
    if row_present and not file_present:
        raise _budget_error(
            "static_generation.ledger_inconsistent",
            "静态生成账本存在尝试但对应attempt文件缺失；失败关闭。",
        )
    if file_present and not row_present:
        return "reconstruct_row"
    if row_revision not in (1, 2) or file_revision not in (1, 2):
        return "fail_closed"
    if row_sha256 == file_sha256:
        return "consistent" if row_revision == file_revision else "fail_closed"
    if row_revision == 1 and file_revision == 2:
        return "settle_from_file"
    return "fail_closed"


class StaticGenerationLedger(Protocol):
    """Fixed project-level ledger; implementations own OS locks and both durable files."""

    root: Path
    database: Path

    def request_guard(self, proposal_sha256: str) -> AbstractContextManager[None]: ...

    def bind_authorization(self, authorization: StaticGenerationAuthorization) -> None: ...

    def load_attempt(self, request_key: str) -> StaticAttemptState | None: ...

    def plan_attempt(
        self,
        proposal: StaticGenerationProposal,
        authorization: StaticGenerationAuthorization,
        *,
        planned_at: str,
    ) -> tuple[StaticAttemptState, bool]: ...

    def record_result(
        self, *, request_key: str, result: StaticAttemptResult
    ) -> StaticAttemptState: ...

    def mark_published(self, request_key: str) -> StaticAttemptState: ...
