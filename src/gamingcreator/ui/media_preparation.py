"""Local background media preparation, with live ownership separate from saved batch state."""

import asyncio
import json
import re
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import cast
from uuid import uuid4

from gamingcreator.application.media_batch import MediaBatchPlan
from gamingcreator.cli.main import _media_preparation_config, execute_prepare_media_batch
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_files import LocalInputReader
from gamingcreator.infrastructure.media_batch_files import MediaBatchFiles

PROFILES = {
    "frames": "config.example.json",
    "temporal": "config.temporal.example.json",
    "detailed": "config.detailed-v6.example.json",
}
TERMINAL = {"finished", "partial", "failed", "cancelled"}


def _invalid(message: str = "请填写有效的项目、录像路径和准备参数。") -> AppError:
    return AppError("input.media_preparation", message, ExitCode.INPUT)


def preparation_project(repository: Path, value: str) -> Path:
    if type(value) is not str or not value.strip() or len(value) > 8192 or "\0" in value:
        raise _invalid()
    root = repository.resolve()
    artifacts = (root / "artifacts").resolve()
    requested = Path(value)
    project = (requested if requested.is_absolute() else root / requested).resolve()
    if (
        not artifacts.is_relative_to(root)
        or project == artifacts
        or not project.is_relative_to(artifacts)
        or not (project / "timeline.sqlite3").resolve().is_relative_to(project)
    ):
        raise _invalid("准备项目须位于当前仓库的artifacts目录内。")
    return project


def _timeout(value: object) -> float:
    if (
        type(value) not in (int, float)
        or not isfinite(cast(float, value))
        or not 1 <= cast(float, value) <= 86400
    ):
        raise _invalid("每段准备时间须为1–86400秒。")
    return float(cast(float, value))


def _clock() -> str:
    return datetime.now(UTC).isoformat()


def _batch_view(plan: MediaBatchPlan, state: dict[str, object]) -> dict[str, object]:
    rows = cast(list[dict[str, object]], state["items"])
    return {
        "batchId": plan.batch_id,
        "status": state["status"],
        "exitCode": state["exitCode"],
        "maxCostCnyPerTask": str(plan.max_cost_cny),
        "timeoutSeconds": plan.timeout_seconds,
        "items": [
            {**row, "sourceName": item.video.name}
            for item, row in zip(plan.items, rows, strict=True)
        ],
        "modelInvocations": 0,
        "newReservations": 0,
    }


@dataclass
class _Job:
    identifier: str
    project: Path
    arguments: dict[str, object]
    names: dict[str, str]
    thread: threading.Thread | None = None
    loop: asyncio.AbstractEventLoop | None = None
    task: asyncio.Task[dict[str, object]] | None = None
    status: str = "queued"
    cancel_requested: bool = False
    progress: dict[str, object] | None = None
    result: dict[str, object] | None = None
    error: dict[str, object] | None = None
    started_at: str = field(default_factory=_clock)
    updated_at: str = field(default_factory=_clock)


