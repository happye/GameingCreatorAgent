"""Project-local refinement sidecar and shared budget ledger. No provider SDK."""

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
from gamingcreator.application.inspection import inspection_view
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import StoredTimeline
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
    if current.exists() and _linked(current):
        raise _fail("refinement.path", "精分析路径拒绝符号链接。")
    while True:
        if current.exists() and _linked(current):
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


def _identity(value: str, pattern: re.Pattern[str], code: str) -> str:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _read_bytes(path: Path, root: Path) -> bytes:
    confined = _confined(root, path)
    if _linked(confined) or not confined.is_file():
        raise _fail("refinement.damaged", "精分析记录不是项目内的普通文件。")
    data = confined.read_bytes()
    if len(data) > _MAX_JSON_BYTES:
        raise _fail("refinement.too_large", "精分析记录超过 1MiB。")
    return data


def _loads(path: Path, root: Path) -> dict[str, object]:
    try:
        value = json.loads(_read_bytes(path, root))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise _fail("refinement.damaged", "精分析记录无法读取。") from None
    if type(value) is not dict:
        raise _fail("refinement.damaged", "精分析记录格式无效。")
    return value


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


def _decimal(value: object) -> Decimal:
    if type(value) is not str:
        raise ValueError("Money must be a decimal string.")
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("Money must be finite.")
    return amount


def _charges(project: Path) -> tuple[BudgetCharge, ...]:
    root = project.resolve()
    base = root / "detail-refinement-budgets"
    if not base.exists():
        return ()
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
            item = json.loads(line)
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
    if not attempts.exists():
        return []
    if _linked(attempts):
        raise _fail("refinement.path", "精分析尝试目录拒绝符号链接。")
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
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise _fail(
            "refinement.damaged", "已发布结果不是有效的主体结构。", request.run_id
        ) from None
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


def reuse_or_refuse(project: Path, timeline: StoredTimeline, event_id: str) -> RefinementOutcome:
    """Read a sidecar or return unverified. This never calls a provider."""
    prepared = prepare_refinement(timeline, event_id)
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
        stored.get("runId") != prepared.request.run_id
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
                    "attempt": number,
                    "requestHash": digest,
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
    cost_cny: Decimal | None,
    revision: str | None,
    detail: CandidateDetail | None,
) -> None:
    """Append the attempt result. Unknown cost is stored as null, never zero."""
    if cost_cny is not None and (not isinstance(cost_cny, Decimal) or cost_cny < 0):
        raise _fail("budget.estimate_invalid", "精分析费用无效。", request.run_id)
    digest = request_hash(request)
    directory = sidecar_directory(project, request.run_id, digest)
    target = directory / "attempts" / f"{attempt}-result.json"
    if target.exists():
        raise _fail("refinement.immutable", "精分析尝试结果不能覆盖。", request.run_id)
    body: dict[str, object] = {
        "attempt": attempt,
        "requestHash": digest,
        "costCny": None if cost_cny is None else format(cost_cny, "f"),
        "revision": revision,
        "status": "completed" if detail is not None else "failed",
    }
    _atomic(target, json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    _append_charge(
        project,
        budget_id,
        BudgetCharge(
            budget_id,
            attempt,
            digest,
            request.run_id,
            reservation,
            len(request.evidence),
            cost_cny,
            revision,
        ),
    )
    if detail is None:
        return
    if not detail_matches_request(detail, request):
        raise _fail("refinement.source_mismatch", "模型输出与冻结候选不一致。", request.run_id)
    payload = canonical_detail_json(detail)
    document = {
        "schemaVersion": RESULT_SCHEMA_VERSION,
        "requestHash": digest,
        "payloadHash": payload_hash(detail),
        "payloadJson": payload,
        "actualModel": None,
        "modelRevision": revision,
        "costCny": None if cost_cny is None else format(cost_cny, "f"),
    }
    result_path = directory / "result.json"
    if result_path.exists():
        raise _fail("refinement.immutable", "已发布的精分析结果不能覆盖。", request.run_id)
    _atomic(result_path, json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8"))


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
) -> RefinementOutcome:
    """Reuse a published key with no call; otherwise plan, release the lock, then send."""
    existing = reuse_or_refuse(project, timeline, event_id)
    if existing.reused or existing.request is None:
        return existing
    request = existing.request
    number = begin_attempt(
        project,
        request,
        budget_id=budget_id,
        ceiling=ceiling,
        reservation=reservation,
        retry=retry,
    )
    result = await provider.refine(request, CancellationContext(request.run_id, 90))
    detail = result.output
    cost = result.metadata.usage.cost_cny
    revision = result.metadata.model_revision
    finish_attempt(
        project,
        request,
        number,
        budget_id=budget_id,
        reservation=reservation,
        cost_cny=cost,
        revision=revision,
        detail=detail,
    )
    if detail is None:
        return RefinementOutcome(
            MatchStatus.UNVERIFIED, request, request_hash(request), None, False
        )
    return RefinementOutcome(MatchStatus.UNVERIFIED, request, request_hash(request), detail, False)


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
