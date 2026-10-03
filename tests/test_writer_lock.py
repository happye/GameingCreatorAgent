from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock

_CHILD = """
import sys
from pathlib import Path
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
lock = ProjectWriterLock(Path(sys.argv[1]))
try:
    lock.acquire()
except AppError as error:
    print(error.code, flush=True)
    sys.exit(int(error.exit_code))
print('acquired', flush=True)
try:
    sys.stdin.read(1)
finally:
    lock.close()
"""


def _child(project: Path) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONPYCACHEPREFIX"] = str(project / "pycache")
    return subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(project)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=environment,
    )


def _finish(process: subprocess.Popen[str], *, kill: bool = False) -> None:
    running = process.poll() is None
    if kill and running:
        process.kill()
    try:
        process.communicate(input="x" if running and not kill else None, timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=10)


def test_existing_lock_file_does_not_claim_ownership(tmp_path: Path) -> None:
    path = tmp_path / ".analysis-writer.lock"
    path.write_bytes(b"persistent content")
    lock = ProjectWriterLock(tmp_path)
    lock.acquire()
    lock.acquire()
    lock.close()
    lock.close()
    assert path.read_bytes() == b"persistent content"


def test_second_process_is_busy_until_owner_closes(tmp_path: Path) -> None:
    owner = _child(tmp_path)
    try:
        assert owner.stdout is not None
        assert owner.stdout.readline().strip() == "acquired"
        contender = _child(tmp_path)
        try:
            assert contender.stdout is not None
            assert contender.stdout.readline().strip() == "storage.writer_busy"
            assert contender.wait(timeout=10) == ExitCode.STORAGE
        finally:
            _finish(contender, kill=contender.poll() is None)
    finally:
        _finish(owner)
    lock = ProjectWriterLock(tmp_path)
    lock.acquire()
    lock.close()
    assert (tmp_path / ".analysis-writer.lock").exists()


def test_forced_owner_exit_releases_lock_without_deleting_file(tmp_path: Path) -> None:
    owner = _child(tmp_path)
    try:
        assert owner.stdout is not None
        assert owner.stdout.readline().strip() == "acquired"
    finally:
        _finish(owner, kill=True)
    lock = ProjectWriterLock(tmp_path)
    lock.acquire()
    lock.close()
    assert (tmp_path / ".analysis-writer.lock").exists()


def test_missing_project_is_a_startup_error(tmp_path: Path) -> None:
    lock = ProjectWriterLock(tmp_path / "missing")
    with pytest.raises(AppError) as caught:
        lock.acquire()
    assert caught.value.code == "storage.writer_lock"
    assert caught.value.exit_code == ExitCode.STORAGE
    lock.close()
