import asyncio
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.windows_job import WindowsProcessJob


@dataclass(frozen=True, slots=True)
class MediaOutputLimit:
    """A new, privately owned output, bounded independently of process timeout."""

    path: Path
    max_bytes: int
    minimum_free_bytes: int = 2 * 1024**3
    directory_max_bytes: int = 4 * 1024**3

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, Path)
            or type(self.max_bytes) is not int
            or self.max_bytes <= 0
        ):
            raise ValueError("Output budget needs a path and positive integer bytes.")
        if type(self.minimum_free_bytes) is not int or self.minimum_free_bytes < 0:
            raise ValueError("Disk reserve must be nonnegative integer bytes.")
        if type(self.directory_max_bytes) is not int or self.directory_max_bytes <= 0:
            raise ValueError("Scratch-directory budget must be positive integer bytes.")

    def check(self) -> str | None:
        if any(is_link(p) for p in (self.path, *self.path.parents)):
            raise ValueError("Budgeted media output cannot traverse links.")
        if self.path.exists() and self.path.stat().st_size >= self.max_bytes:
            return "media.file_limit"
        total = sum(
            p.stat().st_size for p in self.path.parent.iterdir() if not is_link(p) and p.is_file()
        )
        if total >= self.directory_max_bytes:
            return "media.scratch_limit"
        if shutil.disk_usage(self.path.parent).free < self.minimum_free_bytes:
            return "media.disk_space"
        return None


def _output_error(code: str) -> AppError:
    return AppError(
        code,
        "临时媒体达到容量上限，已停止并回收；请缩短镜头或降低输出尺寸。"
        if code in ("media.file_limit", "media.scratch_limit")
        else "可用磁盘空间不足，已停止媒体处理；请先释放空间。",
        ExitCode.ENVIRONMENT,
    )


@dataclass(frozen=True, slots=True)
class ProcessOutput:
    stdout: bytes
    stderr: bytes


async def _read_bounded(reader: asyncio.StreamReader, limit: int, overflow: asyncio.Event) -> bytes:
    chunks = bytearray()
    while chunk := await reader.read(65536):
        if len(chunks) + len(chunk) > limit:
            overflow.set()
        elif not overflow.is_set():
            chunks.extend(chunk)
    return bytes(chunks)


async def _read_consumed_lines(
    reader: asyncio.StreamReader,
    limit: int,
    overflow: asyncio.Event,
    consumer: Callable[[str], bool],
) -> bytes:
    """Consume known records incrementally; bound each line and remaining diagnostics."""
    pending, diagnostics = bytearray(), bytearray()

    def consume(line: bytes) -> None:
        if len(line) > 65536:
            overflow.set()
        elif not overflow.is_set() and not consumer(line.decode("utf-8", "replace")):
            if len(diagnostics) + len(line) > limit:
                overflow.set()
            else:
                diagnostics.extend(line)

    while chunk := await reader.read(65536):
        pending.extend(chunk)
        while (boundary := pending.find(b"\n")) >= 0:
            line = bytes(pending[: boundary + 1])
            del pending[: boundary + 1]
            consume(line)
        if len(pending) > 65536:
            overflow.set()
            pending.clear()
    if pending:
        consume(bytes(pending))
    return bytes(diagnostics)


