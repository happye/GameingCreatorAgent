"""Persistent local creation jobs; OS ownership, not saved status, proves liveness."""

import asyncio
import hashlib
import json
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.cli.creation import execute_plan_creation
from gamingcreator.cli.creation_render import execute_render_creation, read_creation
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.creation_audio import AudioMix
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.infrastructure.file_sharing import retry_file_sharing
from gamingcreator.infrastructure.local_paths import is_link, resolve_existing
from gamingcreator.infrastructure.music_library import MusicLibrary
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui import package_jobs, publication_jobs
from gamingcreator.ui.media import MediaResource, VerifiedMediaCache
from gamingcreator.ui.revision_jobs import (
    editor,
    load_chain,
    prepare_revision,
    render_revision,
    resolve_audio,
    resolve_overrides,
    save_revision,
)


def fail(code: str, message: str, conflict: bool = False) -> AppError:
    return AppError(code, message, ExitCode.STORAGE if conflict else ExitCode.INPUT)


def identity(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{32}", value) is None:
        raise fail("creation.input", "无效任务标识。")
    return value


class CreationJobs:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()
        self.root = self.repository / ".cache/workspace/creations"
        if resolve_existing(self.root) != self.root or any(
            is_link(parent)
            for parent in (self.root, *self.root.parents)
            if parent.is_relative_to(self.repository)
        ):
            raise fail("creation.artifact_invalid", "任务根目录不能使用链接。", True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs = self.root / "jobs"
        self.safe(self.jobs)
        self.jobs.mkdir(exist_ok=True)
        self.threads: list[threading.Thread] = []
        self.cache = VerifiedMediaCache()

    def safe(self, path: Path) -> Path:
        resolved = resolve_existing(path)
        if not resolved.is_relative_to(self.root) or any(
            is_link(parent) for parent in (path, *path.parents) if parent.is_relative_to(self.root)
        ):
            raise fail("creation.artifact_invalid", "任务文件位置无效。", True)
        return resolved

    def read(self, path: Path) -> dict[str, Any]:
        path = self.safe(path)
        if path.stat().st_size > 32_000_000:
            raise ValueError("Oversize job document")
        value = json.loads(
            retry_file_sharing(lambda: path.read_text(encoding="utf-8"), reading=True)
        )
        if not isinstance(value, dict):
            raise ValueError("Invalid job document")
        return value

    def save(self, path: Path, value: dict[str, Any]) -> None:
        self.safe(path)
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)
        retry_file_sharing(lambda: temporary.replace(path))

    def directory(self, job_id: str) -> Path:
        directory = self.safe(self.jobs / identity(job_id))
        if not directory.is_dir():
            raise fail("creation.not_found", "找不到任务。")
        return directory

    def project(self, project_id: object) -> Path:
        from gamingcreator.ui.server import discover_projects

        if not isinstance(project_id, str) or project_id not in {
            item["path"] for item in discover_projects(self.repository)
        }:
            raise fail("creation.not_found", "找不到登记项目。")
        project = resolve_existing(self.repository / project_id)
        if self.root.is_relative_to(project):
            raise fail("creation.input", "任务输出不能位于输入项目内。")
        return project

    def submit(self, kind: str, request: dict[str, Any]) -> dict[str, object]:
        if kind not in ("plan", "revision", "render", "publication", "package") or not isinstance(
            request, dict
        ):
            raise fail("creation.input", "无效任务类型。")
        expected = {"requestId", "projectId", "runIds", "brief", "fps"}
        if kind == "revision":
            expected = {
                "requestId",
                "parentJobId",
                "planId",
                "expectedParentReceiptSha256",
                "clips",
            }
        elif kind == "render":
            expected = (
                {"requestId", "revisionJobId", "width", "height"}
                if "revisionJobId" in request
                else {"requestId", "planJobId", "planId", "width", "height"}
            )
        if kind == "publication":
            expected = {
                "requestId",
                "renderJobId",
                "expectedRenderReceiptSha256",
                "coverFrame",
                "title",
                "description",
                "tags",
            }
        if kind == "package":
            expected = {
                "requestId",
                "publicationJobId",
                "expectedPublicationReceiptSha256",
                "profile",
            }
        optional = (
            {"subtitleMode"}
            if kind == "render"
            else (
                {"subtitleOverrides", "audioMix", "candidateManifestSha256", "replacements"}
                if kind == "revision"
                else set()
            )
        )
        if set(request) - optional != expected:
            raise fail("creation.input", "请填写完整创作参数。")
        if kind == "render" and request.get("subtitleMode", "none") not in (
            "none",
            "sidecar",
            "burn",
        ):
            raise fail("creation.input", "无效字幕选项。")
        request_id = identity(request["requestId"])
        canonical = json.dumps(
            {"kind": kind, "request": request}, sort_keys=True, ensure_ascii=False
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        root_lock = ProjectWriterLock(self.root)
        for attempt in range(100):
            try:
                root_lock.acquire()
                break
            except AppError as error:
                if error.code != "storage.writer_busy" or attempt == 99:
                    raise
                time.sleep(0.01)
        try:
            registration = self.root / (request_id + ".json")
            if registration.exists():
                prior = self.read(registration)
                if prior["digest"] != digest:
                    raise fail("creation.conflict", "同一请求标识已有不同内容。", True)
                job = self.get(prior["jobId"])
                return {key: job[key] for key in ("jobId", "kind", "status")}
            parent_id = None
            parent_digest = None
            if kind == "plan":
                project = self.project(request["projectId"])
                CreativeBrief.from_json(request["brief"])
                runs = request["runIds"]
                if (
                    not isinstance(runs, list)
                    or not runs
                    or any(not isinstance(run, str) or not run for run in runs)
                    or len(runs) != len(set(runs))
                ):
                    raise fail("creation.input", "请选择不同的已完成素材。")
                if type(request["fps"]) is not int or not 1 <= request["fps"] <= 120:
                    raise fail("creation.input", "无效输出帧率。")
                project_id = request["projectId"]
            elif kind == "package":
                parent_id = identity(request["publicationJobId"])
                project_id, parent_digest = package_jobs.prepare(self, request)
                project = self.project(project_id)
            elif kind == "publication":
                parent_id = identity(request["renderJobId"])
                project_id, parent_digest = publication_jobs.prepare(self, request)
                project = self.project(project_id)
            elif kind == "revision" or "revisionJobId" in request:
                parent_id = identity(
                    request["parentJobId"] if kind == "revision" else request["revisionJobId"]
                )
                chain = load_chain(self, parent_id, request.get("planId"))
                if kind == "revision":
                    if request["expectedParentReceiptSha256"] != chain.digest:
                        raise fail("creation.conflict", "父版本已更改，请重新打开编辑器。", True)
                    revised, _ = prepare_revision(self, request, chain)
                    resolve_overrides(request, chain.subtitle_overrides, revised, chain.root_sha)
                    resolve_audio(self, request, chain.audio_mix)
                elif self.read(self.directory(parent_id) / "status.json")["kind"] != "revision":
                    raise fail("creation.conflict", "请选择已完成编辑版本。", True)
                project_id = chain.project_id
                project = self.project(project_id)
                parent_digest = chain.digest
            else:
                parent_id = identity(request["planJobId"])
                parent = self.get(parent_id)
                if parent["kind"] != "plan" or parent["status"] != "completed":
                    raise fail("creation.conflict", "父方案尚未完成。", True)
                report = self.plan_report(self.directory(parent_id))
                select_edit_decision(report, request["planId"])
                project_id = parent["projectId"]
                project = self.project(project_id)
                parent_digest = hash_file(self.directory(parent_id) / "result/receipt.json")
            if kind == "render":
                for key in ("width", "height"):
                    if (
                        type(request[key]) is not int
                        or not 16 <= request[key] <= 3840
                        or request[key] % 2
                    ):
                        raise fail("creation.input", "输出尺寸需为16至3840的偶数。")
            job_id = uuid4().hex
            directory = self.safe(self.jobs / job_id)
            directory.mkdir()
            owner = ProjectWriterLock(directory)
            owner.acquire()
            try:
                now = datetime.now(UTC).isoformat()
                state = {
                    "jobId": job_id,
                    "kind": kind,
                    "status": "pending",
                    "createdAt": now,
                    "updatedAt": now,
                    "projectId": project_id,
                    "parentJobId": parent_id,
                    "error": None,
                }
                self.save(
                    directory / "request.json",
                    {"request": request, "digest": digest, "parentReceiptSha256": parent_digest},
                )
                if kind == "plan":
                    (directory / "input").mkdir()
                    self.save(directory / "input/brief.json", request["brief"])
                self.save(directory / "status.json", state)
                self.save(registration, {"digest": digest, "jobId": job_id})
                worker = threading.Thread(
                    target=self.execute,
                    args=(directory, state, request, project, owner),
                    daemon=True,
                )
                self.threads.append(worker)
                worker.start()
            except BaseException:
                owner.close()
                raise
            return {"jobId": job_id, "kind": kind, "status": "pending"}
        finally:
            root_lock.close()

    def plan_report(self, directory: Path) -> dict[str, Any]:
        receipt = self.read(directory / "result/receipt.json")
        if receipt.get("schemaVersion") != "creation-receipt-v1" or set(
            receipt.get("files", {})
        ) != {"plans.json"}:
            raise ValueError("Invalid plan receipt")
        path = self.safe(directory / "result/plans.json")
        if hash_file(path) != receipt["files"]["plans.json"]:
            raise ValueError("Invalid plan hash")
        return self.read(path)

    def verify(self, directory: Path, state: dict[str, Any]) -> dict[str, Any]:
        receipt_path = self.safe(directory / "result/receipt.json")
        digest = hash_file(receipt_path)
        if (state["status"] == "completed" and "resultReceiptSha256" not in state) or state.get(
            "resultReceiptSha256", digest
        ) != digest:
            raise ValueError("Receipt changed")
        stored = self.read(directory / "request.json")
        result_receipt = self.read(receipt_path)
        if (
            result_receipt.get("jobId") != directory.name
            or result_receipt.get("requestDigest") != stored["digest"]
        ):
            raise ValueError("Result belongs to another job")
        canonical = json.dumps(
            {"kind": state["kind"], "request": stored["request"]},
            sort_keys=True,
            ensure_ascii=False,
        )
        if (
            hashlib.sha256(canonical.encode()).hexdigest() != stored["digest"]
            or state["jobId"] != directory.name
        ):
            raise ValueError("Invalid persisted job identity")
        if state["kind"] == "plan":
            report = self.plan_report(directory)
            request = stored["request"]
            if (
                report.get("brief") != request["brief"]
                or report.get("fps") != request["fps"]
                or any(
                    segment.get("runId") not in request["runIds"]
                    for plan in report["plans"]
                    for segment in plan["segments"]
                )
            ):
                raise ValueError("Result does not match the persisted request")
            state.update({key: report[key] for key in ("plans", "brief", "fps")})
            # Do not alter the immutable original report.
            state = json.loads(json.dumps(state))
            for plan in state["plans"]:
                for segment in plan["segments"]:
                    segment.pop("sourcePath", None)
        elif state["kind"] == "package":
            package_jobs.verify(self, directory, state, stored, result_receipt)
        elif state["kind"] == "publication":
            publication_jobs.verify_publication(self, directory, state, stored, result_receipt)
        elif state["kind"] == "revision":
            chain = load_chain(self, directory.name, pending=state["status"] != "completed")
            state["editor"] = editor(chain, directory.name)
        else:
            request = stored["request"]
            parent_id = request.get("revisionJobId", request.get("planJobId"))
            if state["parentJobId"] != parent_id:
                raise ValueError("Invalid parent job identity")
            parent = self.directory(parent_id)
            parent_state = self.read(parent / "status.json")
            parent_receipt = hash_file(self.safe(parent / "result/receipt.json"))
            if (
                parent_state.get("resultReceiptSha256") != parent_receipt
                or parent_receipt != stored["parentReceiptSha256"]
            ):
                raise ValueError("Parent receipt changed")
            audio_mix = AudioMix()
            if "revisionJobId" in request:
                chain = load_chain(self, parent_id)
                parent_report, expected_edl = chain.report, chain.edl
                audio_mix = chain.audio_mix
                if state["projectId"] != chain.project_id:
                    raise ValueError("Render project changed")
            else:
                parent_report = self.plan_report(parent)
                expected_edl = select_edit_decision(parent_report, request["planId"])
            selected_edl, selection_report, _ = read_creation(self.safe(directory / "selection"))
            if selection_report != parent_report or selected_edl != expected_edl:
                raise ValueError("Selection belongs to another request")
            receipt = self.read(receipt_path)
            if (
                receipt.get("width") != request["width"]
                or receipt.get("height") != request["height"]
            ):
                raise ValueError("Render dimensions changed")
            if receipt.get("audioMix", AudioMix().to_json()) != audio_mix.to_json():
                raise ValueError("Render audio configuration changed")
            music = (
                None
                if audio_mix.bgm is None
                else MusicLibrary(self.repository).resolve(
                    audio_mix.bgm.track_id, audio_mix.bgm.track_receipt_sha256
                )
            )
            if receipt.get("music") != (None if music is None else music.public()):
                raise ValueError("Render music identity changed")
            selection = self.safe(directory / "selection/receipt.json")
            if receipt.get("creationReceiptSha256") != hash_file(selection):
                raise ValueError("Render belongs to another selection")
            mode = request.get("subtitleMode", "none")
            if mode not in ("none", "sidecar", "burn"):
                raise ValueError("Invalid saved subtitle mode")
            subtitles = receipt.get("subtitles")
            expected_files = {"video.mp4"}
            if mode != "none":
                expected_files.add("subtitles.srt")
            if subtitles is not None or mode != "none":
                if (
                    not isinstance(subtitles, dict)
                    or subtitles.get("mode") != mode
                    or type(subtitles.get("cueCount")) is not int
                    or subtitles["cueCount"] < 0
                ):
                    raise ValueError("Invalid subtitle receipt")
            video = self.safe(directory / "result/video.mp4")
            if (
                receipt.get("schemaVersion") != "creation-render-receipt-v1"
                or receipt.get("status") != "completed"
                or set(receipt.get("files", {})) != expected_files
            ):
                raise ValueError("Invalid render receipt")
            resource = MediaResource(video, receipt["files"]["video.mp4"], "video/mp4")
            with self.cache.open(resource):
                size = video.stat().st_size
            base = "/api/creation/jobs/" + state["jobId"] + "/video"
            state["artifact"] = {
                "mediaType": "video/mp4",
                "sizeBytes": size,
                "sha256": resource.sha256,
                "previewUrl": base,
                "downloadUrl": base + "?download=1",
            }
            if mode != "none":
                assert isinstance(subtitles, dict)
                subtitle_path = self.safe(directory / "result/subtitles.srt")
                subtitle_hash = receipt["files"]["subtitles.srt"]
                if hash_file(subtitle_path) != subtitle_hash:
                    raise ValueError("Subtitle file changed")
                state["artifact"].update(
                    subtitleMode=mode,
                    subtitleCueCount=subtitles["cueCount"],
                    subtitleSha256=subtitle_hash,
                    subtitleUrl="/api/creation/jobs/" + state["jobId"] + "/subtitles",
                )
        state["resultReceiptSha256"] = digest
        return state

    def execute(
        self,
        directory: Path,
        state: dict[str, Any],
        request: dict[str, Any],
        project: Path,
        owner: ProjectWriterLock,
    ) -> None:
        try:
            state["status"] = "running"
            self.save(directory / "status.json", state)
            from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

            chain = None
            if state["kind"] == "revision" or "revisionJobId" in request:
                chain = load_chain(self, state["parentJobId"], request.get("planId"))
                if chain.digest != self.read(directory / "request.json")["parentReceiptSha256"]:
                    raise ValueError("Parent receipt changed")

            async def check_sources() -> None:
                source_request = (
                    self.read(self.directory(chain.root_id) / "request.json")["request"]
                    if chain is not None
                    else request
                    if state["kind"] == "plan"
                    else self.read(self.directory(state["parentJobId"]) / "request.json")["request"]
                )
                store = await SqliteTimelineStore.open(project, read_only=True)
                try:
                    for run_id in source_request["runIds"]:
                        run = await store.load_run(run_id)
                        if self.root.is_relative_to(resolve_existing(run.asset.source_path.parent)):
                            raise ValueError("Job root is inside an input media directory")
                finally:
                    await store.close()

            if state["kind"] not in ("publication", "package"):
                asyncio.run(check_sources())
            if state["kind"] == "plan":
                asyncio.run(
                    execute_plan_creation(
                        project,
                        request["runIds"],
                        directory / "input/brief.json",
                        directory / "result",
                        [],
                        request["fps"],
                        None,
                    )
                )
            elif state["kind"] == "package":
                asyncio.run(package_jobs.save_package(self, directory, request))
            elif state["kind"] == "publication":
                asyncio.run(publication_jobs.save_publication(self, directory, request))
            elif state["kind"] == "revision":
                assert chain is not None
                save_revision(self, directory, request, chain)
            elif "revisionJobId" in request:
                assert chain is not None
                asyncio.run(render_revision(self, directory, request, chain))
            else:
                parent = self.directory(state["parentJobId"])
                stored = self.read(directory / "request.json")
                if (
                    hash_file(self.safe(parent / "result/receipt.json"))
                    != stored["parentReceiptSha256"]
                ):
                    raise ValueError("Parent receipt changed")
                report = self.plan_report(parent)
                edl = select_edit_decision(report, request["planId"])
                write_creation(
                    directory / "selection",
                    {"plans.json": report, "edit-decision.json": edl},
                    (project,),
                )
                asyncio.run(
                    execute_render_creation(
                        project,
                        directory / "selection",
                        directory / "result",
                        FfmpegCreationRenderer(self.repository),
                        request["width"],
                        request["height"],
                        subtitle_mode=request.get("subtitleMode", "none"),
                    )
                )
            receipt_path = directory / "result/receipt.json"
            receipt = self.read(receipt_path)
            receipt.update(
                jobId=state["jobId"], requestDigest=self.read(directory / "request.json")["digest"]
            )
            self.save(receipt_path, receipt)
            state = self.verify(directory, state)
            state["status"] = "completed"
        except Exception as error:
            state["status"] = "failed"
            state["error"] = {
                "code": "creation.execution_failed",
                "message": "创作任务失败，请检查素材与方案后用新请求重试。",
            }
            if isinstance(error, AppError) and error.code in (
                "media.file_limit",
                "media.scratch_limit",
                "media.disk_space",
            ):
                state["error"] = {"code": error.code, "message": error.message}
        finally:
            state["updatedAt"] = datetime.now(UTC).isoformat()
            try:
                self.save(directory / "status.json", state)
            finally:
                owner.close()

    def get(self, job_id: str) -> dict[str, Any]:
        directory = self.directory(job_id)
        state = self.read(directory / "status.json")
        if state["status"] in {"pending", "running"}:
            owner = ProjectWriterLock(directory)
            try:
                owner.acquire()
            except AppError as error:
                if error.code != "storage.writer_busy":
                    raise
            else:
                try:
                    state = self.read(directory / "status.json")
                    if state["status"] in {"pending", "running"}:
                        try:
                            state = self.verify(directory, state)
                            state["status"] = "completed"
                        except Exception:
                            state["status"] = "interrupted"
                            state["error"] = {
                                "code": "creation.interrupted",
                                "message": "任务执行已中断，请用新请求重新创建。",
                            }
                        state["updatedAt"] = datetime.now(UTC).isoformat()
                        self.save(directory / "status.json", state)
                finally:
                    owner.close()
        if state["status"] == "completed":
            try:
                state = self.verify(directory, state)
            except Exception:
                state["status"] = "failed"
                state["error"] = {
                    "code": "creation.artifact_invalid",
                    "message": "任务产物已更改，不能预览或下载。",
                }
                state.pop("artifact", None)
                state.pop("editor", None)
                state.pop("package", None)
                state.pop("publication", None)
                state.pop("publicationArtifacts", None)
        return {key: value for key, value in state.items() if key != "resultReceiptSha256"}

    def package(self, job_id: str) -> dict[str, Any]:
        state = self.get(job_id)
        if state["kind"] != "package" or state["status"] != "completed":
            raise ValueError("Package unavailable")
        return dict(state["package"])

    def package_file(self, job_id: str, name: str) -> MediaResource:
        return package_jobs.resource(self, job_id, name)

    def publication(self, job_id: str) -> dict[str, Any]:
        return publication_jobs.snapshot(self, job_id)

    def publication_file(self, job_id: str, name: str) -> MediaResource:
        return publication_jobs.resource(self, job_id, name)

    def edit(self, job_id: str, plan_id: str) -> dict[str, Any]:
        return editor(load_chain(self, job_id, plan_id), job_id)

    def catalog(self, project_id: str) -> dict[str, object]:
        self.project(project_id)
        states = [
            self.get(path.name)
            for path in self.jobs.iterdir()
            if path.is_dir() and re.fullmatch("[0-9a-f]{32}", path.name)
        ]
        states = sorted(
            (state for state in states if state["projectId"] == project_id),
            key=lambda state: state["createdAt"],
            reverse=True,
        )
        return {"jobs": states[:100], "truncated": len(states) > 100}

    def video(self, job_id: str) -> MediaResource:
        state = self.get(job_id)
        if state["kind"] != "render" or state["status"] != "completed":
            raise fail("creation.conflict", "任务没有有效成片。", True)
        return MediaResource(
            self.safe(self.directory(job_id) / "result/video.mp4"),
            state["artifact"]["sha256"],
            "video/mp4",
        )

    def subtitles(self, job_id: str) -> MediaResource:
        state = self.get(job_id)
        if (
            state["kind"] != "render"
            or state["status"] != "completed"
            or "subtitleUrl" not in state.get("artifact", {})
        ):
            raise fail("creation.conflict", "任务没有有效字幕。", True)
        return MediaResource(
            self.safe(self.directory(job_id) / "result/subtitles.srt"),
            state["artifact"]["subtitleSha256"],
            "application/x-subrip; charset=utf-8",
        )

    def close(self) -> None:
        for worker in self.threads:
            worker.join(timeout=1)
