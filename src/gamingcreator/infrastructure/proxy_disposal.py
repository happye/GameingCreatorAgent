"""Remove only the confirmed proxy entries, without following a changed directory path."""

import os
import stat
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from gamingcreator.infrastructure.proxy_lease import is_reparse, regular_single_link


def proxy_stat_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _verify(info: os.stat_result, expected: os.stat_result, *, directory: bool) -> None:
    safe = (
        stat.S_ISDIR(info.st_mode) and not is_reparse(info)
        if directory
        else regular_single_link(info)
    )
    current_key = proxy_stat_identity(info)
    expected_key = proxy_stat_identity(expected)
    if sys.platform == "win32":
        # Windows path and descriptor stat can expose different ctime semantics.
        # Device, inode, type, links, size and write time still bind the open handle.
        current_key, expected_key = current_key[:-1], expected_key[:-1]
    if not safe or not info.st_ino or current_key != expected_key:
        raise OSError("Proxy record identity changed")


def _unlink_windows(
    directory: Path,
    directory_stat: os.stat_result,
    files: dict[str, os.stat_result],
    names: tuple[str, ...],
) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    open_file = kernel.CreateFileW
    open_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    open_file.restype = wintypes.HANDLE
    close_handle = kernel.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    mark_delete = kernel.SetFileInformationByHandle
    mark_delete.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    mark_delete.restype = wintypes.BOOL

    @contextmanager
    def opened(
        path: Path, expected: os.stat_result, *, is_directory: bool = False
    ) -> Iterator[int]:
        # DELETE | FILE_READ_ATTRIBUTES, OPEN_EXISTING, OPEN_REPARSE_POINT | BACKUP_SEMANTICS.
        raw = open_file(str(path), 0x10080, 0, None, 3, 0x02200000, None)
        if raw == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            fd = msvcrt.open_osfhandle(raw, os.O_RDONLY | os.O_BINARY)
        except OSError:
            close_handle(raw)
            raise
        try:
            _verify(os.fstat(fd), expected, directory=is_directory)
            yield raw
        finally:
            os.close(fd)  # The CRT descriptor owns the Win32 handle.

    def delete(handle: int) -> None:
        flag = ctypes.c_ubyte(1)  # FILE_DISPOSITION_INFO contains one BOOLEAN.
        if not mark_delete(handle, 4, ctypes.byref(flag), ctypes.sizeof(flag)):
            raise ctypes.WinError(ctypes.get_last_error())

    if {path.name for path in directory.iterdir()} != files.keys():
        raise OSError("Proxy record entries changed")
    with opened(directory, directory_stat, is_directory=True) as handle:
        # Verify every expected file before the first deletion. The open handles deny new writers.
        with ExitStack() as stack:
            # ExitStack closes last-in first; close the marked proxy before the receipt.
            children = [
                stack.enter_context(opened(directory / name, files[name]))
                for name in reversed(names)
            ]
            for child in reversed(children):
                delete(child)
        delete(handle)  # The OS refuses disposition if the directory still contains any entries.


def _unlink_posix(
    directory: Path,
    directory_stat: os.stat_result,
    files: dict[str, os.stat_result],
    names: tuple[str, ...],
) -> None:
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    if not (directory_flag and nofollow_flag):
        raise OSError("No-follow directory handles are unavailable")
    flags = os.O_RDONLY | directory_flag | nofollow_flag
    with ExitStack() as stack:
        parent = os.open(directory.anchor, flags)
        stack.callback(os.close, parent)
        for part in directory.parts[1:-1]:
            parent = os.open(part, flags, dir_fd=parent)
            stack.callback(os.close, parent)
        child = os.open(directory.name, flags, dir_fd=parent)
        stack.callback(os.close, child)
        _verify(os.fstat(child), directory_stat, directory=True)
        if set(os.listdir(child)) != files.keys():
            raise OSError("Proxy record entries changed")
        for name in names:
            _verify(
                os.stat(name, dir_fd=child, follow_symlinks=False), files[name], directory=False
            )
        for name in names:
            _verify(
                os.stat(name, dir_fd=child, follow_symlinks=False), files[name], directory=False
            )
            os.unlink(name, dir_fd=child)
        current = os.stat(directory.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(current.st_mode) or not os.path.samestat(current, directory_stat):
            raise OSError("Proxy record directory changed")
        os.rmdir(directory.name, dir_fd=parent)


def dispose_proxy_record(
    directory: Path,
    directory_stat: os.stat_result,
    files: dict[str, os.stat_result],
    names: tuple[str, ...],
) -> None:
    if sys.platform == "win32":
        _unlink_windows(directory, directory_stat, files, names)
    else:
        _unlink_posix(directory, directory_stat, files, names)