async def run_media_process(
    arguments: list[str],
    context: CancellationContext,
    max_stdout_bytes: int = 4 * 1024 * 1024,
    max_stderr_bytes: int = 16 * 1024 * 1024,
    *,
    stderr_line_consumer: Callable[[str], bool] | None = None,
    stdout_line_consumer: Callable[[str], bool] | None = None,
    output_limit: MediaOutputLimit | None = None,
) -> ProcessOutput:
    context.check_cancelled()
    if output_limit is not None:
        if output_limit.path.exists() or not output_limit.path.parent.is_dir():
            raise ValueError("Budgeted output must be new and have an existing private parent.")
        if problem := output_limit.check():
            raise _output_error(problem)
    job = None
    process = None
    try:
        if sys.platform == "win32":
            job = WindowsProcessJob()
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=(subprocess.CREATE_NO_WINDOW | 0x00000004) if job is not None else 0,
        )
        if job is not None:
            job.attach_and_resume(process.pid)
    except BaseException as error:
        if job is not None:
            job.close()
        if process is not None and process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await asyncio.wait_for(process.wait(), timeout=5)
        if isinstance(error, OSError):
            raise AppError(
                "environment.media_tool", "无法启动或隔离项目内媒体工具。", ExitCode.ENVIRONMENT
            ) from None
        raise
    assert process.stdout is not None and process.stderr is not None
    overflow = asyncio.Event()
    stdout_task = asyncio.create_task(
        _read_bounded(process.stdout, max_stdout_bytes, overflow)
        if stdout_line_consumer is None
        else _read_consumed_lines(process.stdout, max_stdout_bytes, overflow, stdout_line_consumer)
    )
    stderr_task = asyncio.create_task(
        _read_bounded(process.stderr, max_stderr_bytes, overflow)
        if stderr_line_consumer is None
        else _read_consumed_lines(process.stderr, max_stderr_bytes, overflow, stderr_line_consumer)
    )
    wait_task = asyncio.create_task(process.wait())

    async def collect() -> ProcessOutput:
        stdout, stderr, exit_code = await asyncio.gather(
            stdout_task,
            stderr_task,
            wait_task,
        )
        if exit_code != 0:
            raise AppError("input.media_decode", "媒体文件无法解码。", ExitCode.INPUT)
        if output_limit is not None and (problem := output_limit.check()):
            raise _output_error(problem)
        return ProcessOutput(stdout, stderr)

    async def watch_output() -> str:
        while True:
            if output_limit is not None and (problem := output_limit.check()):
                return problem
            await asyncio.sleep(0.05)

    collection = asyncio.create_task(collect())
    cancellation = asyncio.create_task(context.cancelled.wait())
    limit_reached = asyncio.create_task(overflow.wait())
    file_limit = asyncio.create_task(watch_output()) if output_limit is not None else None
    output_overflow = False
    try:
        done, _ = await asyncio.wait(
            (collection, cancellation, limit_reached, *([file_limit] if file_limit else [])),
            timeout=context.timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancellation in done or context.cancelled.is_set():
            raise asyncio.CancelledError
        if overflow.is_set():
            raise AppError("media.output_limit", "媒体工具输出超过限制。", ExitCode.INPUT)
        if file_limit is not None and file_limit in done:
            output_overflow = True
            raise _output_error(await file_limit)
        if collection not in done:
            raise AppError("media.timeout", "媒体处理超时。", ExitCode.ENVIRONMENT)
        try:
            return await collection
        except AppError as error:
            output_overflow = error.code in (
                "media.file_limit",
                "media.scratch_limit",
                "media.disk_space",
            )
            raise
    finally:
        try:
            if job is not None:
                job.close()
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await asyncio.wait_for(process.wait(), timeout=5)
            # Job termination is asynchronous; descendants can briefly retain pipe handles.
            # Drain to EOF before stopping readers or closing the event loop.
            await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task, wait_task, return_exceptions=True),
                timeout=5,
            )
        finally:
            for task in (
                collection,
                cancellation,
                limit_reached,
                stdout_task,
                stderr_task,
                wait_task,
                *([file_limit] if file_limit else []),
            ):
                task.cancel()
            await asyncio.gather(
                collection,
                cancellation,
                limit_reached,
                stdout_task,
                stderr_task,
                wait_task,
                *([file_limit] if file_limit else []),
                return_exceptions=True,
            )
            if (
                output_overflow
                and output_limit is not None
                and not any(is_link(p) for p in (output_limit.path, *output_limit.path.parents))
            ):
                output_limit.path.unlink(missing_ok=True)
