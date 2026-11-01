"""Exclusive monthly entitlement usage ledger for local media preparation minutes."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO

from gamingcreator.application.entitlements import month_key
from gamingcreator.domain.errors import AppError, ExitCode

SCHEMA = "entitlement-usage-v1"
USAGE_NAME = "entitlement-usage.json"
LOCK_NAME = "entitlement-usage.lock"


class _UsageLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = self._path.open("a+b", buffering=0)
        except OSError as error:
            raise AppError(
                "storage.entitlement_usage", "无法打开套餐用量账本锁。", ExitCode.STORAGE
            ) from error
        try:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._handle = handle
        except OSError as error:
            handle.close()
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise AppError(
                    "storage.entitlement_usage_busy",
                    "套餐用量账本正被占用，请稍后重试。",
                    ExitCode.STORAGE,
                ) from error
            raise AppError(
                "storage.entitlement_usage", "无法锁定套餐用量账本。", ExitCode.STORAGE
            ) from error

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            handle.close()


@contextmanager
def _locked(creations_root: Path) -> Iterator[None]:
    lock = _UsageLock(creations_root / LOCK_NAME)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def usage_path(creations_root: Path) -> Path:
    return creations_root / USAGE_NAME


def preparation_key(project: Path, paths: list[Path]) -> str:
    payload = json.dumps(
        {
            "project": str(project.resolve()),
            "paths": [str(path.resolve()) for path in sorted(paths, key=lambda item: str(item))],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def probe_duration_seconds(repository: Path, media: Path) -> float:
    """Read container duration with the project-local ffprobe (sync, no download)."""
    ffprobe = repository.resolve() / ".tools" / "ffmpeg" / "bin" / "ffprobe.exe"
    if not ffprobe.is_file():
        raise AppError(
            "environment.ffmpeg", "本机 ffprobe 不可用，无法计量准备分钟。", ExitCode.ENVIRONMENT
        )
    try:
        completed = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(media),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except OSError as error:
        raise AppError(
            "environment.ffmpeg", "无法启动 ffprobe 计量录像时长。", ExitCode.ENVIRONMENT
        ) from error
    if completed.returncode != 0:
        raise AppError(
            "input.media_probe",
            f"无法读取录像时长：{media.name}",
            ExitCode.INPUT,
        )
    try:
        duration = Fraction(json.loads(completed.stdout)["format"]["duration"])
    except (TypeError, ValueError, KeyError, ZeroDivisionError) as error:
        raise AppError(
            "input.media_probe",
            f"录像时长无效：{media.name}",
            ExitCode.INPUT,
        ) from error
    if duration <= 0:
        raise AppError(
            "input.media_probe",
            f"录像时长无效：{media.name}",
            ExitCode.INPUT,
        )
    return float(duration)


def _empty_document() -> dict[str, object]:
    return {"schemaVersion": SCHEMA, "months": {}}


def _load_unlocked(path: Path) -> dict[str, object]:
    if not path.is_file():
        return _empty_document()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise AppError(
            "storage.entitlement_usage", "套餐用量账本损坏，请保留文件并检查。", ExitCode.STORAGE
        ) from None
    if type(raw) is not dict or raw.get("schemaVersion") != SCHEMA:
        raise AppError("storage.entitlement_usage", "套餐用量账本版本无效。", ExitCode.STORAGE)
    months = raw.get("months")
    if type(months) is not dict:
        raise AppError("storage.entitlement_usage", "套餐用量账本格式无效。", ExitCode.STORAGE)
    return raw


def _write_unlocked(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def preparation_seconds_this_month(creations_root: Path, now: str | None = None) -> float:
    stamp = now or datetime.now(UTC).isoformat()
    month = month_key(stamp)
    with _locked(creations_root):
        document = _load_unlocked(usage_path(creations_root))
        months = document["months"]
        assert isinstance(months, dict)
        row = months.get(month)
        if type(row) is not dict:
            return 0.0
        value = row.get("preparationSeconds", 0)
        return float(value) if isinstance(value, (int, float)) and value >= 0 else 0.0


def preparation_minutes_this_month(creations_root: Path, now: str | None = None) -> float:
    return preparation_seconds_this_month(creations_root, now) / 60.0


def has_preparation_entry(creations_root: Path, key: str, now: str | None = None) -> bool:
    stamp = now or datetime.now(UTC).isoformat()
    month = month_key(stamp)
    with _locked(creations_root):
        document = _load_unlocked(usage_path(creations_root))
        months = document["months"]
        assert isinstance(months, dict)
        row = months.get(month)
        if type(row) is not dict:
            return False
        entries = row.get("entries")
        if type(entries) is not list:
            return False
        return any(type(item) is dict and item.get("key") == key for item in entries)


def record_preparation_if_new(
    creations_root: Path,
    *,
    key: str,
    seconds: float,
    now: str | None = None,
) -> bool:
    """Record preparation seconds once per key this calendar month.

    Policy: minutes are reserved when a new prepare submit is accepted (before the
    batch runs). Failed batches still count. Resume with the same key does not add.
    Returns True when a new entry was written.
    """
    if seconds <= 0:
        raise ValueError("preparation seconds must be positive")
    stamp = now or datetime.now(UTC).isoformat()
    month = month_key(stamp)
    with _locked(creations_root):
        path = usage_path(creations_root)
        document = _load_unlocked(path)
        months = document.setdefault("months", {})
        assert isinstance(months, dict)
        row = months.get(month)
        if type(row) is not dict:
            row = {"preparationSeconds": 0.0, "entries": []}
            months[month] = row
        entries = row.setdefault("entries", [])
        if type(entries) is not list:
            raise AppError("storage.entitlement_usage", "套餐用量账本格式无效。", ExitCode.STORAGE)
        if any(type(item) is dict and item.get("key") == key for item in entries):
            return False
        entries.append(
            {
                "key": key,
                "seconds": float(seconds),
                "recordedAt": stamp,
            }
        )
        total = float(row.get("preparationSeconds") or 0) + float(seconds)
        row["preparationSeconds"] = total
        _write_unlocked(path, document)
        return True
