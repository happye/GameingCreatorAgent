"""Deterministic Windows cross-process sharing contention, without rerunning steps."""

import hashlib
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui.benchmark_workflow import BenchmarkWorkflows, _read_status, _status_io, _write

HOLDER = r"""
import ctypes
import sys
from ctypes import wintypes
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                              wintypes.HANDLE]
kernel.CreateFileW.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.CloseHandle.restype = wintypes.BOOL
handle = kernel.CreateFileW(sys.argv[1], 0x80000000, int(sys.argv[2]), None, 3, 0, None)
if handle == wintypes.HANDLE(-1).value:
    raise ctypes.WinError(ctypes.get_last_error())
print('ready', flush=True)
try:
    sys.stdin.readline()
finally:
    kernel.CloseHandle(handle)
"""


@contextmanager
def held(path, share, release_after=None):
    process = subprocess.Popen(
        [sys.executable, "-B", "-c", HOLDER, str(path), str(share)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    timer = None
    try:
        assert process.stdout.readline().strip() == "ready", process.stderr.read()
        if release_after is not None:
            timer = threading.Timer(release_after, lambda: process.communicate("release\n"))
            timer.start()
        yield
    finally:
        if timer is not None:
            timer.join(timeout=5)
        if process.poll() is None:
            process.communicate("release\n", timeout=5)
        assert process.returncode == 0


@pytest.fixture
def saved_status(tmp_path):
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "contention"})["id"]
    attempt = "000001-" + "a" * 32
    parent = manager.directory(identifier) / attempt
    parent.mkdir()
    row = dict(
        attemptId=attempt,
        action="ranking",
        startedAt="fixture",
        status="running",
        exitCode=None,
        files={},
        error=None,
        project=None,
        qualityGate=None,
        elapsedMs=None,
        dependencies={},
    )
    path = parent / "status.json"
    _write(path, row)
    return manager, identifier, row, path


@pytest.mark.skipif(os.name != "nt", reason="Real Windows sharing semantics")
def test_terminal_status_recovers_after_other_process_releases(saved_status, monkeypatch):
    manager, identifier, row, path = saved_status
    output = manager._output(identifier, row)
    output.mkdir()
    report = output / "benchmark-report.json"
    data = b'{"saved":true}'
    report.write_bytes(data)
    executions = []

    def execute(*args):
        executions.append(args)
        return 0, None

    monkeypatch.setattr(manager, "_execute", execute)
    lock = ProjectWriterLock(manager.directory(identifier))
    lock.acquire()
    before = path.read_bytes()
    with held(path, 1, release_after=0.2):
        # FILE_SHARE_READ permits readers but prevents replacing this status file.
        assert path.read_bytes() == before
        manager._run(identifier, row, {}, {}, lock)
    restored = manager._attempts(identifier)[0]
    assert restored["status"] == "finished"
    assert restored["files"] == {"benchmark-report.json": hashlib.sha256(data).hexdigest()}
    assert len(executions) == 1
    assert report.read_bytes() == data
    assert not list(path.parent.glob("*.tmp"))
    # Terminal completion still releases the original OS writer lock.
    next_lock = ProjectWriterLock(manager.directory(identifier))
    try:
        next_lock.acquire()
    finally:
        next_lock.close()


@pytest.mark.skipif(os.name != "nt", reason="Real Windows sharing semantics")
def test_replace_timeout_keeps_original_data_output_and_other_temporary(saved_status):
    manager, identifier, row, path = saved_status
    original = path.read_bytes()
    other = path.with_name("status.json.other-writer.tmp")
    other.write_bytes(b"another writer")
    output = manager._output(identifier, row)
    output.mkdir()
    (output / "benchmark-report.json").write_bytes(b"saved output")
    with held(path, 1):
        start = time.monotonic()
        with pytest.raises(OSError) as raised:
            _write(path, {**row, "status": "finished"})
        elapsed = time.monotonic() - start
        assert raised.value.winerror in {5, 32, 33}
        assert 0.9 <= elapsed < 2
        assert path.read_bytes() == original
    assert path.read_bytes() == original
    assert list(path.parent.glob("*.tmp")) == [other]
    assert other.read_bytes() == b"another writer"
    assert (output / "benchmark-report.json").read_bytes() == b"saved output"


