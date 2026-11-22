"""Process-owned read/write leases for one editing proxy source."""

import errno
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gamingcreator.domain.errors import AppError, ExitCode


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def is_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def checked_directory(directory: Path, *, create: bool = False) -> bool:
    """Walk the named ancestors without following directory links or junctions."""
    for entry in (*reversed(directory.parents), directory):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            if not create:
                return False
            entry.mkdir(exist_ok=True)
            info = entry.lstat()
        if is_reparse(info) or not stat.S_ISDIR(info.st_mode):
            raise OSError("Unsafe proxy directory")
    return True


def regular_single_link(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and not is_reparse(info) and info.st_nlink == 1


def _check_lock_file(path: Path, fd: int | None = None) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if fd is None:
            return
        raise
    if not regular_single_link(info):
        raise OSError("Unsafe proxy lock file")
    if fd is not None:
        opened = os.fstat(fd)
        if not regular_single_link(opened) or not os.path.samestat(info, opened):
            raise OSError("Proxy lock file was replaced")


def _lock_windows(fd: int, *, write: bool) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    lock = ctypes.WinDLL("kernel32", use_last_error=True).LockFileEx
    lock.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    ]
    lock.restype = wintypes.BOOL
    # FAIL_IMMEDIATELY for both modes; EXCLUSIVE_LOCK only for writes.
    if not lock(
        msvcrt.get_osfhandle(fd), 1 | (2 if write else 0), 0, 1, 0, ctypes.byref(Overlapped())
    ):
        error = ctypes.get_last_error()
        if error == 33:  # ERROR_LOCK_VIOLATION
            raise BlockingIOError(errno.EAGAIN, "Proxy lease is held")
        raise ctypes.WinError(error)


def _lock(fd: int, *, write: bool) -> None:
    if sys.platform == "win32":
        _lock_windows(fd, write=write)
    else:
        import fcntl

        fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)


@contextmanager
def proxy_lease(repository: Path, source_sha256: str, *, write: bool) -> Iterator[None]:
    if not is_sha256(source_sha256):
        raise ValueError("Invalid source SHA256.")
    path = repository.absolute() / ".cache/workspace/proxy-locks" / f"{source_sha256}.lock"
    fd = None
    try:
        try:
            checked_directory(path.parent, create=True)
            _check_lock_file(path)
            flags = (
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            )
            fd = os.open(path, flags, 0o600)
            checked_directory(path.parent)
            _check_lock_file(path, fd)
            _lock(fd, write=write)
            if not checked_directory(path.parent):
                raise OSError("Proxy lock directory was removed")
            _check_lock_file(path, fd)
        except BlockingIOError:
            raise AppError(
                "storage.proxy_busy", "此编辑代理正在播放、生成或回收。", ExitCode.STORAGE
            ) from None
        except OSError:
            raise AppError(
                "storage.proxy_lock", "无法安全打开编辑代理锁。", ExitCode.STORAGE
            ) from None
        yield
    finally:
        if fd is not None:
            # Closing the descriptor releases the OS lock, including on process exit.
            os.close(fd)
