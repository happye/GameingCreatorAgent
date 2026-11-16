"""本机逐词识别任务：显式开始、查询状态和取消，不另建通用队列或收费路径。"""

from __future__ import annotations

import asyncio
import re
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.asr_words import (
    WordTranscriptionSummary,
    transcribe_project_words,
)

SCHEMA_VERSION = "asr-words-job-v1"
TERMINAL = {"finished", "failed", "cancelled"}
_TASK_ID = re.compile(r"[0-9a-f]{32}")


def _clock() -> str:
    return datetime.now(UTC).isoformat()


def _invalid(message: str = "请填写项目、任务和本机识别模型。") -> AppError:
    return AppError("asr.task_input", message, ExitCode.INPUT)


def _missing_task() -> AppError:
    return AppError("asr.task_not_found", "找不到这个逐词识别任务。", ExitCode.INPUT)


@dataclass
class _Job:
    task_id: str
    project_id: str
    project: Path
    run_id: str
    model: str
    context: CancellationContext
    thread: threading.Thread | None = None
    loop: asyncio.AbstractEventLoop | None = None
    task: asyncio.Task[WordTranscriptionSummary] | None = None
    status: str = "queued"
    cancel_requested: bool = False
    result: dict[str, object] | None = None
    error: dict[str, object] | None = None
    started_at: str = field(default_factory=_clock)
    updated_at: str = field(default_factory=_clock)


class AsrWordsJobs:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        self._closed = False

    def submit(self, document: dict[str, object]) -> dict[str, object]:
        if (
            type(document) is not dict
            or set(document) != {"projectId", "runId", "model"}
            or any(type(value) is not str or not value.strip() for value in document.values())
        ):
            raise _invalid()
        from uuid import uuid4

        from gamingcreator.ui.server import resolve_project

        project_id = document["projectId"]
        run_id = document["runId"]
        model = document["model"]
        if type(project_id) is not str or type(run_id) is not str or type(model) is not str:
            raise _invalid()
        project = resolve_project(self.repository, project_id)
        task_id = uuid4().hex
        job = _Job(
            task_id,
            project_id,
            project,
            run_id,
            model,
            CancellationContext(run_id, 600),
        )
        with self._lock:
            if self._closed:
                raise AppError(
                    "asr.task_closed", "工作台已关闭，不能再开始逐词识别。", ExitCode.INPUT
                )
            self._jobs[task_id] = job
            job.thread = threading.Thread(
                target=self._run, args=(job,), name=f"asr-words-{task_id}", daemon=True
            )
            job.thread.start()
            return self._view(job)

    def get(self, project_id: str, task_id: str) -> dict[str, object]:
        with self._lock:
            return self._view(self._owned(project_id, task_id))

    def cancel(self, project_id: str, task_id: str) -> dict[str, object]:
        with self._lock:
            job = self._owned(project_id, task_id)
            if job.status not in TERMINAL:
                job.cancel_requested = True
                job.status = "cancelling"
                job.updated_at = _clock()
                job.context.cancelled.set()
                if (
                    job.loop is not None
                    and job.task is not None
                    and not job.loop.is_closed()
                    and not job.task.done()
                ):
                    job.loop.call_soon_threadsafe(job.task.cancel)
            return self._view(job)

    def _owned(self, project_id: str, task_id: str) -> _Job:
        from gamingcreator.ui.server import resolve_project

        if (
            type(project_id) is not str
            or not project_id.strip()
            or not _TASK_ID.fullmatch(task_id if type(task_id) is str else "")
        ):
            raise _missing_task()
        project = resolve_project(self.repository, project_id)
        job = self._jobs.get(task_id)
        if job is None or job.project != project or job.project_id != project_id:
            raise _missing_task()
        return job

    def _view(self, job: _Job) -> dict[str, object]:
        return deepcopy(
            {
                "schemaVersion": SCHEMA_VERSION,
                "taskId": job.task_id,
                "projectId": job.project_id,
                "runId": job.run_id,
                "model": job.model,
                "status": job.status,
                "live": job.thread is not None and job.thread.is_alive(),
                "cancellationRequested": job.cancel_requested,
                "result": job.result,
                "error": job.error,
                "startedAt": job.started_at,
                "updatedAt": job.updated_at,
            }
        )

    def _run(self, job: _Job) -> None:
        async def execute() -> WordTranscriptionSummary:
            with self._lock:
                job.loop = asyncio.get_running_loop()
                job.task = asyncio.create_task(
                    transcribe_project_words(
                        job.project,
                        job.run_id,
                        job.model,
                        self.repository,
                        context=job.context,
                    )
                )
                if job.cancel_requested:
                    job.task.cancel()
                else:
                    job.status = "running"
                    job.updated_at = _clock()
                task = job.task
            assert task is not None
            return await task

        try:
            summary = asyncio.run(execute())
            with self._lock:
                job.result = summary.to_json()
                job.status = "finished"
        except AppError as error:
            with self._lock:
                job.error = {
                    "code": error.code,
                    "message": error.message,
                    "exitCode": int(error.exit_code),
                }
                job.status = "cancelled" if error.code == "asr.cancelled" else "failed"
        except asyncio.CancelledError:
            with self._lock:
                job.status = "cancelled"
                job.error = {
                    "code": "asr.cancelled",
                    "message": "逐词识别已取消。",
                    "exitCode": int(ExitCode.CANCELLED),
                }
        finally:
            with self._lock:
                job.loop = None
                job.task = None
                job.updated_at = _clock()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            threads: list[threading.Thread] = []
            for job in self._jobs.values():
                if job.status not in TERMINAL:
                    job.cancel_requested = True
                    job.context.cancelled.set()
                    if (
                        job.loop is not None
                        and job.task is not None
                        and not job.loop.is_closed()
                        and not job.task.done()
                    ):
                        try:
                            job.loop.call_soon_threadsafe(job.task.cancel)
                        except RuntimeError:
                            pass
                if job.thread is not None:
                    threads.append(job.thread)
        for thread in threads:
            thread.join(5)
