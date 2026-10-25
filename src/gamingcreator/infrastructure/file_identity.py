"""File-system change time of an open file, for caches keyed on file identity (TD008).

On Windows os.stat's st_ctime is the creation time, so a same-size rewrite whose
modification time is restored keeps every stat field. NTFS also records a ChangeTime
that the file system itself advances on any data or metadata change, including the
call that restores the modification time; only a caller deliberately setting
ChangeTime through the native API can keep it. Elsewhere st_ctime already is the
inode change time.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from functools import cache

_FILE_BASIC_INFO = 0


def change_time_ns(fd: int) -> int:
    """Change time of the file open as fd, in the platform's own nanosecond units."""
    if sys.platform != "win32":
        return os.fstat(fd).st_ctime_ns
    return _windows_change_time()(fd)


@cache
def _windows_change_time() -> Callable[[int], int]:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class _BasicInfo(ctypes.Structure):
        _fields_ = [
            ("CreationTime", ctypes.c_longlong),
            ("LastAccessTime", ctypes.c_longlong),
            ("LastWriteTime", ctypes.c_longlong),
            ("ChangeTime", ctypes.c_longlong),
            ("FileAttributes", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    query = kernel32.GetFileInformationByHandleEx
    query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    query.restype = wintypes.BOOL

    def read(fd: int) -> int:
        info = _BasicInfo()
        handle = msvcrt.get_osfhandle(fd)
        if not query(handle, _FILE_BASIC_INFO, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        # FILETIME ticks are 100 ns.
        return int(info.ChangeTime) * 100

    return read
