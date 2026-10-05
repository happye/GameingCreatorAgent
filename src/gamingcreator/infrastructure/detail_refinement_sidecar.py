"""Project-local refinement sidecar and shared budget ledger. No provider SDK."""

import asyncio
import errno
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

from gamingcreator.application.detail_refinement import (
    DetailRefinementProvider,
    DetailRefinementRequest,
    RefinementIdentity,
    RefinementSettings,
    canonical_request_json,
    event_fingerprint,
    prepare_refinement,
    request_hash,
)
from gamingcreator.application.detail_refinement_budget import (
    RESULT_SCHEMA_VERSION,
    BudgetCharge,
    assert_same_request,
    canonical_detail_json,
    detail_from_canonical,
    detail_matches_request,
    payload_hash,
    reserve_attempt,
)
from gamingcreator.application.detail_refinement_records import (
    ATTEMPT_SCHEMA_VERSION,
    metadata_from_payload,
    metadata_payload,
    validate_metadata,
)
from gamingcreator.application.inspection import inspection_view
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.application.storage import RunStatus, StoredTimeline
from gamingcreator.domain.actor_details import CandidateDetail, MatchStatus
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import SemanticEvent

_RUN_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_BUDGET_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MAX_JSON_BYTES = 1_048_576


def _fail(code: str, message: str, run_id: str | None = None) -> AppError:
    exit_code = ExitCode.BUDGET if code.startswith("budget.") else ExitCode.STORAGE
    return AppError(code, message, exit_code, run_id)


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _confined(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    if _linked(resolved_root):
        raise _fail("refinement.path", "项目目录不能是符号链接。")
    current = path
    if _linked(current):
        raise _fail("refinement.path", "精分析路径拒绝符号链接。")
    while True:
        if _linked(current):
            raise _fail("refinement.path", "精分析路径拒绝符号链接。")
        if current == resolved_root:
            break
        if current.parent == current:
            raise _fail("refinement.path", "精分析路径逃出了项目目录。")
        current = current.parent
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise _fail("refinement.path", "精分析路径逃出了项目目录。")
    return resolved


def _identity(value: object, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        raise _fail(code, "精分析标识无效。")
    return value


def sidecar_directory(project: Path, run_id: str, digest: str) -> Path:
    root = project.resolve()
    run_id = _identity(run_id, _RUN_ID, "refinement.path")
    digest = _identity(digest, _HASH, "refinement.hash_mismatch")
    return _confined(root, root / "runs" / run_id / "detail-refinements" / digest)


def budget_directory(project: Path, budget_id: str) -> Path:
    root = project.resolve()
    budget_id = _identity(budget_id, _BUDGET_ID, "refinement.path")
    return _confined(root, root / "detail-refinement-budgets" / budget_id)


def _atomic(path: Path, payload: bytes) -> None:
    if len(payload) > _MAX_JSON_BYTES:
        raise _fail("refinement.too_large", "精分析记录超过 1MiB。")
    temporary = path.with_name(path.name + ".tmp")
    if any(_linked(item) for item in (path, temporary, *path.parents)):
        raise _fail("refinement.path", "精分析写入拒绝符号链接。")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _read_bytes(path: Path, root: Path) -> bytes:
    confined = _confined(root, path)
    if _linked(confined) or not confined.is_file():
        raise _fail("refinement.damaged", "精分析记录不是项目内的普通文件。")
    with confined.open("rb") as handle:
        data = handle.read(_MAX_JSON_BYTES + 1)
    if len(data) > _MAX_JSON_BYTES:
        raise _fail("refinement.too_large", "精分析记录超过 1MiB。")
    return data


def _loads(path: Path, root: Path) -> dict[str, object]:
    try:
        value = _strict_json(_read_bytes(path, root))
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise _fail("refinement.damaged", "精分析记录无法读取。") from None
    if type(value) is not dict:
        raise _fail("refinement.damaged", "精分析记录格式无效。")
    return value


def _strict_json(data: bytes) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field.")
            result[key] = value
        return result

    def nonfinite(value: str) -> object:
        raise ValueError("Nonfinite JSON number.")

    return json.loads(data, object_pairs_hook=unique, parse_constant=nonfinite)


class BudgetWriterLock:
    """Held only around restore, ceiling check, and reservation."""

    def __init__(self, project: Path) -> None:
        root = project.resolve()
        self._path = _confined(root, root / "detail-refinement-budgets" / ".writer.lock")
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = self._path.open("a+b", buffering=0)
        except OSError:
            raise _fail("storage.writer_lock", "无法打开精分析预算锁。") from None
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise _fail("storage.writer_busy", "精分析预算锁正被占用。") from None
            raise _fail("storage.writer_lock", "无法获取精分析预算锁。") from None
        self._handle = handle

    def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            handle.close()

    def __enter__(self) -> "BudgetWriterLock":
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class RefinementWriterLock(BudgetWriterLock):
    """Hold across sending and publication; retries cannot overlap an active writer."""

    def __init__(self, project: Path, request: DetailRefinementRequest) -> None:
        root = project.resolve()
        self._path = _confined(
            root, root / "detail-refinement-budgets" / f".key-{request_hash(request)}.lock"
        )
        self._handle = None


def _decimal(value: object) -> Decimal:
    if type(value) is not str:
        raise ValueError("Money must be a decimal string.")
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("Money must be finite.")
    return amount


def _positive_int(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("Expected a positive attempt/frame count.")
    return value


def _charges(project: Path) -> tuple[BudgetCharge, ...]:
    root = project.resolve()
    base = root / "detail-refinement-budgets"
    if not base.exists():
        return _planned_charges(project, {})
    if _linked(base):
        raise _fail("refinement.path", "预算目录拒绝符号链接。")
    latest: dict[tuple[str, str, int], BudgetCharge] = {}
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if child.name.startswith("."):
            continue
        if _linked(child) or not child.is_dir() or not _BUDGET_ID.fullmatch(child.name):
            raise _fail("refinement.path", "预算目录拒绝符号链接或异常名称。")
        ledger = child / "ledger.jsonl"
        if not ledger.exists():
            continue
        for line in _read_bytes(ledger, root).splitlines():
            if not line.strip():
                continue
            try:
                item = _strict_json(line)
            except (ValueError, UnicodeError, RecursionError):
                raise _fail("refinement.damaged", "预算账本无法读取。") from None
            if type(item) is not dict:
                raise _fail("refinement.damaged", "预算账本格式无效。")
            cost = None if item["costCny"] is None else _decimal(item["costCny"])
            charge = BudgetCharge(
                child.name,
                item["attempt"],
                item["requestHash"],
                item["runId"],
                _decimal(item["reservationCny"]),
                item["frames"],
                cost,
                item.get("revision") if type(item.get("revision")) is str else None,
            )
            latest[(charge.budget_id, charge.request_hash, charge.attempt)] = charge
    return _planned_charges(project, latest)


def _planned_charges(
    project: Path,
    latest: dict[tuple[str, str, int], BudgetCharge],
) -> tuple[BudgetCharge, ...]:
    """A crash between planned.json and ledger append must still retain its reservation."""
    root = project.resolve()
    runs = root / "runs"
    _confined(root, runs)
    if not runs.exists():
        return tuple(latest.values())
    for run in runs.iterdir():
        if _linked(run):
            raise _fail("refinement.path", "运行目录拒绝符号链接。")
        details = run / "detail-refinements"
        _confined(root, details)
        if not details.exists():
            continue
        for directory in details.iterdir():
            _confined(root, directory)
            if not directory.is_dir() or not _HASH.fullmatch(directory.name):
                raise _fail("refinement.damaged", "精分析目录标识无效。")
            for number, planned, _result in _attempt_paths(directory):
                row = _loads(planned, root)
                if row.get("requestHash") != directory.name or row.get("attempt") != number:
                    raise _fail("refinement.damaged", "尝试记录身份无效。")
                existing = [key for key in latest if key[1:] == (directory.name, number)]
                if row.get("schemaVersion") != ATTEMPT_SCHEMA_VERSION:
                    if not existing:
                        raise _fail("budget.interrupted", "旧尝试缺少预算归属，预留待核对。")
                    continue
                budget_id = _identity(row.get("budgetId"), _BUDGET_ID, "refinement.path")
                if row.get("runId") != run.name:
                    raise _fail("refinement.damaged", "尝试运行身份无效。")
                charge = BudgetCharge(
                    budget_id,
                    number,
                    directory.name,
                    run.name,
                    _decimal(row.get("reservationCny")),
                    _positive_int(row.get("frames")),
                    None,
                    None,
                )
                key = (budget_id, directory.name, number)
                if existing and existing != [key]:
                    raise _fail("refinement.damaged", "尝试预算归属不一致。")
                if key in latest:
                    before = latest[key]
                    if (before.run_id, before.reservation_cny, before.frames) != (
                        charge.run_id,
                        charge.reservation_cny,
                        charge.frames,
                    ):
                        raise _fail("refinement.damaged", "尝试预留与账本不一致。")
                else:
                    latest[key] = charge
    return tuple(latest.values())


def _append_charge(project: Path, budget_id: str, charge: BudgetCharge) -> None:
    directory = budget_directory(project, budget_id)
    directory.mkdir(parents=True, exist_ok=True)
    ledger = directory / "ledger.jsonl"
    if ledger.exists() and (_linked(ledger) or not ledger.is_file()):
        raise _fail("refinement.damaged", "预算账本不是普通文件。")
    line = (
        json.dumps(
            {
                "attempt": charge.attempt,
                "requestHash": charge.request_hash,
                "runId": charge.run_id,
                "reservationCny": format(charge.reservation_cny, "f"),
                "frames": charge.frames,
                "costCny": None if charge.cost_cny is None else format(charge.cost_cny, "f"),
                "revision": charge.revision,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    with ledger.open("ab") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _attempt_paths(directory: Path) -> list[tuple[int, Path, Path | None]]:
    attempts = directory / "attempts"
    if _linked(attempts):
        raise _fail("refinement.path", "精分析尝试目录拒绝符号链接。")
    if not attempts.exists():
        return []
    found: dict[int, Path] = {}
    for path in attempts.iterdir():
        if _linked(path):
            raise _fail("refinement.path", "精分析尝试拒绝符号链接。")
        match = re.fullmatch(r"([1-9][0-9]*)-planned.json", path.name)
        if match is None:
            continue
        found[int(match.group(1))] = path
    rows = []
    for number, planned in sorted(found.items()):
        result = attempts / f"{number}-result.json"
        rows.append((number, planned, result if result.exists() else None))
    return rows


def _open_attempt(project: Path, run_id: str, digest: str) -> int | None:
    directory = sidecar_directory(project, run_id, digest)
    if not directory.exists():
        return None
    for number, _planned, result in _attempt_paths(directory):
        if result is None:
            return number
    return None


def _next_attempt(project: Path, run_id: str, digest: str) -> int:
    directory = sidecar_directory(project, run_id, digest)
    if not directory.exists():
        return 1
    numbers = [number for number, _planned, _result in _attempt_paths(directory)]
    return (max(numbers) if numbers else 0) + 1


def freeze_request(project: Path, request: DetailRefinementRequest) -> str:
    """Write the immutable request once. Does not call a provider."""
    digest = request_hash(request)
    assert_same_request(request, digest)
    directory = sidecar_directory(project, request.run_id, digest)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "request.json"
    document = {
        "schemaVersion": 1,
        "requestHash": digest,
        "runId": request.run_id,
        "eventFingerprint": request.event_fingerprint,
        "canonicalJson": canonical_request_json(request),
        "basePromptVersion": request.base_prompt_version,
        "basePromptHash": request.base_prompt_hash,
    }
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if target.exists():
        existing = _read_bytes(target, project.resolve())
        if existing != payload:
            raise _fail("refinement.immutable", "已冻结的精分析请求不能改写。", request.run_id)
        return digest
    _atomic(target, payload)
    return digest


def _published(project: Path, request: DetailRefinementRequest) -> CandidateDetail | None:
    directory = sidecar_directory(project, request.run_id, request_hash(request))
    target = directory / "result.json"
    _confined(project.resolve(), target)
    if not target.exists():
        return None
    document = _loads(target, project.resolve())
    actual_model = document.get("actualModel")
    if (
        document.get("schemaVersion") != RESULT_SCHEMA_VERSION
        or document.get("requestHash") != request_hash(request)
        or type(document.get("payloadJson")) is not str
        or (actual_model is not None and type(actual_model) is not str)
    ):
        raise _fail("refinement.damaged", "已发布的精分析结果无效。", request.run_id)
    payload_json = document["payloadJson"]
    assert type(payload_json) is str
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if document.get("payloadHash") != digest:
        raise _fail("refinement.hash_mismatch", "已发布结果的载荷哈希不匹配。", request.run_id)
    try:
        detail = detail_from_canonical(payload_json)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _fail(
            "refinement.damaged", "已发布结果不是有效的主体结构。", request.run_id
        ) from None
    if canonical_detail_json(detail) != payload_json:
        raise _fail("refinement.damaged", "已发布结果不是冻结的规范格式。", request.run_id)
    if not detail_matches_request(detail, request):
        raise _fail("refinement.source_mismatch", "已发布结果与当前候选不一致。", request.run_id)
    if document.get("modelRevision") is not None and type(document.get("modelRevision")) is not str:
        raise _fail("refinement.damaged", "模型版本标识无效。", request.run_id)
    return detail


@dataclass(frozen=True, slots=True)
class RefinementOutcome:
    status: MatchStatus
    request: DetailRefinementRequest | None
    request_hash: str | None
    detail: CandidateDetail | None
    reused: bool

    def __post_init__(self) -> None:
        if self.detail is not None and self.status == MatchStatus.FULL:
            raise ValueError("Sidecar reuse is a typed detail, not a query full match.")
        if self.reused and self.detail is None:
            raise ValueError("A reused refinement needs its typed detail.")
        if self.request is not None and self.request_hash != request_hash(self.request):
            raise ValueError("Outcome hash drifted from the frozen request.")


def _event(timeline: StoredTimeline, event_id: str) -> SemanticEvent:
    event = next((item for item in timeline.events if item.event_id == event_id), None)
    if event is None:
        raise _fail("refinement.missing_event", "时间轴里没有这个候选。", timeline.run.run_id)
    return event


def reuse_or_refuse(
    project: Path,
    timeline: StoredTimeline,
    event_id: str,
    *,
    settings: RefinementSettings | None = None,
    identity: RefinementIdentity | None = None,
) -> RefinementOutcome:
    """Read a sidecar or return unverified. This never calls a provider."""
    prepared = prepare_refinement(timeline, event_id, settings=settings, identity=identity)
    event = _event(timeline, event_id)
    if prepared.request is None or prepared.request_hash is None:
        return RefinementOutcome(MatchStatus.UNVERIFIED, None, None, None, False)
    if prepared.request.event_fingerprint != event_fingerprint(event):
        raise _fail("refinement.source_mismatch", "候选指纹与原事件不一致。", event.run_id)
    directory = sidecar_directory(project, prepared.request.run_id, prepared.request_hash)
    if not directory.exists():
        return RefinementOutcome(
            MatchStatus.UNVERIFIED, prepared.request, prepared.request_hash, None, False
        )
    stored = _loads(directory / "request.json", project.resolve())
    canonical = stored.get("canonicalJson")
    if (
        type(stored.get("schemaVersion")) is not int
        or stored.get("schemaVersion") != 1
        or stored.get("basePromptVersion") != prepared.request.base_prompt_version
        or stored.get("basePromptHash") != prepared.request.base_prompt_hash
        or stored.get("runId") != prepared.request.run_id
        or stored.get("requestHash") != prepared.request_hash
        or stored.get("eventFingerprint") != prepared.request.event_fingerprint
        or type(canonical) is not str
        or hashlib.sha256(canonical.encode("utf-8")).hexdigest() != prepared.request_hash
        or canonical != canonical_request_json(prepared.request)
    ):
        raise _fail("refinement.source_mismatch", "侧车请求与当前候选不一致。", event.run_id)
    detail = _published(project, prepared.request)
    if detail is None:
        return RefinementOutcome(
            MatchStatus.UNVERIFIED, prepared.request, prepared.request_hash, None, False
        )
    return RefinementOutcome(
        MatchStatus.UNVERIFIED, prepared.request, prepared.request_hash, detail, True
    )


def begin_attempt(
    project: Path,
    request: DetailRefinementRequest,
    *,
    budget_id: str,
    ceiling: Decimal,
    reservation: Decimal,
    retry: bool,
) -> int:
    """Reserve and persist a planned attempt. The lock is released before any send."""
    digest = request_hash(request)
    with BudgetWriterLock(project):
        # Re-check after acquire. A caller that looked earlier can lose the race.
        open_attempt = _open_attempt(project, request.run_id, digest)
        if open_attempt is not None and not retry:
            raise _fail(
                "budget.interrupted",
                "已有未完成的精分析尝试，未再次发送。",
                request.run_id,
            )
        directory = sidecar_directory(project, request.run_id, digest)
        if not retry and _attempt_paths(directory):
            raise _fail(
                "refinement.retry_required", "已有精分析尝试，重试需要显式开启。", request.run_id
            )
        if _published(project, request) is not None:
            raise _fail("refinement.immutable", "已有精分析结果，无需再次发送。", request.run_id)
        charges = _charges(project)
        reserve_attempt(ceiling, charges, len(request.evidence), reservation)
        number = _next_attempt(project, request.run_id, digest)
        freeze_request(project, request)
        directory = sidecar_directory(project, request.run_id, digest)
        planned = directory / "attempts" / f"{number}-planned.json"
        if planned.exists():
            raise _fail("refinement.immutable", "精分析尝试编号已存在。", request.run_id)
        _atomic(
            planned,
            json.dumps(
                {
                    "schemaVersion": ATTEMPT_SCHEMA_VERSION,
                    "attempt": number,
                    "requestHash": digest,
                    "runId": request.run_id,
                    "budgetId": budget_id,
                    "frames": len(request.evidence),
                    "promptHash": request.identity.prompt_hash,
                    "reservationCny": format(reservation, "f"),
                    "status": "planned",
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8"),
        )
        _append_charge(
            project,
            budget_id,
            BudgetCharge(
                budget_id,
                number,
                digest,
                request.run_id,
                reservation,
                len(request.evidence),
                None,
                None,
            ),
        )
    return number


def finish_attempt(
    project: Path,
    request: DetailRefinementRequest,
    attempt: int,
    *,
    budget_id: str,
    reservation: Decimal,
    result: ProviderResult[CandidateDetail],
) -> None:
    """Persist metadata and typed output before publishing, so publication is recoverable."""
    validate_metadata(result.metadata, request)
    if result.status not in (
        ProviderStatus.COMPLETED,
        ProviderStatus.FAILED,
        ProviderStatus.CANCELLED,
    ):
        raise ValueError("Unsupported refinement status.")
    detail = result.output
    if detail is not None and not detail_matches_request(detail, request):
        result = ProviderResult(
            ProviderStatus.FAILED, None, result.metadata, ProviderFailure("provider.schema", False)
        )
        detail = None
    digest = request_hash(request)
    directory = sidecar_directory(project, request.run_id, digest)
    target = directory / "attempts" / f"{attempt}-result.json"
    if target.exists():
        raise _fail("refinement.immutable", "精分析尝试结果不能覆盖。", request.run_id)
    body: dict[str, object] = {
        "schemaVersion": ATTEMPT_SCHEMA_VERSION,
        "attempt": attempt,
        "requestHash": digest,
        "promptHash": request.identity.prompt_hash,
        "metadata": metadata_payload(result.metadata),
        "status": result.status.value,
        "error": None
        if result.error is None
        else {"code": result.error.code, "retryable": result.error.retryable},
        "payloadJson": None if detail is None else canonical_detail_json(detail),
        "payloadHash": None if detail is None else payload_hash(detail),
    }
    with BudgetWriterLock(project):
        planned = _loads(directory / "attempts" / f"{attempt}-planned.json", project.resolve())
        _validate_planned(planned, request, attempt)
        if (planned.get("budgetId"), planned.get("reservationCny")) != (
            budget_id,
            format(reservation, "f"),
        ):
            raise _fail("refinement.source_mismatch", "完成记录与预算预留不一致。", request.run_id)
        if target.exists():
            raise _fail("refinement.immutable", "精分析尝试结果不能覆盖。", request.run_id)
        _atomic(target, json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        _settle_record(project, request, planned, result.metadata)
        if detail is not None:
            _publish(project, request, detail, result.metadata)


def _validate_planned(
    planned: dict[str, object], request: DetailRefinementRequest, attempt: int
) -> None:
    expected = {
        "schemaVersion": ATTEMPT_SCHEMA_VERSION,
        "attempt": attempt,
        "requestHash": request_hash(request),
        "runId": request.run_id,
        "frames": len(request.evidence),
        "promptHash": request.identity.prompt_hash,
        "status": "planned",
    }
    if set(planned) != set(expected) | {"budgetId", "reservationCny"} or any(
        planned[key] != value or type(planned[key]) is not type(value)
        for key, value in expected.items()
    ):
        raise _fail("refinement.damaged", "精分析预留身份无效。", request.run_id)
    _identity(planned["budgetId"], _BUDGET_ID, "refinement.path")
    if _decimal(planned["reservationCny"]) <= 0:
        raise _fail("refinement.damaged", "精分析预留必须为正数。", request.run_id)


def _settle_record(
    project: Path,
    request: DetailRefinementRequest,
    planned: dict[str, object],
    metadata: InvocationMetadata,
) -> None:
    charge = BudgetCharge(
        _identity(planned["budgetId"], _BUDGET_ID, "refinement.path"),
        _positive_int(planned["attempt"]),
        request_hash(request),
        request.run_id,
        _decimal(planned["reservationCny"]),
        len(request.evidence),
        metadata.usage.cost_cny,
        metadata.model_revision,
    )
    if charge not in _charges(project):
        _append_charge(project, charge.budget_id, charge)


def _publish(
    project: Path,
    request: DetailRefinementRequest,
    detail: CandidateDetail,
    metadata: InvocationMetadata,
) -> None:
    document = {
        "schemaVersion": RESULT_SCHEMA_VERSION,
        "requestHash": request_hash(request),
        "payloadHash": payload_hash(detail),
        "payloadJson": canonical_detail_json(detail),
        "actualModel": metadata.actual_model,
        "modelRevision": metadata.model_revision,
        "costCny": None
        if metadata.usage.cost_cny is None
        else format(metadata.usage.cost_cny, "f"),
        "metadata": metadata_payload(metadata),
    }
    result_path = sidecar_directory(project, request.run_id, request_hash(request)) / "result.json"
    _confined(project.resolve(), result_path)
    if result_path.exists():
        raise _fail("refinement.immutable", "已发布的精分析结果不能覆盖。", request.run_id)
    _atomic(result_path, json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _recover_refinement(project: Path, request: DetailRefinementRequest) -> CandidateDetail | None:
    """Caller holds the key lock. Repair completed records locally; never resend HTTP."""
    with BudgetWriterLock(project):
        published = _published(project, request)
        successful: list[tuple[CandidateDetail, InvocationMetadata]] = []
        directory = sidecar_directory(project, request.run_id, request_hash(request))
        for number, planned_path, result_path in _attempt_paths(directory):
            if result_path is None:
                continue
            row = _loads(result_path, project.resolve())
            if row.get("schemaVersion") is None:
                if (
                    set(row) == {"attempt", "requestHash", "costCny", "revision", "status"}
                    and row.get("attempt") == number
                    and row.get("requestHash") == request_hash(request)
                    and row.get("status") in ("completed", "failed")
                ):
                    continue  # Legacy attempts have no recoverable typed payload.
                raise _fail("refinement.damaged", "精分析尝试缺少有效版本。", request.run_id)
            try:
                if (
                    set(row)
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
                    or type(row.get("attempt")) is not int
                ):
                    raise ValueError("Invalid attempt fields.")
                if (
                    row.get("schemaVersion"),
                    row.get("attempt"),
                    row.get("requestHash"),
                    row.get("promptHash"),
                ) != (
                    ATTEMPT_SCHEMA_VERSION,
                    number,
                    request_hash(request),
                    request.identity.prompt_hash,
                ):
                    raise ValueError("Attempt identity drift.")
                metadata = metadata_from_payload(row["metadata"])
                validate_metadata(metadata, request)
                raw_status = row["status"]
                if type(raw_status) is not str:
                    raise ValueError("Invalid attempt status.")
                status = ProviderStatus(raw_status)
                payload = row["payloadJson"]
                detail = None
                if status == ProviderStatus.COMPLETED:
                    if type(payload) is not str:
                        raise ValueError("Missing completed payload.")
                    detail = detail_from_canonical(payload)
                    if (
                        canonical_detail_json(detail) != payload
                        or payload_hash(detail) != row["payloadHash"]
                        or not detail_matches_request(detail, request)
                        or row["error"] is not None
                    ):
                        raise ValueError("Invalid recovered output.")
                elif (
                    status not in (ProviderStatus.FAILED, ProviderStatus.CANCELLED)
                    or payload is not None
                    or row["payloadHash"] is not None
                    or type(row["error"]) is not dict
                ):
                    raise ValueError("Invalid failed attempt.")
                planned = _loads(planned_path, project.resolve())
                _validate_planned(planned, request, number)
                _settle_record(project, request, planned, metadata)
                if detail is not None:
                    successful.append((detail, metadata))
            except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
                raise _fail(
                    "refinement.damaged", "精分析尝试无法安全恢复。", request.run_id
                ) from None
        if published is not None:
            return published
        if successful:
            detail, metadata = successful[0]
            _publish(project, request, detail, metadata)
            return detail
        return None


async def send_refinement(
    project: Path,
    timeline: StoredTimeline,
    event_id: str,
    provider: DetailRefinementProvider,
    *,
    budget_id: str,
    ceiling: Decimal,
    reservation: Decimal,
    retry: bool = False,
    settings: RefinementSettings | None = None,
    identity: RefinementIdentity | None = None,
    context: CancellationContext | None = None,
) -> RefinementOutcome:
    """Reuse a published key with no call; otherwise plan, release the lock, then send."""
    if timeline.run.status != RunStatus.COMPLETED:
        raise _fail(
            "refinement.run_incomplete", "精分析仅接受已完成的源运行。", timeline.run.run_id
        )
    existing = reuse_or_refuse(project, timeline, event_id, settings=settings, identity=identity)
    if existing.request is None:
        return existing
    request = existing.request
    with RefinementWriterLock(project, request):
        recovered = _recover_refinement(project, request)
        if recovered is not None:
            return RefinementOutcome(
                MatchStatus.UNVERIFIED, request, request_hash(request), recovered, True
            )
        if context is None:
            context = CancellationContext(request.run_id, request.settings.timeout_seconds)
        if context.run_id != request.run_id:
            raise ValueError("Wrong refinement cancellation context.")
        context.check_cancelled()
        number = begin_attempt(
            project,
            request,
            budget_id=budget_id,
            ceiling=ceiling,
            reservation=reservation,
            retry=retry,
        )
        cancelled = False
        try:
            result = await provider.refine(request, context)
        except (asyncio.CancelledError, Exception) as error:
            cancelled = isinstance(error, asyncio.CancelledError)
            result = ProviderResult(
                ProviderStatus.CANCELLED if cancelled else ProviderStatus.FAILED,
                None,
                InvocationMetadata(
                    request.identity.provider,
                    request.identity.requested_model,
                    None,
                    None,
                    request.identity.prompt_version,
                    request.identity.schema_version,
                    1,
                    ProviderUsage(),
                ),
                ProviderFailure("provider.cancelled" if cancelled else "provider.transport", False),
            )
        finish_attempt(
            project, request, number, budget_id=budget_id, reservation=reservation, result=result
        )
        task = asyncio.current_task()
        if result.status == ProviderStatus.CANCELLED and task is not None and task.cancelling():
            cancelled = True
        if cancelled:
            raise asyncio.CancelledError
        detail = _published(project, request)
        return RefinementOutcome(
            MatchStatus.UNVERIFIED, request, request_hash(request), detail, False
        )


def unchanged_source_event(timeline: StoredTimeline, event_id: str) -> SemanticEvent:
    """Basket and inspection still read the original event after sidecar writes."""
    event = _event(timeline, event_id)
    view = inspection_view(timeline, (), "refinement-sidecar")
    row = next(item for item in view.timeline if item.event_id == event_id)
    if row.facts != event.observable_facts or (row.start_us, row.end_us) != (
        event.source_range.start_us,
        event.source_range.end_us,
    ):
        raise _fail("refinement.source_mismatch", "原事件被精分析改写。", event.run_id)
    return event
