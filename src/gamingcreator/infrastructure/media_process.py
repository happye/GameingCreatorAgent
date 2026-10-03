import asyncio
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.windows_job import WindowsProcessJob


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


async def run_media_process(
    arguments: list[str],
    context: CancellationContext,
    max_stdout_bytes: int = 4 * 1024 * 1024,
    max_stderr_bytes: int = 16 * 1024 * 1024,
) -> ProcessOutput:
    context.check_cancelled()
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
    stdout_task = asyncio.create_task(_read_bounded(process.stdout, max_stdout_bytes, overflow))
    stderr_task = asyncio.create_task(_read_bounded(process.stderr, max_stderr_bytes, overflow))
    wait_task = asyncio.create_task(process.wait())

    async def collect() -> ProcessOutput:
        stdout, stderr, exit_code = await asyncio.gather(
            stdout_task,
            stderr_task,
            wait_task,
        )
        if exit_code != 0:
            raise AppError("input.media_decode", "媒体文件无法解码。", ExitCode.INPUT)
        return ProcessOutput(stdout, stderr)

    collection = asyncio.create_task(collect())
    cancellation = asyncio.create_task(context.cancelled.wait())
    limit_reached = asyncio.create_task(overflow.wait())
    try:
        done, _ = await asyncio.wait(
            (collection, cancellation, limit_reached),
            timeout=context.timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancellation in done or context.cancelled.is_set():
            raise asyncio.CancelledError
        if overflow.is_set():
            raise AppError("media.output_limit", "媒体工具输出超过限制。", ExitCode.INPUT)
        if collection not in done:
            raise AppError("media.timeout", "媒体处理超时。", ExitCode.ENVIRONMENT)
        return await collection
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
            ):
                task.cancel()
            await asyncio.gather(
                collection,
                cancellation,
                limit_reached,
                stdout_task,
                stderr_task,
                wait_task,
                return_exceptions=True,
            )