@pytest.mark.skipif(os.name != "nt", reason="Real Windows sharing semantics")
@pytest.mark.parametrize("release", [True, False])
def test_status_read_waits_only_until_release_or_deadline(saved_status, release):
    manager, identifier, row, path = saved_status
    original = path.read_bytes()
    with held(path, 0, release_after=0.2 if release else None):
        start = time.monotonic()
        if release:
            assert manager._attempts(identifier) == [row]
        else:
            with pytest.raises(OSError) as raised:
                manager._attempts(identifier)
            assert getattr(raised.value, "winerror", None) in {None, 5, 32, 33}
            assert raised.value.errno == 13
        elapsed = time.monotonic() - start
        assert (0.15 if release else 0.9) <= elapsed < 2
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "error",
    [OSError(2, "missing"), PermissionError(13, "not a sharing error"), ValueError("invalid")],
)
def test_non_sharing_errors_fail_immediately(error, monkeypatch):
    attempts = []
    sleeps = []
    monkeypatch.setattr("gamingcreator.ui.benchmark_workflow.time.sleep", sleeps.append)

    def fail():
        attempts.append(True)
        raise error

    with pytest.raises(type(error)) as raised:
        _status_io(fail)
    assert raised.value is error
    assert attempts == [True]
    assert sleeps == []


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_all_supported_windows_sharing_codes_retry(winerror, monkeypatch):
    attempts = []
    error = OSError("sharing")
    error.winerror = winerror
    monkeypatch.setattr("gamingcreator.ui.benchmark_workflow.time.sleep", lambda _: None)

    def eventually():
        attempts.append(True)
        if len(attempts) == 1:
            raise error
        return b"original"

    assert _status_io(eventually) == b"original"
    assert len(attempts) == 2


@pytest.mark.skipif(os.name != "nt", reason="Windows CRT EACCES mapping")
def test_permanent_read_access_denied_remains_bounded_and_raises_original(
    saved_status, monkeypatch
):
    manager, identifier, _, path = saved_status
    original = path.read_bytes()
    error = PermissionError(13, "permanent ACL denial")
    attempts = []

    def denied(_):
        attempts.append(True)
        raise error

    monkeypatch.setattr("gamingcreator.ui.benchmark_workflow.read_bounded", denied)
    start = time.monotonic()
    with pytest.raises(PermissionError) as raised:
        manager._attempts(identifier)
    assert raised.value is error
    assert 0.9 <= time.monotonic() - start < 2
    assert len(attempts) > 1
    assert path.read_bytes() == original


def test_cleanup_failure_preserves_original_replace_error(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    path.write_bytes(b"original")
    failure = OSError(2, "replace failed")

    def fail_replace(*_):
        raise failure

    def fail_cleanup(*_, **__):
        raise PermissionError(13, "temporary busy")

    monkeypatch.setattr(Path, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(OSError) as raised:
        _write(path, {"status": "finished"})
    assert raised.value is failure
    assert path.read_bytes() == b"original"


def test_read_revalidates_path_after_wait_and_propagates_link_error(tmp_path, monkeypatch):
    from gamingcreator.domain.errors import AppError, ExitCode

    path = tmp_path / "status.json"
    checks = []
    sharing = OSError("sharing")
    sharing.winerror = 32
    link_error = AppError("input.benchmark_workflow", "changed link", ExitCode.INPUT)

    def check(candidate):
        checks.append(candidate)
        if len(checks) > 1:
            raise link_error
        return candidate

    def busy(_):
        raise sharing

    monkeypatch.setattr("gamingcreator.ui.benchmark_workflow._plain", check)
    monkeypatch.setattr("gamingcreator.ui.benchmark_workflow.read_bounded", busy)
    monkeypatch.setattr("gamingcreator.ui.benchmark_workflow.time.sleep", lambda _: None)
    with pytest.raises(AppError) as raised:
        _read_status(path)
    assert raised.value is link_error
    assert checks == [path, path]
