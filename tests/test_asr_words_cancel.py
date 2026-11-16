"""E12：取消和超时只停这次逐词任务，保留已有结果，不会自动重试，也不会杀掉别人的进程。"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import sys
from pathlib import Path

import pytest
from test_asr_words_cli import MODEL, FakeWords, _seed

from gamingcreator.application.providers import (
    CancellationContext,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.asr_runtime import NATIVE_FILES
from gamingcreator.infrastructure.asr_words import transcribe_project_words
from gamingcreator.infrastructure.media_process import run_media_process


def _install_complete_runtime(repository: Path) -> None:
    _touch_interpreter(repository)
    pin_path = repository / "docs" / "references" / "asr-native-toolchain.json"
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    native = repository / ".tools" / "native" / "msvc" / pin["version"]
    native.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in sorted(NATIVE_FILES):
        path = native / name
        if not path.exists():
            path.write_bytes(name.encode())
        payload = path.read_bytes()
        files[name] = hashlib.sha256(payload).hexdigest()
    pin["files"] = files
    pin_path.write_text(json.dumps(pin), encoding="utf-8")


def _touch_interpreter(repository: Path) -> None:
    interpreter = repository / ".venv" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    if not interpreter.exists():
        interpreter.touch()


def _asr_words_root(project: Path) -> Path:
    return project / "runs" / "run-1" / "asr-words"


def _staging_leftovers(project: Path) -> list[Path]:
    root = _asr_words_root(project)
    if not root.exists():
        return []
    return [
        path
        for path in root.rglob("*")
        if path.name.startswith(".tmp-") or path.name.endswith(".tmp")
    ]


def test_cancel_before_start_keeps_existing_result_and_does_not_retry(tmp_path):
    repository, project, _bundle = _seed(tmp_path)
    summary = asyncio.run(
        transcribe_project_words(project, "run-1", MODEL, repository, provider=FakeWords())
    )
    before = (summary.result_directory / "words.json").read_bytes()
    provider = FakeWords()
    context = CancellationContext("run-1", 5)
    context.cancelled.set()
    with pytest.raises(AppError) as error:
        asyncio.run(
            transcribe_project_words(
                project, "run-1", MODEL, repository, provider=provider, context=context
            )
        )
    assert error.value.code == "asr.cancelled"
    assert error.value.message == "逐词识别已取消。"
    assert error.value.exit_code == ExitCode.CANCELLED
    assert provider.calls == 0
    assert (summary.result_directory / "words.json").read_bytes() == before
    assert _staging_leftovers(project) == []


def test_timeout_and_cancel_reap_only_this_worker_and_keep_published_sidecar(tmp_path, monkeypatch):
    repository, project, _bundle = _seed(tmp_path)
    _install_complete_runtime(repository)
    published = asyncio.run(
        transcribe_project_words(project, "run-1", MODEL, repository, provider=FakeWords())
    )
    before = (published.result_directory / "words.json").read_bytes()
    _select_new_revision(monkeypatch)

    code = (
        "import os,sys,time;from pathlib import Path;"
        "Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(30)"
    )

    async def controlled(arguments, context, **kwargs):
        path = Path(str(context.run_id) + "-pid")
        # replaced below
        return await run_media_process([sys.executable, "-I", "-B", "-c", code, str(path)], context)

    # real implementation is assigned in the test body after pid path is known
    import gamingcreator.infrastructure.local_asr as local_asr

    pid_path = tmp_path / "word-worker.pid"

    async def waiting_worker(arguments, context, **kwargs):
        return await run_media_process(
            [sys.executable, "-I", "-B", "-c", code, str(pid_path)], context
        )

    monkeypatch.setattr(local_asr, "run_media_process", waiting_worker)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None
    handle = None
    if kernel is not None:
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]

    async def cancel_scenario():
        nonlocal handle
        context = CancellationContext("run-1", 5)
        task = asyncio.create_task(
            transcribe_project_words(project, "run-1", MODEL, repository, context=context)
        )
        for _ in range(200):
            if pid_path.exists() or task.done():
                break
            await asyncio.sleep(0.02)
        if not pid_path.exists():
            with pytest.raises(AppError) as started:
                await task
            raise AssertionError(started.value.code + " " + started.value.message)
        if kernel is not None:
            handle = kernel.OpenProcess(0x100000, False, int(pid_path.read_text()))
            assert handle
        context.cancelled.set()
        with pytest.raises(AppError) as error:
            await task
        assert error.value.code == "asr.cancelled"
        assert error.value.message == "逐词识别已取消。"

    try:
        asyncio.run(cancel_scenario())
        if kernel is not None:
            assert kernel.WaitForSingleObject(handle, 5000) == 0
        else:
            assert not Path(f"/proc/{pid_path.read_text()}").exists()
    finally:
        if kernel is not None and handle:
            kernel.CloseHandle(handle)

    assert (published.result_directory / "words.json").read_bytes() == before
    assert _staging_leftovers(project) == []

    # Timeout on a fresh sleeping worker must not rewrite or retry automatically.
    timeout_pid = tmp_path / "word-timeout.pid"
    calls = {"count": 0}

    async def timeout_worker(arguments, context, **kwargs):
        calls["count"] += 1
        return await run_media_process(
            [sys.executable, "-I", "-B", "-c", code, str(timeout_pid)], context
        )

    monkeypatch.setattr(local_asr, "run_media_process", timeout_worker)
    with pytest.raises(AppError) as timeout_error:
        asyncio.run(
            transcribe_project_words(
                project,
                "run-1",
                MODEL,
                repository,
                context=CancellationContext("run-1", 0.2),
            )
        )
    assert timeout_error.value.code == "asr.timeout"
    assert timeout_error.value.message == "逐词识别超时。"
    assert calls["count"] == 1
    assert (published.result_directory / "words.json").read_bytes() == before
    assert _staging_leftovers(project) == []


def test_cancelling_one_word_task_does_not_stop_another(tmp_path, monkeypatch):
    repo_a, project_a, _ = _seed(tmp_path / "a")
    repo_b, project_b, _ = _seed(tmp_path / "b")
    _install_complete_runtime(repo_a)
    _install_complete_runtime(repo_b)
    kept_a = asyncio.run(
        transcribe_project_words(project_a, "run-1", MODEL, repo_a, provider=FakeWords())
    )
    kept_b = asyncio.run(
        transcribe_project_words(project_b, "run-1", MODEL, repo_b, provider=FakeWords())
    )
    before_a = (kept_a.result_directory / "words.json").read_bytes()
    before_b = (kept_b.result_directory / "words.json").read_bytes()
    _select_new_revision(monkeypatch)

    import gamingcreator.infrastructure.local_asr as local_asr

    code = (
        "import os,sys,time;from pathlib import Path;"
        "Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(30)"
    )
    pids: dict[int, Path] = {}

    async def controlled(arguments, context, **kwargs):
        path = pids.setdefault(id(context), tmp_path / f"{id(context)}.pid")
        return await run_media_process([sys.executable, "-I", "-B", "-c", code, str(path)], context)

    monkeypatch.setattr(local_asr, "run_media_process", controlled)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None
    handle_a = handle_b = None
    if kernel is not None:
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]

    async def scenario():
        nonlocal handle_a, handle_b
        context_a = CancellationContext("run-1", 8)
        context_b = CancellationContext("run-1", 8)
        task_a = asyncio.create_task(
            transcribe_project_words(project_a, "run-1", MODEL, repo_a, context=context_a)
        )
        task_b = asyncio.create_task(
            transcribe_project_words(project_b, "run-1", MODEL, repo_b, context=context_b)
        )
        for _ in range(200):
            if (
                (len(pids) == 2 and all(path.exists() for path in pids.values()))
                or task_a.done()
                or task_b.done()
            ):
                break
            await asyncio.sleep(0.02)
        if not (len(pids) == 2 and all(path.exists() for path in pids.values())):
            codes = []
            if task_a.done():
                with pytest.raises(AppError) as one:
                    await task_a
                codes.append(one.value.code + " " + one.value.message)
            if task_b.done():
                with pytest.raises(AppError) as two:
                    await task_b
                codes.append(two.value.code + " " + two.value.message)
            raise AssertionError(" ".join(codes) or "并行的词级识别进程没有都启动。")
        path_a = pids[id(context_a)]
        path_b = pids[id(context_b)]
        if kernel is not None:
            handle_a = kernel.OpenProcess(0x100000, False, int(path_a.read_text()))
            handle_b = kernel.OpenProcess(0x100000, False, int(path_b.read_text()))
            assert handle_a and handle_b
        context_a.cancelled.set()
        with pytest.raises(AppError) as cancelled:
            await task_a
        assert cancelled.value.code == "asr.cancelled"
        if kernel is not None:
            assert kernel.WaitForSingleObject(handle_a, 5000) == 0
            assert kernel.WaitForSingleObject(handle_b, 0) == 0x102
        else:
            assert not Path(f"/proc/{path_a.read_text()}").exists()
            assert Path(f"/proc/{path_b.read_text()}").exists()
        context_b.cancelled.set()
        with pytest.raises(AppError) as other:
            await task_b
        assert other.value.code == "asr.cancelled"
        if kernel is not None:
            assert kernel.WaitForSingleObject(handle_b, 5000) == 0

    try:
        asyncio.run(scenario())
    finally:
        if kernel is not None:
            if handle_a:
                kernel.CloseHandle(handle_a)
            if handle_b:
                kernel.CloseHandle(handle_b)

    assert (kept_a.result_directory / "words.json").read_bytes() == before_a
    assert (kept_b.result_directory / "words.json").read_bytes() == before_b
    assert _staging_leftovers(project_a) == []
    assert _staging_leftovers(project_b) == []


def _select_new_revision(monkeypatch):
    from dataclasses import replace

    from gamingcreator.infrastructure.asr_models import select_installed_asr_settings

    def select(repository, model):
        return replace(select_installed_asr_settings(repository, model), model_revision="0" * 40)

    # Preserve old results while exercising a worker with a different identity.
    monkeypatch.setattr(
        "gamingcreator.infrastructure.asr_words.select_installed_asr_settings", select
    )


def test_cancel_after_staging_write_does_not_publish(tmp_path, monkeypatch):
    import gamingcreator.infrastructure.asr_words_sidecar as sidecar

    repository, project, _ = _seed(tmp_path)
    context = CancellationContext("run-1", 5)
    original = sidecar._write_published_file

    def write_then_cancel(path, payload):
        original(path, payload)
        if path.name == "receipt.json":
            context.cancelled.set()

    monkeypatch.setattr(sidecar, "_write_published_file", write_then_cancel)
    with pytest.raises(AppError) as error:
        asyncio.run(
            transcribe_project_words(
                project, "run-1", MODEL, repository, provider=FakeWords(), context=context
            )
        )
    assert error.value.code == "asr.cancelled"
    assert not list(_asr_words_root(project).glob("*/words.json"))
    assert _staging_leftovers(project) == []
