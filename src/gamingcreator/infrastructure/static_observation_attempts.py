"""Fixed project-level static-generation ledger, attempt files, and non-blocking OS locks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO, Literal, cast

from gamingcreator.application.providers import (
    CostStatus,
    InvocationMetadata,
    ProviderUsage,
)
from gamingcreator.application.static_observation_budget import (
    StaticAttemptResult,
    StaticAttemptState,
    attempt_charge,
    consistency_verdict,
    ensure_plan_allowed,
)
from gamingcreator.application.static_observation_generation import (
    TIMELINE_FILE_NAME,
    StaticGenerationAuthorization,
    StaticGenerationProposal,
    authorization_sha256,
)
from gamingcreator.domain.actor_details import AttributeKind, AttributeStatus
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.static_observations import (
    MAX_STATIC_OBSERVATION_ACTORS,
    StaticActor,
    StaticAttribute,
)

LEDGER_SCHEMA_VERSION = "static-observation-generation-ledger-v1"
ATTEMPT_SCHEMA_VERSION = "static-observation-generation-attempt-v1"
LEDGER_SQLITE_NAME = "generation-ledger.sqlite3"
LEDGER_INITIALIZED_MARKER = "ledger-initialized"
LEDGER_INITIALIZATION_LOCK = "init.lock"
MAX_ATTEMPT_FILE_BYTES = 65_536
_MAX_INT = 2**63 - 1

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,8})?\Z")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z"
)
_DIAGNOSTIC = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_ATTEMPT_ID = re.compile(r"attempt-[0-9a-f]{32}\Z")

_LEDGER_USER_VERSION = 1
_LEDGER_SCHEMA = (
    """
    CREATE TABLE generation_meta (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE generation_authorizations (
        authorization_id TEXT PRIMARY KEY NOT NULL,
        authorization_sha256 TEXT NOT NULL,
        proposal_sha256 TEXT NOT NULL,
        project_root TEXT NOT NULL,
        database_path TEXT NOT NULL,
        ledger_root TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        currency TEXT NOT NULL,
        max_cost_cny TEXT NOT NULL,
        max_requests INTEGER NOT NULL,
        max_input_frames INTEGER NOT NULL,
        bound_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE generation_attempts (
        request_key TEXT PRIMARY KEY NOT NULL,
        attempt_id TEXT NOT NULL UNIQUE,
        authorization_id TEXT NOT NULL,
        authorization_sha256 TEXT NOT NULL,
        proposal_sha256 TEXT NOT NULL,
        run_id TEXT NOT NULL,
        collection_id TEXT NOT NULL,
        reservation_cny TEXT NOT NULL,
        currency TEXT NOT NULL,
        planned_at TEXT NOT NULL,
        status TEXT NOT NULL,
        revision INTEGER NOT NULL,
        input_frames INTEGER NOT NULL,
        charge_cny TEXT,
        charge_status TEXT NOT NULL,
        result_status TEXT,
        published INTEGER NOT NULL,
        file_sha256 TEXT NOT NULL,
        recorded_at TEXT,
        settled_at TEXT,
        FOREIGN KEY (authorization_id)
            REFERENCES generation_authorizations (authorization_id)
            ON DELETE RESTRICT
    )
    """,
)
_REQUIRED_COLUMNS = {
    "generation_meta": frozenset({"key", "value"}),
    "generation_authorizations": frozenset(
        {
            "authorization_id",
            "authorization_sha256",
            "proposal_sha256",
            "project_root",
            "database_path",
            "ledger_root",
            "provider",
            "model",
            "currency",
            "max_cost_cny",
            "max_requests",
            "max_input_frames",
            "bound_at",
        }
    ),
    "generation_attempts": frozenset(
        {
            "request_key",
            "attempt_id",
            "authorization_id",
            "authorization_sha256",
            "proposal_sha256",
            "run_id",
            "collection_id",
            "reservation_cny",
            "currency",
            "planned_at",
            "status",
            "revision",
            "input_frames",
            "charge_cny",
            "charge_status",
            "result_status",
            "published",
            "file_sha256",
            "recorded_at",
            "settled_at",
        }
    ),
}
_ATTEMPT_FIELDS = frozenset(
    {
        "schemaVersion",
        "attemptId",
        "requestKey",
        "authorizationId",
        "authorizationSha256",
        "proposalSha256",
        "runId",
        "collectionId",
        "reservationCny",
        "currency",
        "plannedAt",
        "revision",
        "inputFrames",
        "status",
        "result",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "status",
        "actors",
        "metadata",
        "responseSha256",
        "responseBytes",
        "contentBytes",
        "httpStatus",
        "diagnostics",
        "recordedAt",
    }
)
_METADATA_FIELDS = frozenset(
    {
        "provider",
        "requestedModel",
        "actualModel",
        "modelRevision",
        "promptVersion",
        "schemaVersion",
        "attempt",
        "usage",
        "elapsedMs",
        "priceVersion",
        "requestId",
        "executionDetails",
    }
)
_USAGE_FIELDS = frozenset(
    {
        "inputTokens",
        "outputTokens",
        "cachedInputTokens",
        "originalCost",
        "currency",
        "costCny",
        "costStatus",
    }
)
_ACTOR_FIELDS = frozenset({"actorId", "attributes"})
_ATTRIBUTE_FIELDS = frozenset({"partGroup", "partId", "kind", "value", "status"})


def _storage_error(code: str, message: str) -> AppError:
    return AppError(code, message, ExitCode.STORAGE)


def _busy_error(code: str, message: str) -> AppError:
    return AppError(code, message, ExitCode.BUDGET)


def _inconsistent() -> AppError:
    return _storage_error(
        "static_generation.ledger_inconsistent",
        "静态生成账本、attempt文件或重算投影不一致；失败关闭。",
    )


def _corrupt() -> AppError:
    return _storage_error(
        "static_generation.ledger_corrupt", "静态生成账本已损坏或版本不受支持；失败关闭。"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise _inconsistent()
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "0E-8") else text


def _decimal_value(value: object, *, optional: bool = False) -> Decimal | None:
    if value is None and optional:
        return None
    if type(value) is not str or not _DECIMAL.fullmatch(value):
        raise _inconsistent()
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise _inconsistent() from None
    if not amount.is_finite() or amount < 0 or _decimal_text(amount) != value:
        raise _inconsistent()
    return amount


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise _inconsistent()
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    del value
    raise _inconsistent()


def _decode_document(data: bytes) -> dict[str, object]:
    if type(data) is not bytes or not data or len(data) > MAX_ATTEMPT_FILE_BYTES:
        raise _inconsistent()
    if data.startswith(b"\xef\xbb\xbf"):
        raise _inconsistent()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _inconsistent() from None
    try:
        decoded: object = json.loads(
            text, object_pairs_hook=_pairs, parse_constant=_invalid_constant
        )
    except (json.JSONDecodeError, RecursionError):
        raise _inconsistent() from None
    if type(decoded) is not dict:
        raise _inconsistent()
    return cast(dict[str, object], decoded)


def _object(value: object, fields: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or set(cast(dict[str, object], value)) != fields:
        raise _inconsistent()
    return cast(dict[str, object], value)


def _string(value: object) -> str:
    if type(value) is not str:
        raise _inconsistent()
    return value


def _hash_value(value: object) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise _inconsistent()
    return value


def _identifier(value: object) -> str:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise _inconsistent()
    return value


def _integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _inconsistent()
    return value


def _timestamp(value: object) -> str:
    if type(value) is not str or not _TIMESTAMP.fullmatch(value):
        raise _inconsistent()
    return value


def _array(value: object, maximum: int) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        raise _inconsistent()
    return cast(list[object], value)


def _attempt_id_for(request_key: str) -> str:
    return "attempt-" + _sha256(("static-generation:" + request_key).encode("utf-8"))[:32]


def _assert_plain_file(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_junction():
            raise _storage_error(
                "static_generation.ledger_path", "静态生成账本文件不能是符号链接或目录联接。"
            )
        if path.exists():
            stat = path.lstat()
            if stat.st_nlink != 1 or not path.is_file():
                raise _storage_error(
                    "static_generation.ledger_path", "静态生成账本文件必须是普通单链接文件。"
                )
    except OSError:
        raise _storage_error(
            "static_generation.ledger_path", "无法核对静态生成账本文件。"
        ) from None


def _assert_plain_directory(path: Path, *, create: bool) -> Path:
    try:
        if path.is_symlink() or path.is_junction():
            raise _storage_error(
                "static_generation.ledger_path", "静态生成账本目录不能是符号链接或目录联接。"
            )
        if create:
            path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise _storage_error(
            "static_generation.ledger_path", "无法创建静态生成账本目录。"
        ) from error
    try:
        resolved = path.resolve()
    except OSError:
        raise _storage_error(
            "static_generation.ledger_path", "无法解析静态生成账本目录。"
        ) from None
    if not resolved.is_dir():
        raise _storage_error("static_generation.ledger_path", "静态生成账本路径必须是目录。")
    return resolved


class _NonBlockingFileLock:
    """An OS lock owned by this open handle; closing releases it even after a crash."""

    def __init__(self, path: Path, code: str, message: str) -> None:
        self._path = path
        self._code = code
        self._message = message
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        try:
            handle = self._path.open("a+b", buffering=0)
        except OSError:
            raise _storage_error(
                "static_generation.ledger_lock", "无法打开静态生成锁文件。"
            ) from None
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise _busy_error(self._code, self._message) from None
        self._handle = handle

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            handle.close()


class _BlockingInitializationLock:
    """Serializes one-time ledger initialization; released by the OS after a crash."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        try:
            handle = self._path.open("a+b", buffering=0)
        except OSError:
            raise _storage_error(
                "static_generation.ledger_lock", "无法打开静态生成初始化锁。"
            ) from None
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            handle.close()
            raise _storage_error(
                "static_generation.ledger_lock", "无法等待静态生成账本初始化。"
            ) from None
        self._handle = handle

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            handle.close()


@dataclass(frozen=True, slots=True)
class _FileAttempt:
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
    result: StaticAttemptResult | None


@dataclass(frozen=True, slots=True)
class _Row:
    request_key: str
    attempt_id: str
    authorization_id: str
    authorization_sha256: str
    proposal_sha256: str
    run_id: str
    collection_id: str
    reservation_cny: Decimal
    currency: str
    planned_at: str
    status: str
    revision: int
    input_frames: int
    charge_cny: Decimal | None
    charge_status: str
    result_status: str | None
    published: bool
    file_sha256: str
    recorded_at: str | None
    settled_at: str | None


def _usage_document(usage: ProviderUsage) -> dict[str, object]:
    return {
        "inputTokens": usage.input_tokens,
        "outputTokens": usage.output_tokens,
        "cachedInputTokens": usage.cached_input_tokens,
        "originalCost": None if usage.original_cost is None else _decimal_text(usage.original_cost),
        "currency": usage.currency,
        "costCny": None if usage.cost_cny is None else _decimal_text(usage.cost_cny),
        "costStatus": usage.cost_status.value,
    }


def _load_usage(value: object) -> ProviderUsage:
    item = _object(value, _USAGE_FIELDS)
    try:
        cost_status = CostStatus(_string(item["costStatus"]))
    except ValueError:
        raise _inconsistent() from None
    currency = item["currency"]
    if currency is not None:
        currency = _string(currency)
    return ProviderUsage(
        _integer(item["inputTokens"], 0, _MAX_INT) if item["inputTokens"] is not None else None,
        _integer(item["outputTokens"], 0, _MAX_INT) if item["outputTokens"] is not None else None,
        _integer(item["cachedInputTokens"], 0, _MAX_INT)
        if item["cachedInputTokens"] is not None
        else None,
        _decimal_value(item["originalCost"], optional=True),
        currency,
        _decimal_value(item["costCny"], optional=True),
        cost_status,
    )


def _metadata_document(metadata: InvocationMetadata) -> dict[str, object]:
    return {
        "provider": metadata.provider,
        "requestedModel": metadata.requested_model,
        "actualModel": metadata.actual_model,
        "modelRevision": metadata.model_revision,
        "promptVersion": metadata.prompt_version,
        "schemaVersion": metadata.schema_version,
        "attempt": metadata.attempt,
        "usage": _usage_document(metadata.usage),
        "elapsedMs": metadata.elapsed_ms,
        "priceVersion": metadata.price_version,
        "requestId": metadata.request_id,
        "executionDetails": metadata.execution_details,
    }


def _load_metadata(value: object) -> InvocationMetadata:
    item = _object(value, _METADATA_FIELDS)

    def optional_text(name: str) -> str | None:
        raw = item[name]
        return None if raw is None else _string(raw)

    return InvocationMetadata(
        _string(item["provider"]),
        _string(item["requestedModel"]),
        optional_text("actualModel"),
        optional_text("modelRevision"),
        _string(item["promptVersion"]),
        _string(item["schemaVersion"]),
        _integer(item["attempt"], 0, _MAX_INT),
        _load_usage(item["usage"]),
        _integer(item["elapsedMs"], 0, _MAX_INT) if item["elapsedMs"] is not None else None,
        optional_text("priceVersion"),
        optional_text("requestId"),
        optional_text("executionDetails"),
    )


def _attribute_document(attribute: StaticAttribute) -> dict[str, object]:
    return {
        "partGroup": attribute.part_group,
        "partId": attribute.part_id,
        "kind": attribute.kind.value,
        "value": attribute.value,
        "status": attribute.status.value,
    }


def _actor_document(actor: StaticActor) -> dict[str, object]:
    return {
        "actorId": actor.actor_id,
        "attributes": [_attribute_document(item) for item in actor.attributes],
    }


def _load_attribute(value: object) -> StaticAttribute:
    item = _object(value, _ATTRIBUTE_FIELDS)
    try:
        kind = AttributeKind(_string(item["kind"]))
        status = AttributeStatus(_string(item["status"]))
    except ValueError:
        raise _inconsistent() from None
    return StaticAttribute(
        _string(item["partGroup"]),
        _string(item["partId"]),
        kind,
        _string(item["value"]),
        status,
    )


def _load_actor(value: object) -> StaticActor:
    item = _object(value, _ACTOR_FIELDS)
    return StaticActor(
        _string(item["actorId"]),
        tuple(_load_attribute(entry) for entry in _array(item["attributes"], 16)),
    )


def _result_document(result: StaticAttemptResult) -> dict[str, object]:
    return {
        "status": result.status,
        "actors": [_actor_document(actor) for actor in result.actors],
        "metadata": _metadata_document(result.metadata),
        "responseSha256": result.response_sha256,
        "responseBytes": result.response_bytes,
        "contentBytes": result.content_bytes,
        "httpStatus": result.http_status,
        "diagnostics": list(result.diagnostics),
        "recordedAt": result.recorded_at,
    }


def _load_result(value: object) -> StaticAttemptResult:
    item = _object(value, _RESULT_FIELDS)
    raw_status = _string(item["status"])
    if raw_status not in ("observed", "no_observations", "failed", "cancelled"):
        raise _inconsistent()
    diagnostics = tuple(_string(entry) for entry in _array(item["diagnostics"], 4))
    if any(not _DIAGNOSTIC.fullmatch(entry) for entry in diagnostics):
        raise _inconsistent()
    return StaticAttemptResult(
        cast(
            Literal["observed", "no_observations", "failed", "cancelled"],
            raw_status,
        ),
        tuple(
            _load_actor(entry) for entry in _array(item["actors"], MAX_STATIC_OBSERVATION_ACTORS)
        ),
        _load_metadata(item["metadata"]),
        None if item["responseSha256"] is None else _hash_value(item["responseSha256"]),
        _integer(item["responseBytes"], 0, _MAX_INT),
        _integer(item["contentBytes"], 0, _MAX_INT) if item["contentBytes"] is not None else None,
        _integer(item["httpStatus"], 100, 599) if item["httpStatus"] is not None else None,
        diagnostics,
        _timestamp(item["recordedAt"]),
    )


def _load_file_attempt(document: dict[str, object]) -> _FileAttempt:
    item = _object(document, _ATTEMPT_FIELDS)
    if _string(item["schemaVersion"]) != ATTEMPT_SCHEMA_VERSION:
        raise _inconsistent()
    revision = _integer(item["revision"], 1, 2)
    status = _string(item["status"])
    if status not in ("planned", "recorded"):
        raise _inconsistent()
    if (status == "planned") != (revision == 1) or (status == "recorded") != (revision == 2):
        raise _inconsistent()
    result = None if item["result"] is None else _load_result(item["result"])
    if (result is None) != (revision == 1):
        raise _inconsistent()
    attempt_id = _string(item["attemptId"])
    if not _ATTEMPT_ID.fullmatch(attempt_id):
        raise _inconsistent()
    request_key = _hash_value(item["requestKey"])
    if attempt_id != _attempt_id_for(request_key):
        raise _inconsistent()
    reservation = _decimal_value(item["reservationCny"])
    assert reservation is not None
    if reservation <= 0:
        raise _inconsistent()
    if _string(item["currency"]) != "CNY":
        raise _inconsistent()
    return _FileAttempt(
        attempt_id,
        request_key,
        _identifier(item["authorizationId"]),
        _hash_value(item["authorizationSha256"]),
        _hash_value(item["proposalSha256"]),
        _identifier(item["runId"]),
        _identifier(item["collectionId"]),
        reservation,
        "CNY",
        _timestamp(item["plannedAt"]),
        revision,
        _integer(item["inputFrames"], 1, 1),
        result,
    )


def _file_document(attempt: _FileAttempt) -> dict[str, object]:
    return {
        "schemaVersion": ATTEMPT_SCHEMA_VERSION,
        "attemptId": attempt.attempt_id,
        "requestKey": attempt.request_key,
        "authorizationId": attempt.authorization_id,
        "authorizationSha256": attempt.authorization_sha256,
        "proposalSha256": attempt.proposal_sha256,
        "runId": attempt.run_id,
        "collectionId": attempt.collection_id,
        "reservationCny": _decimal_text(attempt.reservation_cny),
        "currency": attempt.currency,
        "plannedAt": attempt.planned_at,
        "revision": attempt.revision,
        "inputFrames": attempt.input_frames,
        "status": "planned" if attempt.revision == 1 else "recorded",
        "result": None if attempt.result is None else _result_document(attempt.result),
    }


class SqliteStaticGenerationLedger:
    """One fixed project ledger; no collection, output path, or restart selects it."""

    def __init__(self, project: Path) -> None:
        try:
            if project.is_symlink() or project.is_junction():
                raise _storage_error(
                    "static_generation.ledger_path", "静态生成项目不能是符号链接或目录联接。"
                )
            self._project = project.resolve()
        except OSError:
            raise _storage_error(
                "static_generation.ledger_path", "无法解析静态生成项目目录。"
            ) from None
        if not self._project.is_dir():
            raise _storage_error("static_generation.ledger_path", "静态生成项目目录不存在。")
        self.root = _assert_plain_directory(
            self._project / ".static-observation-generation" / "ledger", create=True
        )
        self._attempts = _assert_plain_directory(self.root / "attempts", create=True)
        self._locks = _assert_plain_directory(self.root / "locks", create=True)
        self.database = self._project / TIMELINE_FILE_NAME
        self._ledger_path = self.root / LEDGER_SQLITE_NAME
        self._marker_path = self.root / LEDGER_INITIALIZED_MARKER
        _assert_plain_file(self._ledger_path)
        _assert_plain_file(self._marker_path)
        for suffix in ("-wal", "-shm", "-journal"):
            _assert_plain_file(self._ledger_path.with_name(self._ledger_path.name + suffix))
        initialization_lock: _BlockingInitializationLock | None = None
        try:
            if not self._initialized_pair_present():
                initialization_lock = _BlockingInitializationLock(
                    self._locks / LEDGER_INITIALIZATION_LOCK
                )
                initialization_lock.acquire()
            create = False if initialization_lock is None else self._initialization_decision()
            try:
                self._connection: sqlite3.Connection | None = sqlite3.connect(
                    str(self._ledger_path), timeout=5.0, autocommit=True
                )
            except sqlite3.Error as error:
                raise _corrupt() from error
            try:
                self._connection.row_factory = sqlite3.Row
                self._connection.execute("PRAGMA foreign_keys=ON")
                self._connection.execute("PRAGMA busy_timeout=5000")
                self._connection.execute("PRAGMA synchronous=FULL")
                if create:
                    self._create_schema()
                    self._write_marker()
                else:
                    with self._transaction():
                        self._validate_schema()
                self._validate_marker()
                if self._ledger_path.resolve().parent != self.root:
                    raise _storage_error(
                        "static_generation.ledger_path", "静态生成账本逃逸了固定账本根。"
                    )
            except AppError:
                self.close()
                raise
            except sqlite3.Error as error:
                self.close()
                raise _corrupt() from error
        finally:
            if initialization_lock is not None:
                initialization_lock.release()

    def _initialized_pair_present(self) -> bool:
        try:
            if not self._ledger_path.is_file() or not self._marker_path.is_file():
                return False
            return self._ledger_path.stat().st_size > 0
        except OSError:
            raise _storage_error(
                "static_generation.ledger_path", "无法核对静态生成账本文件。"
            ) from None

    def _has_durable_traces(self) -> bool:
        if self._marker_path.is_file():
            return True
        if any(self._attempts.iterdir()):
            return True
        for suffix in ("-wal", "-shm", "-journal"):
            if self._ledger_path.with_name(self._ledger_path.name + suffix).exists():
                return True
        for entry in self._locks.iterdir():
            if entry.name != LEDGER_INITIALIZATION_LOCK:
                return True
        known = {
            LEDGER_SQLITE_NAME,
            LEDGER_INITIALIZED_MARKER,
            "attempts",
            "locks",
        }
        return any(entry.name not in known for entry in self.root.iterdir())

    def _initialization_decision(self) -> bool:
        """Decide under the initialization lock; an existing empty DB always fails closed."""
        try:
            exists = self._ledger_path.is_file()
            size = self._ledger_path.stat().st_size if exists else None
        except OSError:
            raise _storage_error(
                "static_generation.ledger_path", "无法核对静态生成账本文件。"
            ) from None
        if size is not None:
            if size == 0:
                raise _corrupt()
            if self._marker_path.is_file():
                return False
            raise _inconsistent()
        if self._has_durable_traces():
            raise _inconsistent()
        return True

    def _write_marker(self) -> None:
        temporary = self._marker_path.with_name(f".{self._marker_path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(LEDGER_SCHEMA_VERSION.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._marker_path)
        except OSError as error:
            raise _storage_error(
                "static_generation.ledger_path", "无法写入静态生成账本初始化标记。"
            ) from error
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass

    def _validate_marker(self) -> None:
        try:
            if not self._marker_path.is_file():
                raise _inconsistent()
            content = self._marker_path.read_bytes()
        except OSError:
            raise _inconsistent() from None
        if content != LEDGER_SCHEMA_VERSION.encode("utf-8"):
            raise _inconsistent()

    @property
    def _db(self) -> sqlite3.Connection:
        connection = getattr(self, "_connection", None)
        if connection is None:
            raise _storage_error("static_generation.ledger_closed", "静态生成账本已关闭。")
        return cast(sqlite3.Connection, connection)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def _create_schema(self) -> None:
        with self._transaction():
            row = self._db.execute("PRAGMA user_version").fetchone()
            version = 0 if row is None else cast(int, row[0])
            if version == _LEDGER_USER_VERSION:
                # A concurrent process created the same fixed schema while this one waited.
                self._validate_schema()
                return
            if version != 0:
                raise _corrupt()
            tables = self._db.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
            if tables is not None and tables[0]:
                raise _corrupt()
            self._db.execute(f"PRAGMA user_version={_LEDGER_USER_VERSION}")
            for statement in _LEDGER_SCHEMA:
                self._db.execute(statement)
            self._db.execute(
                "INSERT INTO generation_meta (key,value) VALUES ('schema_version',?)",
                (LEDGER_SCHEMA_VERSION,),
            )
            self._validate_schema()

    def _validate_schema(self) -> None:
        row = self._db.execute("PRAGMA user_version").fetchone()
        if row is None or cast(int, row[0]) != _LEDGER_USER_VERSION:
            raise _corrupt()
        meta = self._db.execute(
            "SELECT value FROM generation_meta WHERE key='schema_version'"
        ).fetchone()
        if meta is None or cast(str, meta[0]) != LEDGER_SCHEMA_VERSION:
            raise _corrupt()
        for table, required in _REQUIRED_COLUMNS.items():
            columns = {
                cast(str, item[1]) for item in self._db.execute(f"PRAGMA table_info({table})")
            }
            if not required <= columns:
                raise _corrupt()
        integrity = self._db.execute("PRAGMA integrity_check").fetchall()
        if len(integrity) != 1 or cast(str, integrity[0][0]) != "ok":
            raise _corrupt()

    @contextmanager
    def request_guard(self, proposal_sha256: str) -> Iterator[None]:
        if type(proposal_sha256) is not str or not _HASH.fullmatch(proposal_sha256):
            raise _inconsistent()
        lock = _NonBlockingFileLock(
            self._locks / f"request-{proposal_sha256}.lock",
            "static_generation.request_busy",
            "同一冻结提案已有执行进程；本次不发送、不等待。",
        )
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    @contextmanager
    def _budget_lock(self) -> Iterator[None]:
        lock = _NonBlockingFileLock(
            self._locks / "budget.lock",
            "static_generation.budget_busy",
            "静态生成预算账本正被另一进程预留或结算；本次不等待。",
        )
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def _attempt_path(self, attempt_id: str) -> Path:
        if not _ATTEMPT_ID.fullmatch(attempt_id):
            raise _inconsistent()
        return self._attempts / f"{attempt_id}.json"

    def _read_attempt_file(self, attempt_id: str) -> tuple[_FileAttempt, str] | None:
        path = self._attempt_path(attempt_id)
        try:
            if path.is_symlink() or path.is_junction():
                raise _inconsistent()
            if not path.exists():
                return None
            if not path.is_file() or path.lstat().st_nlink != 1:
                raise _inconsistent()
            if path.lstat().st_size > MAX_ATTEMPT_FILE_BYTES:
                raise _inconsistent()
            data = path.read_bytes()
        except OSError:
            raise _inconsistent() from None
        document = _decode_document(data)
        return _load_file_attempt(document), _sha256(data)

    def _write_attempt_file(self, attempt: _FileAttempt) -> str:
        data = _canonical_json(_file_document(attempt)).encode("utf-8")
        if len(data) > MAX_ATTEMPT_FILE_BYTES:
            raise _inconsistent()
        path = self._attempt_path(attempt.attempt_id)
        temporary = path.with_name(f".{path.stem}.{os.getpid()}.tmp")
        try:
            if temporary.exists():
                temporary.unlink()
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as error:
            raise _storage_error(
                "static_generation.attempt_write", "无法写入静态生成attempt文件。"
            ) from error
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass
        return _sha256(data)

    def _row(self, request_key: str) -> _Row | None:
        row = cast(
            sqlite3.Row | None,
            self._db.execute(
                "SELECT * FROM generation_attempts WHERE request_key=?", (request_key,)
            ).fetchone(),
        )
        return None if row is None else self._row_from(row)

    def _row_from(self, row: sqlite3.Row) -> _Row:
        reservation = _decimal_value(row["reservation_cny"])
        if reservation is None or reservation <= 0:
            raise _inconsistent()
        charge = _decimal_value(row["charge_cny"], optional=True)
        charge_status = cast(str, row["charge_status"])
        if charge_status not in ("known", "unknown") or (charge is None) != (
            charge_status == "unknown"
        ):
            raise _inconsistent()
        status = cast(str, row["status"])
        revision = cast(int, row["revision"])
        result_status = cast(str | None, row["result_status"])
        if status not in ("planned", "recorded"):
            raise _inconsistent()
        if (status == "planned") != (revision == 1) or (status == "recorded") != (revision == 2):
            raise _inconsistent()
        if revision == 2 and result_status not in (
            "observed",
            "no_observations",
            "failed",
            "cancelled",
        ):
            raise _inconsistent()
        if revision == 1 and result_status is not None:
            raise _inconsistent()
        published = row["published"]
        if published not in (0, 1):
            raise _inconsistent()
        recorded_at = cast(str | None, row["recorded_at"])
        settled_at = cast(str | None, row["settled_at"])
        return _Row(
            cast(str, row["request_key"]),
            cast(str, row["attempt_id"]),
            cast(str, row["authorization_id"]),
            cast(str, row["authorization_sha256"]),
            cast(str, row["proposal_sha256"]),
            cast(str, row["run_id"]),
            cast(str, row["collection_id"]),
            reservation,
            cast(str, row["currency"]),
            cast(str, row["planned_at"]),
            status,
            revision,
            cast(int, row["input_frames"]),
            charge,
            charge_status,
            result_status,
            bool(published),
            cast(str, row["file_sha256"]),
            recorded_at,
            settled_at,
        )

    def _authorization_row(self, authorization_id: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self._db.execute(
                "SELECT * FROM generation_authorizations WHERE authorization_id=?",
                (authorization_id,),
            ).fetchone(),
        )

    def bind_authorization(self, authorization: StaticGenerationAuthorization) -> None:
        digest = authorization_sha256(authorization)
        if digest != authorization.authorization_sha256:
            raise AppError(
                "static_generation.authorization_hash",
                "人类授权内容与冻结哈希不一致。",
                ExitCode.BUDGET,
            )
        values = (
            authorization.authorization_id,
            digest,
            authorization.proposal_sha256,
            authorization.project_root,
            authorization.database_path,
            authorization.ledger_root,
            authorization.identity.provider,
            authorization.identity.model,
            authorization.currency,
            _decimal_text(authorization.max_cost_cny),
            authorization.max_requests,
            authorization.max_input_frames,
        )
        try:
            with self._transaction():
                existing = self._authorization_row(authorization.authorization_id)
                if existing is None:
                    self._db.execute(
                        """
                        INSERT INTO generation_authorizations (
                            authorization_id, authorization_sha256, proposal_sha256,
                            project_root, database_path, ledger_root, provider, model,
                            currency, max_cost_cny, max_requests, max_input_frames, bound_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (*values, _timestamp_now()),
                    )
                    return
                stored = tuple(
                    existing[key]
                    for key in (
                        "authorization_id",
                        "authorization_sha256",
                        "proposal_sha256",
                        "project_root",
                        "database_path",
                        "ledger_root",
                        "provider",
                        "model",
                        "currency",
                        "max_cost_cny",
                        "max_requests",
                        "max_input_frames",
                    )
                )
                if stored != values:
                    raise AppError(
                        "static_generation.authorization_conflict",
                        "相同 authorizationId 首次绑定了不同内容；失败关闭。",
                        ExitCode.BUDGET,
                    )
        except AppError:
            raise
        except sqlite3.Error as error:
            raise _corrupt() from error

    def _read_expected_attempt(self, request_key: str) -> tuple[_FileAttempt, str] | None:
        row = self._row(request_key)
        attempt_id = row.attempt_id if row is not None else _attempt_id_for(request_key)
        found = self._read_attempt_file(attempt_id)
        if found is None:
            return None
        attempt, digest = found
        if attempt.request_key != request_key:
            raise _inconsistent()
        return attempt, digest

    def _insert_row_from_file(self, attempt: _FileAttempt, digest: str) -> None:
        charge, charge_status = (
            (None, "unknown") if attempt.result is None else attempt_charge(attempt.result)
        )
        self._db.execute(
            """
            INSERT INTO generation_attempts (
                request_key, attempt_id, authorization_id, authorization_sha256,
                proposal_sha256, run_id, collection_id, reservation_cny, currency,
                planned_at, status, revision, input_frames, charge_cny, charge_status,
                result_status, published, file_sha256, recorded_at, settled_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                attempt.request_key,
                attempt.attempt_id,
                attempt.authorization_id,
                attempt.authorization_sha256,
                attempt.proposal_sha256,
                attempt.run_id,
                attempt.collection_id,
                _decimal_text(attempt.reservation_cny),
                attempt.currency,
                attempt.planned_at,
                "planned" if attempt.revision == 1 else "recorded",
                attempt.revision,
                attempt.input_frames,
                None if charge is None else _decimal_text(charge),
                charge_status,
                None if attempt.result is None else attempt.result.status,
                0,
                digest,
                None if attempt.result is None else attempt.result.recorded_at,
                None if attempt.result is None else _timestamp_now(),
            ),
        )

    def _settle_row_from_file(self, attempt: _FileAttempt, digest: str) -> None:
        if attempt.result is None:
            raise _inconsistent()
        charge, charge_status = attempt_charge(attempt.result)
        self._db.execute(
            """
            UPDATE generation_attempts
            SET status='recorded', revision=?, charge_cny=?, charge_status=?,
                result_status=?, file_sha256=?, recorded_at=?, settled_at=?
            WHERE request_key=? AND revision=1 AND status='planned'
            """,
            (
                attempt.revision,
                None if charge is None else _decimal_text(charge),
                charge_status,
                attempt.result.status,
                digest,
                attempt.result.recorded_at,
                _timestamp_now(),
                attempt.request_key,
            ),
        )

    def _verify_row_matches_file(self, row: _Row, attempt: _FileAttempt) -> None:
        if (
            row.attempt_id != attempt.attempt_id
            or row.request_key != attempt.request_key
            or row.authorization_id != attempt.authorization_id
            or row.authorization_sha256 != attempt.authorization_sha256
            or row.proposal_sha256 != attempt.proposal_sha256
            or row.run_id != attempt.run_id
            or row.collection_id != attempt.collection_id
            or row.reservation_cny != attempt.reservation_cny
            or row.currency != attempt.currency
            or row.planned_at != attempt.planned_at
            or row.revision != attempt.revision
            or row.input_frames != attempt.input_frames
        ):
            raise _inconsistent()
        if attempt.result is None:
            if row.charge_status != "unknown" or row.charge_cny is not None:
                raise _inconsistent()
            if row.published:
                raise _inconsistent()
            return
        charge, status = attempt_charge(attempt.result)
        if row.charge_status != status or row.charge_cny != charge:
            raise _inconsistent()
        if row.result_status != attempt.result.status:
            raise _inconsistent()
        if row.published and attempt.result.status not in ("observed", "no_observations"):
            raise _inconsistent()

    def _state_from(self, row: _Row, attempt: _FileAttempt) -> StaticAttemptState:
        return StaticAttemptState(
            attempt.attempt_id,
            attempt.request_key,
            attempt.authorization_id,
            attempt.authorization_sha256,
            attempt.proposal_sha256,
            attempt.run_id,
            attempt.collection_id,
            attempt.reservation_cny,
            attempt.currency,
            attempt.planned_at,
            attempt.revision,
            attempt.input_frames,
            row.published,
            attempt.result,
            row.charge_cny,
            cast(Literal["known", "unknown"], row.charge_status),
        )

    def _reconcile_locked(self, request_key: str) -> StaticAttemptState | None:
        row = self._row(request_key)
        found = self._read_expected_attempt(request_key)
        if row is None and found is None:
            return None
        if found is None:
            raise _inconsistent()
        attempt, digest = found
        if row is None:
            authorization = self._authorization_row(attempt.authorization_id)
            if (
                authorization is None
                or cast(str, authorization["authorization_sha256"]) != attempt.authorization_sha256
            ):
                raise _inconsistent()
            self._insert_row_from_file(attempt, digest)
            row = self._row(request_key)
            if row is None or row.file_sha256 != digest or row.revision != attempt.revision:
                raise _inconsistent()
            self._verify_row_matches_file(row, attempt)
            return self._state_from(row, attempt)
        verdict = consistency_verdict(
            row_present=True,
            file_present=True,
            row_revision=row.revision,
            file_revision=attempt.revision,
            row_sha256=row.file_sha256,
            file_sha256=digest,
        )
        if verdict == "consistent":
            if row.file_sha256 != digest:
                raise _inconsistent()
            self._verify_row_matches_file(row, attempt)
        elif verdict == "settle_from_file":
            self._verify_planned_prefix(row, attempt)
            self._settle_row_from_file(attempt, digest)
            settled = self._row(request_key)
            if settled is None:
                raise _inconsistent()
            row = settled
            self._verify_row_matches_file(row, attempt)
        else:
            raise _inconsistent()
        if attempt.result is not None and row.recorded_at is None:
            raise _inconsistent()
        return self._state_from(row, attempt)

    def _verify_planned_prefix(self, row: _Row, attempt: _FileAttempt) -> None:
        if (
            row.attempt_id != attempt.attempt_id
            or row.request_key != attempt.request_key
            or row.authorization_id != attempt.authorization_id
            or row.authorization_sha256 != attempt.authorization_sha256
            or row.proposal_sha256 != attempt.proposal_sha256
            or row.run_id != attempt.run_id
            or row.collection_id != attempt.collection_id
            or row.reservation_cny != attempt.reservation_cny
            or row.planned_at != attempt.planned_at
        ):
            raise _inconsistent()

    def load_attempt(self, request_key: str) -> StaticAttemptState | None:
        if type(request_key) is not str or not _HASH.fullmatch(request_key):
            raise _inconsistent()
        try:
            with self._budget_lock():
                state = self._reconcile_locked(request_key)
                if state is not None:
                    self._verify_authorization_binding(state)
                return state
        except AppError:
            raise
        except sqlite3.Error as error:
            raise _corrupt() from error

    def _verify_authorization_binding(self, state: StaticAttemptState) -> None:
        row = self._authorization_row(state.authorization_id)
        if row is None or cast(str, row["authorization_sha256"]) != state.authorization_sha256:
            raise _inconsistent()

    def _all_attempts(self) -> tuple[StaticAttemptState, ...]:
        rows = cast(
            list[sqlite3.Row],
            self._db.execute(
                "SELECT request_key FROM generation_attempts ORDER BY request_key"
            ).fetchall(),
        )
        attempts: list[StaticAttemptState] = []
        for item in rows:
            state = self._reconcile_locked(cast(str, item["request_key"]))
            if state is None:
                raise _inconsistent()
            self._verify_authorization_binding(state)
            attempts.append(state)
        return tuple(attempts)

    def _authorization_attempts(
        self, authorization_id: str, authorization_sha256: str
    ) -> tuple[StaticAttemptState, ...]:
        attempts = self._all_attempts()
        return tuple(
            attempt
            for attempt in attempts
            if attempt.authorization_id == authorization_id
            and attempt.authorization_sha256 == authorization_sha256
        )

    def _ensure_attempt_authorization(
        self, state: StaticAttemptState, authorization: StaticGenerationAuthorization
    ) -> None:
        if (
            state.authorization_id != authorization.authorization_id
            or state.authorization_sha256 != authorization.authorization_sha256
        ):
            raise AppError(
                "static_generation.authorization_conflict",
                "同一冻结提案已由另一种人类授权执行；失败关闭且不新发送。",
                ExitCode.BUDGET,
            )

    def plan_attempt(
        self,
        proposal: StaticGenerationProposal,
        authorization: StaticGenerationAuthorization,
        *,
        planned_at: str,
    ) -> tuple[StaticAttemptState, bool]:
        if (
            authorization.proposal_sha256 != proposal.proposal_sha256
            or authorization.ledger_root != proposal.ledger_root
            or authorization.database_path != proposal.database_path
            or authorization.project_root != proposal.project_root
        ):
            raise AppError(
                "static_generation.authorization_scope",
                "人类授权的项目、数据库或账本根与冻结提案不一致。",
                ExitCode.BUDGET,
            )
        _timestamp(planned_at)
        try:
            with self._budget_lock():
                existing = self._reconcile_locked(proposal.proposal_sha256)
                if existing is not None:
                    self._ensure_attempt_authorization(existing, authorization)
                    return existing, False
                attempts = self._authorization_attempts(
                    authorization.authorization_id,
                    authorization.authorization_sha256,
                )
                ensure_plan_allowed(
                    attempts,
                    reservation_cny=proposal.reservation_cny,
                    currency=authorization.currency,
                    max_cost_cny=authorization.max_cost_cny,
                    max_requests=authorization.max_requests,
                    max_input_frames=authorization.max_input_frames,
                )
                bound = self._authorization_row(authorization.authorization_id)
                if (
                    bound is None
                    or cast(str, bound["authorization_sha256"])
                    != authorization.authorization_sha256
                ):
                    raise AppError(
                        "static_generation.authorization_conflict",
                        "人类授权尚未绑定或内容已变化；失败关闭。",
                        ExitCode.BUDGET,
                    )
                attempt = _FileAttempt(
                    _attempt_id_for(proposal.proposal_sha256),
                    proposal.proposal_sha256,
                    authorization.authorization_id,
                    authorization.authorization_sha256,
                    proposal.proposal_sha256,
                    proposal.run_id,
                    proposal.collection_id,
                    proposal.reservation_cny,
                    authorization.currency,
                    planned_at,
                    1,
                    1,
                    None,
                )
                digest = self._write_attempt_file(attempt)
                self._insert_row_from_file(attempt, digest)
                state = self._reconcile_locked(proposal.proposal_sha256)
                if state is None:
                    raise _inconsistent()
                return state, True
        except AppError:
            raise
        except sqlite3.Error as error:
            raise _corrupt() from error

    def record_result(self, *, request_key: str, result: StaticAttemptResult) -> StaticAttemptState:
        if type(request_key) is not str or not _HASH.fullmatch(request_key):
            raise _inconsistent()
        try:
            with self._budget_lock():
                state = self._reconcile_locked(request_key)
                if state is None:
                    raise _inconsistent()
                if state.result is not None:
                    if state.result == result:
                        return state
                    raise _inconsistent()
                found = self._read_expected_attempt(request_key)
                if found is None:
                    raise _inconsistent()
                planned, _ = found
                attempt, digest = self._persist_recorded_file(planned, result)
                self._settle_recorded_row(request_key, result, digest)
                settled = self._reconcile_locked(request_key)
                if settled is None or settled.result != result:
                    raise _inconsistent()
                return settled
        except AppError:
            raise
        except sqlite3.Error as error:
            raise _corrupt() from error

    def _persist_recorded_file(
        self, planned: _FileAttempt, result: StaticAttemptResult
    ) -> tuple[_FileAttempt, str]:
        attempt = _FileAttempt(
            planned.attempt_id,
            planned.request_key,
            planned.authorization_id,
            planned.authorization_sha256,
            planned.proposal_sha256,
            planned.run_id,
            planned.collection_id,
            planned.reservation_cny,
            planned.currency,
            planned.planned_at,
            2,
            1,
            result,
        )
        return attempt, self._write_attempt_file(attempt)

    def _settle_recorded_row(
        self, request_key: str, result: StaticAttemptResult, digest: str
    ) -> None:
        charge, charge_status = attempt_charge(result)
        self._db.execute(
            """
            UPDATE generation_attempts
            SET status='recorded', revision=2, charge_cny=?, charge_status=?,
                result_status=?, file_sha256=?, recorded_at=?, settled_at=?
            WHERE request_key=? AND revision=1 AND status='planned'
            """,
            (
                None if charge is None else _decimal_text(charge),
                charge_status,
                result.status,
                digest,
                result.recorded_at,
                _timestamp_now(),
                request_key,
            ),
        )

    def mark_published(self, request_key: str) -> StaticAttemptState:
        if type(request_key) is not str or not _HASH.fullmatch(request_key):
            raise _inconsistent()
        try:
            with self._budget_lock():
                state = self._reconcile_locked(request_key)
                if state is None or state.result is None:
                    raise _inconsistent()
                if state.result.status not in ("observed", "no_observations"):
                    raise _inconsistent()
                if not state.published:
                    self._db.execute(
                        "UPDATE generation_attempts SET published=1 WHERE request_key=?",
                        (request_key,),
                    )
                updated = self._reconcile_locked(request_key)
                if updated is None or not updated.published:
                    raise _inconsistent()
                return updated
        except AppError:
            raise
        except sqlite3.Error as error:
            raise _corrupt() from error

    def close(self) -> None:
        connection = getattr(self, "_connection", None)
        self._connection = None
        if connection is not None:
            try:
                cast(sqlite3.Connection, connection).close()
            except sqlite3.Error:
                pass


def _timestamp_now() -> str:
    return datetime.now(UTC).isoformat()
