"""Contain a process created with CREATE_SUSPENDED before any user code runs.

The caller owns process creation and reaping, and must close the job in a finally
block. An unnamed, non-inheritable job prevents descendants from retaining its
last handle. Windows child processes inherit membership, without breakaway flags.
"""

from __future__ import annotations

import ctypes
import errno
import os
from ctypes import wintypes
from typing import cast

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_SYNCHRONIZE = 0x00100000
_THREAD_SUSPEND_RESUME = 0x0002
_TH32CS_SNAPTHREAD = 0x00000004
_ERROR_NO_MORE_FILES = 18
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_DWORD_MAX = 0xFFFFFFFF


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _ThreadEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


def _api_error(operation: str) -> OSError:
    # Avoid FormatMessage/WinError: system messages can include private context.
    return OSError(ctypes.get_last_error(), f"Windows {operation} failed")


def _kernel32() -> ctypes.WinDLL:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    kernel.Thread32First.restype = wintypes.BOOL
    kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    kernel.Thread32Next.restype = wintypes.BOOL
    kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenThread.restype = wintypes.HANDLE
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


class WindowsProcessJob:
    """Own one process tree; attach only a newly CREATE_SUSPENDED process.

    close() is idempotent and requests termination of the entire tree. The caller
    must then wait for its process. This object is confined to its creating thread.
    If OpenProcess itself fails, the caller's existing process handle is required
    to terminate and reap its suspended process.
    """

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError(errno.ENOTSUP, "Windows process containment is unavailable")
        self._kernel = _kernel32()
        self._handle: int | None = None
        self._attached = False
        handle = self._kernel.CreateJobObjectW(None, None)
        if not handle:
            raise _api_error("CreateJobObjectW")
        self._handle = cast(int, handle)
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._kernel.SetInformationJobObject(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = _api_error("SetInformationJobObject")
            self.close()
            raise error

    def attach_and_resume(self, pid: int) -> None:
        """Assign the suspended process first, then resume its initial thread."""
        if type(pid) is not int or not 0 < pid <= _DWORD_MAX:
            raise ValueError("A positive Windows process identifier is required")
        if self._handle is None or self._attached:
            raise OSError(errno.EINVAL, "Windows job is closed or already attached")
        process = self._kernel.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE | _SYNCHRONIZE, False, pid
        )
        if not process:
            raise _api_error("OpenProcess")
        try:
            if not self._kernel.AssignProcessToJobObject(self._handle, process):
                raise _api_error("AssignProcessToJobObject")
            self._attached = True
            self._resume_threads(pid)
        except BaseException:
            # Fail closed before releasing the process handle. The process has
            # not intentionally run outside the job, so no descendants can escape.
            self._kernel.TerminateProcess(process, 1)
            self.close()
            if self._kernel.WaitForSingleObject(process, 5000) != 0:
                raise OSError(errno.EIO, "Windows suspended process cleanup failed") from None
            raise
        finally:
            self._close_handle(cast(int, process))

    def _resume_threads(self, pid: int) -> None:
        snapshot = self._kernel.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
        if snapshot == _INVALID_HANDLE_VALUE or not snapshot:
            raise _api_error("CreateToolhelp32Snapshot")
        thread_ids: list[int] = []
        try:
            entry = _ThreadEntry32()
            entry.dwSize = ctypes.sizeof(entry)
            if not self._kernel.Thread32First(snapshot, ctypes.byref(entry)):
                raise _api_error("Thread32First")
            while True:
                if entry.th32OwnerProcessID == pid:
                    thread_ids.append(entry.th32ThreadID)
                entry.dwSize = ctypes.sizeof(entry)
                if not self._kernel.Thread32Next(snapshot, ctypes.byref(entry)):
                    if ctypes.get_last_error() != _ERROR_NO_MORE_FILES:
                        raise _api_error("Thread32Next")
                    break
        finally:
            self._close_handle(cast(int, snapshot))
        if len(thread_ids) != 1:
            raise OSError(errno.EINVAL, "Expected one newly suspended process thread")
        thread = self._kernel.OpenThread(_THREAD_SUSPEND_RESUME, False, thread_ids[0])
        if not thread:
            raise _api_error("OpenThread")
        try:
            previous_count = self._kernel.ResumeThread(thread)
            if previous_count == _DWORD_MAX:
                raise _api_error("ResumeThread")
            if previous_count != 1:
                raise OSError(errno.EINVAL, "Expected one initial process suspension")
        finally:
            self._close_handle(cast(int, thread))

    def _close_handle(self, handle: int) -> None:
        if not self._kernel.CloseHandle(handle):
            raise _api_error("CloseHandle")

    def close(self) -> None:
        """Close the last non-inheritable job handle, terminating its process tree."""
        if self._handle is not None:
            self._close_handle(self._handle)
            self._handle = None
