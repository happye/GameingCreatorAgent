from __future__ import annotations

import ctypes
import gc
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import pytest

from gamingcreator.infrastructure.windows_job import WindowsProcessJob

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows process containment")


def kernel32() -> ctypes.WinDLL:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessHandleCount.restype = wintypes.BOOL
    return kernel


def start_suspended(code: str, *arguments: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-c", code, *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x00000004 | subprocess.CREATE_NO_WINDOW,
    )


def test_job_close_terminates_venv_launcher_interpreter_and_descendants(tmp_path: Path) -> None:
    ready = tmp_path / "ready.json"
    code = """
import json, os, pathlib, subprocess, sys, time
child = subprocess.Popen(
    [sys.executable, '-c', 'import os,time; print(os.getpid(),flush=True); time.sleep(60)'],
    stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
real_child = int(child.stdout.readline())
ready = pathlib.Path(sys.argv[1])
temporary = ready.with_suffix('.tmp')
temporary.write_text(json.dumps([os.getpid(), child.pid, real_child]))
temporary.replace(ready)
time.sleep(60)
"""
    kernel = kernel32()
    job = WindowsProcessJob()
    process = start_suspended(code, str(ready))
    handles: list[int] = []
    try:
        job.attach_and_resume(process.pid)
        deadline = time.monotonic() + 8
        while not ready.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.02)
        assert ready.exists(), "Contained interpreter did not start"
        pids = json.loads(ready.read_text())
        # The venv redirector must be exercised, not only a direct interpreter.
        assert process.pid != pids[0]
        assert pids[1] != pids[2]
        for pid in {process.pid, *pids}:
            handle = kernel.OpenProcess(0x00100000, False, pid)
            assert handle
            handles.append(handle)
            assert kernel.WaitForSingleObject(handle, 0) == 258
        job.close()
        job.close()
        process.wait(timeout=5)
        for handle in handles:
            assert kernel.WaitForSingleObject(handle, 5000) == 0
    finally:
        job.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for handle in handles:
            assert kernel.CloseHandle(handle)


def test_natural_completion_and_repeated_close_release_handles() -> None:
    kernel = kernel32()

    def count_handles() -> int:
        count = wintypes.DWORD()
        assert kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count))
        return count.value

    def run_once() -> None:
        job = WindowsProcessJob()
        process = start_suspended("pass")
        try:
            job.attach_and_resume(process.pid)
            assert process.wait(timeout=5) == 0
        finally:
            job.close()
            job.close()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)

    run_once()
    gc.collect()
    before = count_handles()
    for _ in range(12):
        run_once()
    gc.collect()
    assert count_handles() <= before + 1


@pytest.mark.parametrize("before_assignment", [False, True])
def test_attach_failure_terminates_suspended_process(
    monkeypatch: pytest.MonkeyPatch, before_assignment: bool
) -> None:
    job = WindowsProcessJob()
    process = start_suspended("import time; time.sleep(60)")

    def fail_resume(_pid: int) -> None:
        raise OSError(5, "Simulated resume failure")

    def fail_assignment(_job: int, _process: int) -> int:
        ctypes.set_last_error(5)
        return 0

    if before_assignment:
        monkeypatch.setattr(job._kernel, "AssignProcessToJobObject", fail_assignment)
    else:
        monkeypatch.setattr(job, "_resume_threads", fail_resume)
    try:
        with pytest.raises(OSError):
            job.attach_and_resume(process.pid)
        assert process.wait(timeout=5) != 0
        job.close()
        job.close()
    finally:
        job.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


@pytest.mark.parametrize("pid", [0, -1, True, 1.5, 0x100000000])
def test_job_rejects_invalid_identifiers_without_touching_other_processes(pid: int) -> None:
    job = WindowsProcessJob()
    try:
        with pytest.raises(ValueError):
            job.attach_and_resume(pid)
    finally:
        job.close()
