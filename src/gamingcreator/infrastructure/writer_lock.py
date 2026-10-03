"""A process-owned, non-blocking writer lock; the persistent file is not the lock."""

from __future__ import annotations

import errno
import sys
from pathlib import Path
from typing import BinaryIO

from gamingcreator.domain.errors import AppError, ExitCode


class ProjectWriterLock:
    def __init__(self, project: Path) -> None:
        self._path = project / ".analysis-writer.lock"
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        try:
            # Never truncate a file whose first byte may be owned by another process.
            handle = self._path.open("a+b", buffering=0)
        except OSError:
            raise AppError(
                "storage.writer_lock", "无法打开项目写入锁。", ExitCode.STORAGE
            ) from None
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
                code, message = "storage.writer_busy", "该项目已有写入进程。"
            else:
                code, message = "storage.writer_lock", "无法获取项目写入锁。"
            raise AppError(code, message, ExitCode.STORAGE) from None

    def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        # Closing an owned descriptor releases the OS lock, even after a crash.
        handle.close()
