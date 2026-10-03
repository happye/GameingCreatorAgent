import asyncio
import ctypes
import sys
from pathlib import Path

import pytest

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.media_process import run_media_process


def process_kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel


def process_is_alive(pid: int) -> bool:
    if sys.platform != "win32":
        return Path(f"/proc/{pid}").exists()
    kernel = process_kernel()
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258
    finally:
        kernel.CloseHandle(handle)


def test_process_cancellation_before_start_has_no_side_effects(tmp_path: Path) -> None:
    context = CancellationContext("run", 5)
    context.cancelled.set()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_media_process([sys.executable, "-c", "raise RuntimeError()"], context))


def test_process_cancellation_reaps_started_child(tmp_path: Path) -> None:
    pid_path = tmp_path / "中文 pid.txt"
    code = "import os,sys,time; from pathlib import Path; Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)"

    kernel = process_kernel() if sys.platform == "win32" else None
    original_handle = None

    async def scenario() -> None:
        nonlocal original_handle
        context = CancellationContext("run", 5)
        task = asyncio.create_task(
            run_media_process([sys.executable, "-I", "-B", "-c", code, str(pid_path)], context)
        )
        for _ in range(100):
            if pid_path.exists():
                break
            await asyncio.sleep(0.02)
        assert pid_path.exists()
        if kernel is not None:
            # Pin the interpreter itself; the venv launcher has a different PID.
            original_handle = kernel.OpenProcess(0x100000, False, int(pid_path.read_text()))
            assert original_handle
        context.cancelled.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(scenario())
        if kernel is not None:
            # Job termination is asynchronous; pipe EOF can precede object signaling.
            assert kernel.WaitForSingleObject(original_handle, 5000) == 0
        else:
            assert not process_is_alive(int(pid_path.read_text()))
    finally:
        if kernel is not None and original_handle:
            kernel.CloseHandle(original_handle)


def test_process_timeout_and_output_limit_are_bounded_and_sanitized() -> None:
    with pytest.raises(AppError, match="超时") as error:
        asyncio.run(
            run_media_process(
                [sys.executable, "-I", "-B", "-c", "import time;time.sleep(30)"],
                CancellationContext("run", 0.1),
            )
        )
    assert error.value.code == "media.timeout"
    with pytest.raises(AppError) as error:
        asyncio.run(
            run_media_process(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    "import sys;sys.stderr.write('private-data'*100000)",
                ],
                CancellationContext("run", 5),
                max_stderr_bytes=1024,
            )
        )
    assert error.value.code == "media.output_limit" and "private-data" not in str(error.value)


def test_process_reads_both_pipes_without_deadlock() -> None:
    result = asyncio.run(
        run_media_process(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                "import sys;sys.stdout.write('a'*100000);sys.stderr.write('b'*100000)",
            ],
            CancellationContext("run", 5),
        )
    )
    assert len(result.stdout) == len(result.stderr) == 100000


def test_continuous_excess_output_is_stopped_without_waiting_for_eof() -> None:
    code = "import sys\nwhile True:\n sys.stderr.write('x'*65536);sys.stderr.flush()"
    with pytest.raises(AppError) as error:
        asyncio.run(
            run_media_process(
                [sys.executable, "-I", "-B", "-c", code],
                CancellationContext("run", 5),
                max_stderr_bytes=1024,
            )
        )
    assert error.value.code == "media.output_limit"
