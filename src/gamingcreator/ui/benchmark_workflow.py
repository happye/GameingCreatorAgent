"""Persistent local acceptance steps, reusing the public scripts and CLI contracts."""

import asyncio
import hashlib
import importlib.util
import mimetypes
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlencode
from uuid import uuid4

from gamingcreator.application.benchmark_preparation import canonical_json, loads_plan
from gamingcreator.application.benchmark_review import decode_object
from gamingcreator.application.retrieval import RetrievalMode
from gamingcreator.cli.main import (
    execute_benchmark,
    execute_bind_benchmark,
    execute_freeze_benchmark,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.benchmark_preparation_files import read_bounded
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui.benchmark_reference_review import render_reference_review
from gamingcreator.ui.benchmark_review import render_benchmark_review
from gamingcreator.ui.media import MediaResource

VERSION = "benchmark-workflow-v1"
STEPS = (
    "register",
    "references",
    "references-import",
    "freeze",
    "bind",
    "ranking",
    "review",
    "score",
)
FIELDS = {
    "register": {"inputText"},
    "references": {"inputText"},
    "references-import": {"inputText"},
    "freeze": set(),
    "bind": {"project", "inputText", "partition"},
    "ranking": {"mode"},
    "review": set(),
    "score": {"inputText"},
}
SCRIPT_ROOT = Path(__file__).resolve().parents[3] / "scripts"
MAX_FILE = 16_777_216


def _invalid(message: str = "验收资料或步骤不符，请保留原资料后检查。") -> AppError:
    return AppError("input.benchmark_workflow", message, ExitCode.INPUT)


def _clock() -> str:
    return datetime.now(UTC).isoformat()


def _id(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{32}", value) is None:
        raise _invalid("验收流程编号无效。")
    return value


def _plain(path: Path) -> Path:
    if any(item.is_symlink() or item.is_junction() for item in (path, *path.parents)):
        raise _invalid("验收资料不能通过文件或目录链接替换。")
    return path


def _write(path: Path, document: dict[str, object]) -> None:
    data = canonical_json(document)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    with _plain(temporary).open("xb") as stream:
        stream.write(data)
    _plain(temporary).replace(_plain(path))


def _script(name: str, arguments: list[str], repository: Path) -> int:
    # Only fixed, trusted repository entry points. No supplied module/path/code is executed.
    path = repository / "scripts" / name
    if not path.is_file():
        path = SCRIPT_ROOT / name
    _plain(path)
    spec = importlib.util.spec_from_file_location("benchmark_workspace_entry", path)
    if spec is None or spec.loader is None:
        raise _invalid("公开验收入口缺失，请检查项目安装。")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Callable[[list[str]], int], module.main)(arguments)


class BenchmarkWorkflows:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()
        self.root = self.repository / "artifacts" / "benchmark-workflows"
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._closed = False

    def directory(self, identifier: str) -> Path:
        path = _plain(self.root / _id(identifier))
        if not path.resolve().is_relative_to(self.repository):
            raise _invalid()
        return path

    def create(self, document: dict[str, object]) -> dict[str, object]:
        if set(document) != {"name"} or type(document["name"]) is not str:
            raise _invalid()
        name = document["name"].strip()
        if not name or len(name) > 120 or "\0" in name:
            raise _invalid("请填写不超过120字的流程名称。")
        with self._lock:
            if self._closed:
                raise _invalid("工作台正在关闭。")
            identifier = uuid4().hex
            directory = self.directory(identifier)
            directory.mkdir(parents=True)
            _write(
                directory / "workflow.json",
                {"schemaVersion": VERSION, "id": identifier, "name": name, "createdAt": _clock()},
            )
        return self.get(identifier)

    def _metadata(self, identifier: str) -> dict[str, object]:
        document = decode_object(read_bounded(_plain(self.directory(identifier) / "workflow.json")))
        if (
            set(document) != {"schemaVersion", "id", "name", "createdAt"}
            or document["schemaVersion"] != VERSION
            or document["id"] != identifier
            or type(document["name"]) is not str
            or type(document["createdAt"]) is not str
        ):
            raise _invalid("流程登记资料已改变。")
        return document

    def _attempts(self, identifier: str) -> list[dict[str, object]]:
        directory = self.directory(identifier)
        attempts = []
        for path in sorted(directory.glob("[0-9]*-*/status.json")):
            row = decode_object(read_bounded(_plain(path)))
            if (
                set(row)
                != {
                    "attemptId",
                    "action",
                    "startedAt",
                    "status",
                    "exitCode",
                    "files",
                    "error",
                    "project",
                    "qualityGate",
                    "elapsedMs",
                    "dependencies",
                }
                or row["attemptId"] != path.parent.name
                or re.fullmatch(r"\d{6}-[a-f0-9]{32}", path.parent.name) is None
                or row["action"] not in STEPS
                or row["status"] not in {"running", "finished", "failed"}
                or type(row["files"]) is not dict
                or type(row["dependencies"]) is not dict
            ):
                raise _invalid("流程步骤记录已改变。")
            attempts.append(row)
        return attempts

    def _busy(self, identifier: str) -> bool:
        lock = ProjectWriterLock(self.directory(identifier))
        _plain(self.directory(identifier) / ".analysis-writer.lock")
        try:
            lock.acquire()
        except AppError as error:
            if error.code == "storage.writer_busy":
                return True
            raise
        finally:
            lock.close()
        return False

    def get(self, identifier: str) -> dict[str, object]:
        with self._lock:
            metadata = self._metadata(identifier)
            attempts = self._attempts(identifier)
            busy = (
                self._busy(identifier)
                if any(row["status"] == "running" for row in attempts)
                else False
            )
            for row in attempts:
                if row["status"] == "running" and not busy:
                    row["status"] = "interrupted"
                    row["error"] = "执行所有权已释放；保留已有文件，明确重试会创建新目录。"
            return {
                **metadata,
                "attempts": attempts,
                "busy": busy,
                "qualityGate": next(
                    (
                        row["qualityGate"]
                        for row in reversed(attempts)
                        if row["action"] == "score" and row["status"] == "finished"
                    ),
                    None,
                ),
                "paidRequestsSent": 0,
            }

    def catalog(self) -> dict[str, object]:
        with self._lock:
            _plain(self.root)
            paths = sorted(self.root.glob("*/workflow.json"), reverse=True)
            if len(paths) > 200:
                raise _invalid("流程超过200个，请先保留资料后整理。")
            rows = [
                {
                    key: value
                    for key, value in self.get(path.parent.name).items()
                    if key != "attempts"
                }
                for path in paths
            ]
            rows.sort(key=lambda row: str(row["createdAt"]), reverse=True)
            return {"schemaVersion": VERSION, "workflows": rows}

    def _output(self, identifier: str, row: dict[str, object]) -> Path:
        return _plain(self.directory(identifier) / cast(str, row["attemptId"]) / "output")

    def file(self, identifier: str, attempt: str, name: str) -> bytes:
        if re.fullmatch(r"\d{6}-[a-f0-9]{32}", attempt) is None:
            raise _invalid()
        row = next(
            (item for item in self._attempts(identifier) if item["attemptId"] == attempt), None
        )
        if (
            row is None
            or row["status"] != "finished"
            or name not in cast(dict[str, object], row["files"])
            or re.fullmatch(r"[a-z][a-z0-9-]*\.(json|html)", name) is None
        ):
            raise _invalid("只有已完成步骤的登记文件可以读取。")
        data = read_bounded(_plain(self._output(identifier, row) / name), MAX_FILE)
        if hashlib.sha256(data).hexdigest() != cast(dict[str, object], row["files"])[name]:
            raise _invalid("保存资料已改变，不能继续使用旧结果。")
        return data

    def _successful(self, identifier: str) -> dict[str, dict[str, object]]:
        rows = {
            cast(str, row["action"]): row
            for row in self._attempts(identifier)
            if row["status"] == "finished"
        }
        for row in rows.values():
            for name in cast(dict[str, object], row["files"]):
                self.file(identifier, cast(str, row["attemptId"]), name)
        return rows

    def submit(self, document: dict[str, object]) -> dict[str, object]:
        if (
            set(document) != {"workflow", "action", "fields"}
            or type(document["action"]) is not str
            or document["action"] not in STEPS
            or type(document["fields"]) is not dict
        ):
            raise _invalid()
        identifier, action = _id(document["workflow"]), document["action"]
        fields = cast(dict[str, object], document["fields"])
        if set(fields) != FIELDS[action] or any(
            type(value) is not str for value in fields.values()
        ):
            raise _invalid()
        if "inputText" in fields:
            value = cast(str, fields["inputText"])
            if value or action != "register":
                uploaded = decode_object(value.encode())
                if action == "register":
                    sources = uploaded.get("sources", [])
                    if type(sources) is list and any(
                        type(item) is dict
                        and type(item.get("path")) is str
                        and item["path"]
                        and not Path(item["path"]).is_absolute()
                        for item in sources
                    ):
                        raise _invalid("上传登记资料须使用原录像完整路径，空路径可以留待填写。")
        if action == "references":
            plan = loads_plan(cast(str, fields["inputText"]))
            if any(not Path(source.path).is_absolute() for source in plan.sources):
                raise _invalid("载入的计划须包含原录像完整路径，不猜测下载文件的原目录。")
        if action == "bind":
            if fields["partition"] not in {"development", "test"}:
                raise _invalid()
            project_path = Path(cast(str, fields["project"]))
            project = (
                project_path if project_path.is_absolute() else self.repository / project_path
            ).resolve()
            if (
                not project.is_relative_to(self.repository / "artifacts")
                or not (project / "timeline.sqlite3").resolve().is_relative_to(self.repository)
                or not (project / "timeline.sqlite3").is_file()
            ):
                raise _invalid("请选择当前仓库artifacts中的已有分析项目。")
            fields = {**fields, "project": str(project)}
        if action == "ranking" and fields["mode"] not in {"lexical", "semantic", "hybrid"}:
            raise _invalid()
        with self._lock:
            if self._closed:
                raise _invalid("工作台正在关闭。")
            self._metadata(identifier)
            directory = self.directory(identifier)
            lock = ProjectWriterLock(directory)
            _plain(directory / ".analysis-writer.lock")
            lock.acquire()
            try:
                rows = self._successful(identifier)
                index = STEPS.index(action)
                required = {
                    "references-import": "references",
                    "freeze": "references-import",
                    "bind": "freeze",
                    "ranking": "bind",
                    "review": "ranking",
                    "score": "review",
                }
                if action in required and required[action] not in rows:
                    raise _invalid("请先完成页面提示的前一步。")
                if any(STEPS.index(key) > index for key in rows):
                    raise _invalid("后续资料已生成，早期来源或结果不能改写；请新建流程。")
                attempts = self._attempts(identifier)
                if len(attempts) >= 200:
                    raise _invalid("本流程步骤超过200次，请保留资料后新建流程。")
                attempt = f"{len(attempts) + 1:06d}-{uuid4().hex}"
                parent = _plain(directory / attempt)
                parent.mkdir()
                dependencies = {key: row["attemptId"] for key, row in rows.items()}
                row: dict[str, object] = {
                    "attemptId": attempt,
                    "action": action,
                    "startedAt": _clock(),
                    "status": "running",
                    "exitCode": None,
                    "files": {},
                    "error": None,
                    "project": fields.get("project", rows.get("bind", {}).get("project")),
                    "qualityGate": None,
                    "elapsedMs": None,
                    "dependencies": dependencies,
                }
                _write(
                    parent / "request.json",
                    {"action": action, "fields": fields, "dependencies": dependencies},
                )
                _write(parent / "status.json", row)
                thread = threading.Thread(
                    target=self._run, args=(identifier, row, fields, rows, lock), daemon=True
                )
                self._threads[identifier] = thread
                thread.start()
            except BaseException:
                lock.close()
                raise
        return self.get(identifier)

    def _execute(
        self,
        identifier: str,
        row: dict[str, object],
        fields: dict[str, object],
        rows: dict[str, dict[str, object]],
    ) -> tuple[int, object]:
        parent = self.directory(identifier) / cast(str, row["attemptId"])
        output = parent / "output"
        action = row["action"]
        input_path = parent / "input.json"
        if fields.get("inputText"):
            with input_path.open("xb") as stream:
                stream.write(cast(str, fields["inputText"]).encode())
        if action == "register":
            arguments = ["--output", str(output)]
            if input_path.exists():
                arguments.extend(["--input", str(input_path)])
            return _script("prepare-benchmark-plan.py", arguments, self.repository), None
        if action in {"references", "references-import"}:
            arguments = ["--output", str(output)]
            if action == "references":
                arguments.extend(["--input", str(input_path)])
            else:
                arguments.extend(
                    [
                        "--review-directory",
                        str(self._output(identifier, rows["references"])),
                        "--record",
                        str(input_path),
                    ]
                )
            return _script("prepare-benchmark-references.py", arguments, self.repository), None
        if action == "freeze":
            asyncio.run(
                execute_freeze_benchmark(
                    self._output(identifier, rows["references-import"]) / "benchmark-plan.json",
                    output,
                    self.repository,
                )
            )
            return 0, None
        if action == "bind":
            asyncio.run(
                execute_bind_benchmark(
                    self._output(identifier, rows["freeze"]),
                    Path(cast(str, row["project"])),
                    input_path,
                    cast(str, fields["partition"]),
                    output,
                )
            )
            return 0, None
        binding = self._output(identifier, rows["bind"])
        project = Path(cast(str, row["project"]))
        if action == "ranking":
            output.mkdir()
            report = output / "benchmark-report.json"
            result = asyncio.run(
                execute_benchmark(
                    project,
                    binding / "benchmark.json",
                    report,
                    self.repository,
                    mode=cast(RetrievalMode, fields["mode"]),
                    binding_path=binding,
                )
            )
            return (0 if result["qualityGate"] is True else 6), None
        report = self._output(identifier, rows["ranking"]) / "benchmark-report.json"
        arguments = [
            "--project",
            str(project),
            "--binding",
            str(binding),
            "--report",
            str(report),
            "--output",
            str(output),
        ]
        if action == "score":
            arguments.extend(["--record", str(input_path), "--score"])
        return _script("prepare-benchmark-review.py", arguments, self.repository), None

    def _run(
        self,
        identifier: str,
        row: dict[str, object],
        fields: dict[str, object],
        rows: dict[str, dict[str, object]],
        lock: ProjectWriterLock,
    ) -> None:
        start = time.perf_counter()
        try:
            code, _ = self._execute(identifier, row, fields, rows)
            row["exitCode"] = code
            if code not in {0, 6}:
                raise _invalid("原片、冻结资料或记录核对失败；原输入及这次文件已保留。")
            output = self._output(identifier, row)
            if row["action"] == "ranking":
                names = {"benchmark-report.json"}
            else:
                receipt = decode_object(read_bounded(_plain(output / "receipt.json")))
                names = set(cast(dict[str, object], receipt["files"]))
                for name in names:
                    data = read_bounded(_plain(output / name), MAX_FILE)
                    if (
                        hashlib.sha256(data).hexdigest()
                        != cast(dict[str, object], receipt["files"])[name]
                    ):
                        raise _invalid()
                names.add("receipt.json")
            row["files"] = {
                name: hashlib.sha256(read_bounded(_plain(output / name), MAX_FILE)).hexdigest()
                for name in names
            }
            if row["action"] == "score":
                row["qualityGate"] = decode_object(
                    read_bounded(output / "benchmark-fixed-report.json")
                )["qualityGate"]
            row["status"] = "finished"
        except (
            AppError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            OverflowError,
            RecursionError,
        ) as error:
            row["status"] = "failed"
            row["error"] = (
                error.message
                if isinstance(error, AppError)
                else "资料读取或保存失败；保留已有文件，检查后明确重试。"
            )
            if row["exitCode"] is None:
                row["exitCode"] = int(error.exit_code) if isinstance(error, AppError) else 2
        finally:
            row["elapsedMs"] = round((time.perf_counter() - start) * 1000, 3)
            try:
                _write(
                    self.directory(identifier) / cast(str, row["attemptId"]) / "status.json", row
                )
            finally:
                lock.close()

    def page(self, identifier: str, attempt: str, name: str) -> bytes:
        original = self.file(identifier, attempt, name)
        if name == "edit.html":
            return original
        if name != "review.html":
            raise _invalid()
        context = decode_object(self.file(identifier, attempt, "context.json"))
        template = decode_object(self.file(identifier, attempt, "record-template.json"))
        media = cast(list[dict[str, object]], context["media"])
        urls = {
            cast(str, item.get("id", item.get("runId"))): "/api/benchmark-source?"
            + urlencode(
                {
                    "workflow": identifier,
                    "attempt": attempt,
                    "source": item.get("id", item.get("runId")),
                }
            )
            for item in media
        }
        renderer = (
            render_reference_review
            if context.get("schemaVersion") == "benchmark-reference-context-v1"
            else render_benchmark_review
        )
        return renderer(context, template, media_urls=urls).encode()

    def media(self, identifier: str, attempt: str, source: str) -> MediaResource:
        context = decode_object(self.file(identifier, attempt, "context.json"))
        row = next(
            (
                item
                for item in cast(list[dict[str, object]], context["media"])
                if item.get("id", item.get("runId")) == source
            ),
            None,
        )
        if row is None:
            raise _invalid("没有此步骤登记的原片。")
        sha = row.get("sha256")
        if sha is None:
            manifest = cast(dict[str, object], context["manifest"])
            sha = next(
                item["sha256"]
                for item in cast(list[dict[str, object]], manifest["media"])
                if item["runId"] == source
            )
        path = Path(cast(str, row["path"]))
        return MediaResource(
            path, cast(str, sha), mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        )

    def close(self) -> None:
        with self._lock:
            self._closed = True
            threads = list(self._threads.values())
        for thread in threads:
            thread.join(5)