class MediaPreparationJobs:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        self._closed = False

    def submit(self, document: dict[str, object]) -> dict[str, object]:
        if type(document) is not dict:
            raise _invalid()
        resume = "resume" in document
        fields = (
            {"project", "resume", "timeoutSeconds"}
            if resume
            else {"project", "paths", "profile", "maxCostCny", "timeoutSeconds"}
        )
        if set(document) != fields or type(document["project"]) is not str:
            raise _invalid()
        project = preparation_project(self.repository, document["project"])
        timeout = _timeout(document["timeoutSeconds"])
        identifier = uuid4().hex
        arguments: dict[str, object] = {"timeout_seconds": timeout}
        input_bytes: bytes | None = None
        config_bytes: bytes | None = None
        names: dict[str, str]
        if resume:
            batch_id = document["resume"]
            if type(batch_id) is not str or not re.fullmatch(r"[a-f0-9]{32}", batch_id):
                raise _invalid("批次号无效。")
            if not (project / "timeline.sqlite3").is_file():
                raise _invalid("原项目数据库尚未创建，请保留批次资料后重新提交。")
            try:
                plan, _, _ = MediaBatchFiles(project, batch_id).load()
                _media_preparation_config(plan.config)
            except (OSError, ValueError, AppError):
                raise _invalid("原批次资料无法核对，请保留文件并检查后再继续。") from None
            arguments["resume"] = batch_id
            names = {item.item_id: item.video.name for item in plan.items}
        else:
            profile = document["profile"]
            paths = document["paths"]
            budget = document["maxCostCny"]
            if (
                type(profile) is not str
                or profile not in PROFILES
                or type(paths) is not list
                or not 1 <= len(paths) <= 100
                or type(budget) is not str
                or len(budget) > 64
            ):
                raise _invalid()
            try:
                amount = Decimal(budget)
                if not amount.is_finite() or amount <= 0:
                    raise ValueError
                config_path = self.repository / PROFILES[profile]
                _media_preparation_config(LocalInputReader().load_config(config_path))
                config_bytes = config_path.read_bytes()
            except (InvalidOperation, ValueError, OSError, AppError):
                raise _invalid("准备方案或以后每段分析上限无效。") from None
            items = []
            for index, value in enumerate(paths):
                if (
                    type(value) is not str
                    or not value.strip()
                    or len(value) > 16384
                    or "\0" in value
                ):
                    raise _invalid("每段录像须填写本地路径。")
                path = Path(value)
                if str(path.drive).startswith("\\\\") or "://" in value:
                    raise _invalid("请使用本机录像路径。")
                path = (path if path.is_absolute() else self.repository / path).resolve()
                items.append({"id": f"录像{index + 1}", "path": str(path)})
            if len({row["path"].casefold() for row in items}) != len(items):
                raise _invalid("同一录像路径请只提交一次。")
            names = {row["id"]: Path(row["path"]).name for row in items}
            input_bytes = json.dumps(
                {"schemaVersion": "media-batch-input-v1", "items": items}, ensure_ascii=False
            ).encode()
            arguments["max_cost_cny"] = budget
        with self._lock:
            if self._closed or any(
                job.thread is not None and job.thread.is_alive() for job in self._jobs.values()
            ):
                raise AppError(
                    "storage.preparation_busy",
                    "已有批次正在准备，请完成或停止后再提交。",
                    ExitCode.STORAGE,
                )
            if len(self._jobs) >= 100:
                oldest = next(iter(self._jobs))
                del self._jobs[oldest]
            if input_bytes is not None and config_bytes is not None:
                directory = self.repository / ".cache" / "ui-media-preparation" / identifier
                directory.mkdir(parents=True)
                for filename, content in (
                    ("input.json", input_bytes),
                    ("config.json", config_bytes),
                ):
                    with (directory / filename).open("xb") as stream:
                        stream.write(content)
                arguments.update(
                    input_path=directory / "input.json", config_path=directory / "config.json"
                )
            job = _Job(identifier, project, arguments, names)
            self._jobs[identifier] = job
            job.thread = threading.Thread(
                target=self._run, args=(job,), name=f"media-preparation-{identifier}", daemon=True
            )
            job.thread.start()
            return self._view(job, document["project"])

    def _view(self, job: _Job, project_reference: str) -> dict[str, object]:
        return deepcopy(
            {
                "schemaVersion": "media-preparation-job-v1",
                "jobId": job.identifier,
                "project": project_reference,
                "batchId": job.progress["batchId"] if job.progress else job.arguments.get("resume"),
                "status": job.status,
                "live": job.thread is not None and job.thread.is_alive(),
                "cancellationRequested": job.cancel_requested,
                "progress": job.progress,
                "result": job.result,
                "error": job.error,
                "startedAt": job.started_at,
                "updatedAt": job.updated_at,
                "modelInvocations": 0,
                "newReservations": 0,
            }
        )

    def _owned(self, project: Path, identifier: str) -> _Job:
        job = self._jobs.get(identifier)
        if job is None or job.project != project:
            raise AppError("input.preparation_job", "本项目没有这个页面准备任务。", ExitCode.INPUT)
        return job

    def get(self, project_reference: str, identifier: str) -> dict[str, object]:
        project = preparation_project(self.repository, project_reference)
        with self._lock:
            return self._view(self._owned(project, identifier), project_reference)

    def cancel(self, project_reference: str, identifier: str) -> dict[str, object]:
        project = preparation_project(self.repository, project_reference)
        with self._lock:
            job = self._owned(project, identifier)
            if job.status not in TERMINAL:
                job.cancel_requested = True
                job.status = "cancelling"
                if (
                    job.loop is not None
                    and job.task is not None
                    and not job.loop.is_closed()
                    and not job.task.done()
                ):
                    job.loop.call_soon_threadsafe(job.task.cancel)
            return self._view(job, project_reference)

    def _run(self, job: _Job) -> None:
        def progress(document: dict[str, object]) -> None:
            with self._lock:
                snapshot = deepcopy(document)
                for row in cast(list[dict[str, object]], snapshot["items"]):
                    row["sourceName"] = job.names[cast(str, row["id"])]
                job.progress = snapshot
                job.updated_at = _clock()

        async def execute() -> dict[str, object]:
            with self._lock:
                job.loop = asyncio.get_running_loop()
                job.task = asyncio.create_task(
                    execute_prepare_media_batch(
                        job.project,
                        self.repository,
                        on_progress=progress,
                        input_path=cast(Path | None, job.arguments.get("input_path")),
                        config_path=cast(Path | None, job.arguments.get("config_path")),
                        max_cost_cny=cast(str | None, job.arguments.get("max_cost_cny")),
                        resume=cast(str | None, job.arguments.get("resume")),
                        timeout_seconds=cast(float, job.arguments["timeout_seconds"]),
                    )
                )
                if job.cancel_requested:
                    job.task.cancel()
                else:
                    job.status = "running"
            return await job.task

        try:
            result = asyncio.run(execute())
            with self._lock:
                job.result = result
                state = str(result["status"])
                job.status = state if state in TERMINAL else "failed"
        except asyncio.CancelledError:
            with self._lock:
                job.status = "cancelled"
        except Exception as error:
            with self._lock:
                job.status = "failed"
                job.error = (
                    {"code": error.code, "message": error.message}
                    if isinstance(error, AppError)
                    else {
                        "code": "environment.media_preparation",
                        "message": "本地准备停止，请检查环境后明确续跑。",
                    }
                )
        finally:
            with self._lock:
                job.loop = None
                job.task = None
                job.updated_at = _clock()

    def catalog(
        self, project_reference: str, *, limit: int = 20, offset: int = 0
    ) -> dict[str, object]:
        project = preparation_project(self.repository, project_reference)
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 1_000_000
        ):
            raise _invalid()
        directories = sorted(
            (
                path
                for path in (project / "media-batches").glob("*")
                if re.fullmatch(r"[a-f0-9]{32}", path.name) and path.is_dir()
            ),
            key=lambda path: path.name,
        )
        batches = []
        for directory in directories[offset : offset + limit]:
            if not re.fullmatch(r"[a-f0-9]{32}", directory.name):
                continue
            try:
                plan, state, _ = MediaBatchFiles(project, directory.name).load()
                batches.append({**_batch_view(plan, state), "readable": True})
            except (OSError, ValueError, AppError):
                batches.append(
                    {
                        "batchId": directory.name,
                        "readable": False,
                        "message": "批次资料无法核对，请保留文件后检查。",
                    }
                )
        with self._lock:
            active = next(
                (
                    self._view(job, project_reference)
                    for job in self._jobs.values()
                    if job.project == project and job.thread is not None and job.thread.is_alive()
                ),
                None,
            )
        return {
            "schemaVersion": "media-preparation-catalog-v1",
            "project": project_reference,
            "batches": batches,
            "total": len(directories),
            "offset": offset,
            "limit": limit,
            "activeJob": active,
            "modelInvocations": 0,
            "newReservations": 0,
        }

    def close(self) -> None:
        with self._lock:
            self._closed = True
            jobs = list(self._jobs.values())
        for job in jobs:
            self.cancel(str(job.project), job.identifier)
        for job in jobs:
            if job.thread is not None:
                job.thread.join(timeout=5)
