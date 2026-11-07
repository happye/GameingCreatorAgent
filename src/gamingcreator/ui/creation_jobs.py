"""Persistent local creation jobs; OS ownership, not saved status, proves liveness."""

import asyncio
import hashlib
import json
import re
import shutil
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.creation_feedback import (
    normalize_edit_kinds,
    plan_preferences,
    summarize_feedback,
)
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.narration import NarrationRequest
from gamingcreator.application.narration_script import build_narration_script
from gamingcreator.application.providers import CancellationContext
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
from gamingcreator.ui import narration_jobs, package_jobs, publication_jobs
from gamingcreator.ui.media import MediaResource, VerifiedMediaCache
from gamingcreator.ui.revision_jobs import (
    editable_clips as version_clips,
)
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
        self.narration_contexts: dict[
            str, tuple[CancellationContext, asyncio.AbstractEventLoop | None]
        ] = {}
        self.narration_cancel_requests: set[str] = set()
        self.narration_lock = threading.Lock()
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
        if kind not in (
            "plan",
            "revision",
            "render",
            "publication",
            "package",
            "narration",
        ) or not isinstance(request, dict):
            raise fail("creation.input", "无效任务类型。")
        expected = {"requestId", "projectId", "runIds", "brief", "fps"}
        if kind == "narration":
            expected = {"requestId", "projectId", "text", "voiceId"}
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
            {"subtitleMode", "safeAreaMarginPercent", "badgeText", "badgeCorner"}
            if kind == "render"
            else (
                {
                    "subtitleOverrides",
                    "audioMix",
                    "candidateManifestSha256",
                    "replacements",
                    "narration",
                    "overlays",
                }
                if kind == "revision"
                else {"costConfirmationYuan"}
                if kind == "narration"
                else {"eventIds", "clipRanges", "reasoningPreparedHash"}
                if kind == "plan"
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
        if kind == "render":
            try:
                from gamingcreator.domain.creation_presentation import PresentationOptions

                PresentationOptions.from_request(request)
            except ValueError as error:
                raise fail("creation.input", str(error)) from error
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
            # A repeated request above stays idempotent; only new work counts against a plan.
            self.check_entitlement(kind, request)
            parent_id = None
            parent_digest = None
            if kind == "narration":
                project = self.project(request["projectId"])
                NarrationRequest(
                    request_id, request["projectId"], request["text"], request["voiceId"]
                )
                try:
                    reused = narration_jobs.paid_gate(self, request)
                except ValueError as error:
                    raise fail("creation.input", str(error)) from error
                if reused is not None:
                    return {"jobId": reused, "kind": "narration", "status": "completed"}
                project_id = request["projectId"]
            elif kind == "plan":
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
                # A clip basket: plans may use only these analysed events (ids carry their run).
                events = request.get("eventIds", [])
                if (
                    not isinstance(events, list)
                    or ("eventIds" in request and not events)
                    or len(events) > 500
                    or any(not isinstance(e, str) or not e for e in events)
                    or len(events) != len(set(events))
                    or any(e.split(":", 1)[0] not in runs for e in events)
                ):
                    raise fail("creation.input", "片段篮里的片段无效，或不属于所选录像。")
                if "clipRanges" in request:
                    from gamingcreator.application.creative_planner import validate_clip_ranges

                    try:
                        if not isinstance(request["clipRanges"], list):
                            raise ValueError("Clip ranges must be a list.")
                        validate_clip_ranges(request["clipRanges"], tuple(events))
                    except ValueError as error:
                        raise fail("creation.input", str(error)) from error
                if "reasoningPreparedHash" in request:
                    from gamingcreator.ui.plan_reasoning_jobs import verified_plan

                    verified_plan(self, request)
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
                    frames = (
                        revised["segments"][-1]["outputStartFrame"]
                        + revised["segments"][-1]["outputFrames"]
                    )
                    from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary
                    from gamingcreator.ui.overlay_jobs import resolve_selection

                    resolve_selection(
                        OverlayAssetLibrary(self.repository), request, chain.overlays, frames
                    )
                    narration_jobs.resolve(
                        self, request, chain.narration, chain.project_id, frames, chain.plan.fps
                    )
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
                if kind == "render":
                    from gamingcreator.application.entitlements import watermark_for

                    # Decided once at registration, so a later plan change never alters a job.
                    state["watermark"] = watermark_for(self.entitlement_selection())
                self.save(
                    directory / "request.json",
                    {"request": request, "digest": digest, "parentReceiptSha256": parent_digest},
                )
                if kind == "plan":
                    (directory / "input").mkdir()
                    self.save(directory / "input/brief.json", request["brief"])
                    # Captured once, so re-running the job never depends on later history.
                    try:
                        summary = self.feedback(request["projectId"])
                        preferences = plan_preferences(summary)
                        edit_kinds = normalize_edit_kinds(summary.get("editKinds"))
                    except Exception:
                        preferences, edit_kinds = {}, {}  # Statistics never block planning.
                    self.save(directory / "input/preferences.json", preferences)
                    self.save(
                        directory / "input/edit-habits.json",
                        {"schemaVersion": "creation-edit-habits-v1", "editKinds": edit_kinds},
                    )
                self.save(directory / "status.json", state)
                self.save(registration, {"digest": digest, "jobId": job_id})
                if kind == "narration":
                    with self.narration_lock:
                        self.narration_contexts[job_id] = (CancellationContext(job_id, 3600), None)
                worker = threading.Thread(
                    target=self.execute,
                    args=(directory, state, request, project, owner),
                    daemon=True,
                )
                self.threads.append(worker)
                worker.start()
            except BaseException:
                with self.narration_lock:
                    self.narration_contexts.pop(job_id, None)
                    self.narration_cancel_requests.discard(job_id)
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
        if state["kind"] == "narration":
            narration_jobs.verify_asset(self, directory, state, stored)
        elif state["kind"] == "plan":
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
            narration = None
            expected_overlays = None
            if "revisionJobId" in request:
                chain = load_chain(self, parent_id)
                parent_report, expected_edl = chain.report, chain.edl
                audio_mix = chain.audio_mix
                narration = chain.narration
                expected_overlays = chain.overlays.to_json() if chain.overlays.items else None
                if state["projectId"] != chain.project_id:
                    raise ValueError("Render project changed")
            else:
                parent_report = self.plan_report(parent)
                expected_edl = select_edit_decision(parent_report, request["planId"])
            selected_edl, selection_report, _ = read_creation(self.safe(directory / "selection"))
            if selection_report != parent_report or selected_edl != expected_edl:
                raise ValueError("Selection belongs to another request")
            receipt = self.read(receipt_path)
            if receipt.get("overlays") != expected_overlays:
                raise ValueError("Render overlay selection changed")
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
            if narration is not None:
                from gamingcreator.infrastructure.narration_mix import narration_receipt

                narration_asset = narration_jobs.asset(self, narration, state["projectId"])
                if receipt.get("narration") != narration_receipt(
                    narration, narration_asset, receipt["fpsNumerator"]
                ):
                    raise ValueError("Render narration identity changed")
                expected_files.add("narration.txt")
                text = self.safe(directory / "result/narration.txt")
                if (
                    hash_file(text) != narration_asset.text_sha256
                    or receipt["files"].get("narration.txt") != narration_asset.text_sha256
                ):
                    raise ValueError("Render narration text changed")
            elif "narration" in receipt:
                raise ValueError("Render contains unselected narration")
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
            if receipt.get("watermark") != state.get("watermark"):
                raise ValueError("Watermark record mismatch")
            if state.get("watermark") is not None:
                state["artifact"]["watermark"] = state["watermark"]
            if narration is not None:
                state["artifact"].update(
                    narrationTextUrl=f"/api/creation/jobs/{state['jobId']}/narration-text",
                    narrationTextSha256=receipt["files"]["narration.txt"],
                )
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

            if state["kind"] not in ("publication", "package", "narration"):
                asyncio.run(check_sources())
            if state["kind"] == "narration":
                asyncio.run(narration_jobs.generate(self, directory, request))
            elif state["kind"] == "plan" and "reasoningPreparedHash" in request:
                from gamingcreator.ui.plan_reasoning_jobs import save_plan

                save_plan(self, directory, request)
            elif state["kind"] == "plan":
                asyncio.run(
                    execute_plan_creation(
                        project,
                        request["runIds"],
                        directory / "input/brief.json",
                        directory / "result",
                        list(request.get("eventIds", [])),
                        request["fps"],
                        None,
                        preferences=self._preferences(directory),
                        edit_kinds=self._edit_habits(directory),
                        **(
                            {"clip_ranges": request["clipRanges"]}
                            if "clipRanges" in request
                            else {}
                        ),
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
                asyncio.run(
                    render_revision(self, directory, request, chain, state.get("watermark"))
                )
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
                from gamingcreator.domain.creation_presentation import PresentationOptions

                asyncio.run(
                    execute_render_creation(
                        project,
                        directory / "selection",
                        directory / "result",
                        FfmpegCreationRenderer(self.repository),
                        request["width"],
                        request["height"],
                        subtitle_mode=request.get("subtitleMode", "none"),
                        watermark=state.get("watermark"),
                        presentation=PresentationOptions.from_request(request),
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
        except asyncio.CancelledError:
            state["status"] = "interrupted"
            state["error"] = {"code": "creation.cancelled", "message": "本地旁白生成已取消。"}
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
                if state["kind"] == "narration":
                    with self.narration_lock:
                        if (
                            directory.name in self.narration_cancel_requests
                            or (directory / "cancel-requested.json").exists()
                        ) and state["status"] == "completed":
                            state["status"] = "interrupted"
                            state.pop("narrationAsset", None)
                            # A cancelled asset is never attachable; drop its owned files.
                            with suppress(Exception):
                                shutil.rmtree(self.safe(directory / "result"))
                            state["error"] = {
                                "code": "creation.cancelled",
                                "message": "本地旁白生成已取消。",
                            }
                        self.save(directory / "status.json", state)
                        self.narration_contexts.pop(directory.name, None)
                        self.narration_cancel_requests.discard(directory.name)
                else:
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
                            if (directory / "cancel-requested.json").exists():
                                raise ValueError("Cancellation was accepted before the crash")
                            state = self.verify(directory, state)
                            state["status"] = "completed"
                        except Exception:
                            state["status"] = "interrupted"
                            state.pop("narrationAsset", None)
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

    def _enterprise_dir(self) -> Path:
        path = self.root / "enterprise"
        path.mkdir(exist_ok=True)
        (path / "teams").mkdir(exist_ok=True)
        (path / "audit").mkdir(exist_ok=True)
        return path

    def _team_path(self, project_id: str) -> Path:
        from gamingcreator.application.enterprise import project_team_key

        return self._enterprise_dir() / "teams" / f"{project_team_key(project_id)}.json"

    def _audit_path(self, project_id: str) -> Path:
        from gamingcreator.application.enterprise import project_team_key

        return self._enterprise_dir() / "audit" / f"{project_team_key(project_id)}.jsonl"

    def team(self, project_id: object) -> dict[str, Any] | None:
        """Team for one project; falls back read-only to the pre-T10 global file if needed."""
        self.project(project_id)
        path = self._team_path(str(project_id))
        if path.is_file():
            return self.read(path)
        legacy = self.root / "enterprise-team.json"
        return self.read(legacy) if legacy.is_file() else None

    @contextmanager
    def root_writer(self) -> Iterator[None]:
        """The creations-root writer lock, waited for briefly like job registration does."""
        lock = ProjectWriterLock(self.root)
        for attempt in range(100):
            try:
                lock.acquire()
                break
            except AppError as error:
                if error.code != "storage.writer_busy" or attempt == 99:
                    raise
                time.sleep(0.01)
        try:
            yield
        finally:
            lock.close()

    def set_team(self, project_id: object, value: object, actor: object) -> dict[str, Any]:
        from gamingcreator.application.enterprise import PERMISSIONS, role_of, validate_team

        self.project(project_id)
        project = str(project_id)
        with self.root_writer():
            current = self.team(project)
            try:
                team = validate_team(value)
                if (
                    current is not None
                    and role_of(current, str(actor)) not in PERMISSIONS["edit_team"]
                ):
                    raise PermissionError("只有负责人可以修改团队设置。")
                if current is None and role_of(team, str(actor)) != "owner":
                    raise PermissionError("创建团队的人必须是负责人。")
            except (PermissionError, ValueError) as error:
                raise fail("enterprise.input", str(error)) from error
            self.save(self._team_path(project), team)
            self._append_audit(
                project,
                {
                    "kind": "team_change",
                    "at": datetime.now(UTC).isoformat(),
                    "projectId": project,
                    "actor": str(actor),
                    "actorSelfReported": True,
                    "action": "set_team",
                    "before": current,
                    "after": team,
                    "note": "操作人姓名自报，不是登录账号",
                },
            )
            return team

    def review(
        self, package_job_id: str, actor: object, action: object, comment: object
    ) -> dict[str, Any]:
        from gamingcreator.application.enterprise import apply_review, check_brand

        package_job_id = identity(package_job_id)
        project = str(self.read(self.directory(package_job_id) / "status.json")["projectId"])
        with self.root_writer():
            team = self.team(project)
            if team is None:
                raise fail("enterprise.input", "请先设置该项目的团队成员。")
            texts = self._package_texts(package_job_id)
            reviews = self.root / "reviews"
            reviews.mkdir(exist_ok=True)
            path = reviews / f"{package_job_id}.json"
            record = self.read(path) if path.is_file() else None
            when = datetime.now(UTC).isoformat()
            try:
                updated = apply_review(
                    team,
                    record,
                    str(actor),
                    str(action),
                    comment if isinstance(comment, str) else "",
                    check_brand(team, texts),
                    when,
                )
            except (PermissionError, ValueError) as error:
                raise fail("enterprise.review", str(error)) from error
            self.save(path, updated)
            last = updated["events"][-1]
            self._append_audit(
                project,
                {
                    "kind": "review",
                    "at": when,
                    "projectId": project,
                    "packageJobId": package_job_id,
                    "actor": str(actor),
                    "actorSelfReported": True,
                    "action": str(action),
                    "state": updated["state"],
                    "comment": last.get("comment") or "",
                    "brandIssues": list(last.get("brandIssues") or []),
                    "note": "操作人姓名自报，不是登录账号",
                },
            )
            return updated

    def _package_texts(self, package_job_id: str) -> dict[str, str]:
        self.package(package_job_id)  # re-verifies the package files and receipts
        result = self.safe(self.directory(package_job_id) / "result")
        return {
            "标题": (result / "title.txt").read_text(encoding="utf-8"),
            "简介": (result / "description.txt").read_text(encoding="utf-8"),
            "标签": " ".join(json.loads((result / "tags.json").read_text(encoding="utf-8"))),
        }

    def publish_blockers(self, package_job_id: str) -> list[str]:
        from gamingcreator.application.enterprise import check_brand, publish_blockers

        package_job_id = identity(package_job_id)
        project = str(self.read(self.directory(package_job_id) / "status.json")["projectId"])
        team = self.team(project)
        if team is None or not team["reviewRequired"]:
            return []
        record = self.review_state(package_job_id)
        issues = check_brand(team, self._package_texts(package_job_id))
        return publish_blockers(team, record, issues)

    def review_state(self, package_job_id: str) -> dict[str, Any] | None:
        path = self.root / "reviews" / f"{identity(package_job_id)}.json"
        return self.read(path) if path.is_file() else None

    def _append_audit(self, project_id: str, row: dict[str, Any]) -> None:
        path = self._audit_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def audit_rows(self, project_id: object) -> list[dict[str, Any]]:
        from gamingcreator.application.enterprise import merge_audit_rows, review_events_as_audit

        self.project(project_id)
        project = str(project_id)
        appended: list[dict[str, Any]] = []
        path = self._audit_path(project)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    appended.append(row)
        from_reviews: list[dict[str, Any]] = []
        for directory in self.jobs.iterdir():
            if not directory.is_dir() or re.fullmatch("[0-9a-f]{32}", directory.name) is None:
                continue
            try:
                state = self.read(directory / "status.json")
            except (OSError, ValueError, AppError):
                continue
            if state.get("kind") != "package" or state.get("projectId") != project:
                continue
            record = self.review_state(directory.name)
            if record:
                from_reviews.extend(review_events_as_audit(project, directory.name, record))
        return merge_audit_rows(appended, from_reviews)

    def export_audit(self, project_id: object, fmt: object) -> tuple[str, str, str]:
        from gamingcreator.application.enterprise import audit_as_csv, audit_as_json

        rows = self.audit_rows(project_id)
        if fmt == "csv":
            return audit_as_csv(rows), "enterprise-audit.csv", "text/csv; charset=utf-8"
        if fmt == "json":
            return audit_as_json(rows), "enterprise-audit.json", "application/json; charset=utf-8"
        raise fail("enterprise.input", "审计导出格式只能是 json 或 csv。")

    def entitlement_selection(self) -> dict[str, Any] | None:
        path = self.root / "entitlement.json"
        return self.read(path) if path.is_file() else None

    def select_plan(self, plan: object) -> dict[str, Any]:
        from gamingcreator.application.entitlements import PLANS

        if not isinstance(plan, str) or plan not in PLANS:
            raise fail("entitlement.input", "未知套餐。")
        selection = {
            "plan": plan,
            "selectedAt": datetime.now(UTC).isoformat(),
            "billing": "none-local-evaluation",
        }
        self.save(self.root / "entitlement.json", selection)
        return self.entitlement_summary()

    def _statuses(self) -> list[dict[str, Any]]:
        states = []
        for directory in self.jobs.iterdir():
            if directory.is_dir() and re.fullmatch("[0-9a-f]{32}", directory.name):
                try:
                    states.append({**self.read(directory / "status.json"), "directory": directory})
                except (OSError, ValueError, AppError):
                    continue
        return states

    def entitlement_summary(self) -> dict[str, Any]:
        from gamingcreator.application.entitlements import renders_this_month, summary
        from gamingcreator.infrastructure.entitlement_usage import (
            preparation_minutes_this_month,
        )

        used = renders_this_month(self._statuses(), datetime.now(UTC).isoformat())
        preparation = preparation_minutes_this_month(self.root)
        return summary(
            self.entitlement_selection(),
            used,
            preparation_minutes_used=preparation,
        )

    def check_entitlement(self, kind: str, request: dict[str, Any]) -> None:
        from gamingcreator.application.entitlements import (
            EntitlementError,
            renders_this_month,
            require_package_platform,
            require_render,
        )

        selection = self.entitlement_selection()
        try:
            if kind == "render":
                used = renders_this_month(self._statuses(), datetime.now(UTC).isoformat())
                require_render(selection, used)
            elif kind == "package":
                profile = request.get("profile")
                if not isinstance(profile, dict):
                    raise fail("creation.input", "平台设置无效。")
                # One finished video, many copy versions: platforms count per render.
                states = self._statuses()
                render_of = {
                    s["directory"].name: s.get("parentJobId")
                    for s in states
                    if s.get("kind") == "publication"
                }
                target = render_of.get(str(request.get("publicationJobId")))
                platforms = set()
                for state in states:
                    if (
                        state.get("kind") == "package"
                        and target is not None
                        and render_of.get(str(state.get("parentJobId"))) == target
                        and state.get("status") in ("pending", "running", "completed")
                    ):
                        stored = self.read(state["directory"] / "request.json")["request"]
                        platforms.add(stored["profile"].get("Platform"))
                require_package_platform(selection, platforms, str(profile.get("Platform")))
        except EntitlementError as error:
            raise fail("entitlement.denied", str(error)) from error

    def feedback(self, project_id: str) -> dict[str, object]:
        """Read-only usage statistics from saved records; videos are not re-hashed here.

        A project-level cache under ``feedback-cache/`` is keyed by the SHA-256 of all
        contributing file contents (not mtime/TTL). Cache hits still re-read those bytes to
        verify the fingerprint, but skip JSON parse and summarization.
        """
        self.project(project_id)
        fingerprint, records = self._feedback_scan(project_id)
        cache_dir = self.root / "feedback-cache"
        cache_dir.mkdir(exist_ok=True)
        cache_path = cache_dir / (hashlib.sha256(project_id.encode("utf-8")).hexdigest() + ".json")
        try:
            if cache_path.is_file():
                cached = self.read(cache_path)
                if (
                    cached.get("schemaVersion") == "creation-feedback-cache-v1"
                    and cached.get("projectId") == project_id
                    and cached.get("fingerprint") == fingerprint
                    and isinstance(cached.get("summary"), dict)
                ):
                    summary: dict[str, object] = cached["summary"]
                    return summary
        except (OSError, ValueError, AppError):
            pass  # Corrupt cache must not block statistics.
        summary = summarize_feedback(records)
        try:
            self.save(
                cache_path,
                {
                    "schemaVersion": "creation-feedback-cache-v1",
                    "projectId": project_id,
                    "fingerprint": fingerprint,
                    "summary": summary,
                },
            )
        except (OSError, ValueError, AppError):
            pass  # Statistics remain available even when the cache cannot be written.
        return summary

    def _feedback_scan(self, project_id: str) -> tuple[str, list[dict[str, Any]]]:
        """Return content fingerprint and parsed records for one project."""
        digest = hashlib.sha256()
        digest.update(project_id.encode("utf-8"))
        records: list[dict[str, Any]] = []
        for directory in sorted(self.jobs.iterdir(), key=lambda item: item.name):
            if not directory.is_dir() or re.fullmatch("[0-9a-f]{32}", directory.name) is None:
                continue
            try:
                payload = self._feedback_job_payload(directory, project_id)
            except (OSError, ValueError, AppError):
                continue  # An unreadable record is left out of the statistics, not guessed.
            if payload is None:
                continue
            job_digest, record = payload
            digest.update(directory.name.encode("ascii"))
            digest.update(bytes.fromhex(job_digest))
            records.append(record)
        return digest.hexdigest(), records

    def _feedback_job_payload(
        self, directory: Path, project_id: str
    ) -> tuple[str, dict[str, Any]] | None:
        """Hash and parse one completed job; ``None`` if it is out of scope for this project."""
        status_path = directory / "status.json"
        request_path = directory / "request.json"
        status_bytes = retry_file_sharing(lambda: status_path.read_bytes(), reading=True)
        state = json.loads(status_bytes.decode("utf-8"))
        if not isinstance(state, dict):
            raise ValueError("Invalid job document")
        if state.get("projectId") != project_id or state.get("status") != "completed":
            return None
        request_bytes = retry_file_sharing(lambda: request_path.read_bytes(), reading=True)
        request_document = json.loads(request_bytes.decode("utf-8"))
        if not isinstance(request_document, dict):
            raise ValueError("Invalid job document")
        parts = [b"status.json", status_bytes, b"request.json", request_bytes]
        record: dict[str, Any] = {
            "jobId": directory.name,
            "kind": state.get("kind"),
            "status": state.get("status"),
            "createdAt": state.get("createdAt", ""),
            "request": request_document.get("request", {}),
        }
        if record["kind"] == "plan":
            plans_path = directory / "result/plans.json"
            plans_bytes = retry_file_sharing(lambda: plans_path.read_bytes(), reading=True)
            plans_document = json.loads(plans_bytes.decode("utf-8"))
            if not isinstance(plans_document, dict):
                raise ValueError("Invalid job document")
            parts.extend([b"result/plans.json", plans_bytes])
            record["plans"] = plans_document.get("plans", [])
        elif record["kind"] == "revision":
            root_path = directory / "result/revision.json"
            edl_path = directory / "result/edit-decision.json"
            root_bytes = retry_file_sharing(lambda: root_path.read_bytes(), reading=True)
            edl_bytes = retry_file_sharing(lambda: edl_path.read_bytes(), reading=True)
            root_document = json.loads(root_bytes.decode("utf-8"))
            edl_document = json.loads(edl_bytes.decode("utf-8"))
            if not isinstance(root_document, dict) or not isinstance(edl_document, dict):
                raise ValueError("Invalid job document")
            parts.extend(
                [b"result/revision.json", root_bytes, b"result/edit-decision.json", edl_bytes]
            )
            record["root"] = root_document
            record["segments"] = edl_document.get("segments", [])
        job_digest = hashlib.sha256()
        for part in parts:
            job_digest.update(part)
        return job_digest.hexdigest(), record

    def _preferences(self, directory: Path) -> dict[str, int] | None:
        path = directory / "input/preferences.json"
        if not path.is_file():
            return None  # Jobs registered before feedback ordering keep template order.
        value = self.read(path)
        return {k: v for k, v in value.items() if isinstance(k, str) and type(v) is int}

    def _edit_habits(self, directory: Path) -> dict[str, int] | None:
        path = directory / "input/edit-habits.json"
        if not path.is_file():
            return None  # Pre-T9 plan jobs never applied trim suggestions.
        value = self.read(path)
        kinds = value.get("editKinds") if isinstance(value, dict) else value
        return normalize_edit_kinds(kinds)

    def timeline_export(
        self, job_id: str, plan_id: str, fmt: str, size: str = "1920x1080"
    ) -> tuple[bytes, str, str]:
        from gamingcreator.application.creation_subtitles import build_subtitles
        from gamingcreator.application.timeline_export import (
            ExportCaption,
            captions_from_cues,
            to_fcpxml,
            to_otio,
            to_xmeml,
        )

        width, _, height = size.partition("x")
        if not (width.isdecimal() and height.isdecimal()) or not all(
            16 <= int(v) <= 3840 and int(v) % 2 == 0 for v in (width, height)
        ):
            raise fail("creation.input", "时间线尺寸须为 16–3840 之间的偶数，如 1280x720。")
        chain = load_chain(self, job_id, plan_id)
        name = f"gamingcreator-{job_id[:8]}"
        # Best-effort AV extras; Final Cut / Resolve / Premiere import remains unverified.
        captions: tuple[ExportCaption, ...] = ()
        try:
            runs = {timeline.run.run_id: timeline for timeline in chain.timelines}
            overrides = {item["clipId"]: item["text"] for item in chain.subtitle_overrides}
            cues = build_subtitles(
                chain.plan,
                (),
                per_clip=(runs[row["runId"]].transcripts for row in chain.edl["segments"]),
                overrides=(
                    overrides.get(row["clipId"]) for row in version_clips(chain.edl, chain.root_sha)
                ),
            )
            captions = captions_from_cues(cues, int(chain.edl["fpsNumerator"]))
        except Exception:
            captions = ()
        if fmt == "fcpxml":
            body = to_fcpxml(
                chain.edl,
                name,
                int(width),
                int(height),
                captions=captions,
                include_audio_track=True,
            )
            return body.encode("utf-8"), f"{name}.fcpxml", "application/xml"
        if fmt == "otio":
            return (
                to_otio(chain.edl, name, captions=captions, include_audio_track=True).encode(
                    "utf-8"
                ),
                f"{name}.otio",
                "application/json",
            )
        if fmt == "xmeml":
            return (
                to_xmeml(chain.edl, name, captions=captions, include_audio_track=True).encode(
                    "utf-8"
                ),
                f"{name}-premiere.xml",
                "application/xml",
            )
        raise fail("creation.input", "时间线格式只支持 fcpxml、otio 或 xmeml。")

    def narration_script(self, job_id: str, plan_id: str) -> dict[str, object]:
        from gamingcreator.application.knowledge import search
        from gamingcreator.application.narration_script import knowledge_query
        from gamingcreator.infrastructure.knowledge_store import KnowledgeStore

        chain = load_chain(self, job_id, plan_id)
        brief = CreativeBrief.from_json(chain.report["brief"])
        knowledge = search(
            KnowledgeStore(self.repository).entries(), brief.game, knowledge_query(brief)
        )[:3]
        return build_narration_script(
            brief,
            version_clips(chain.edl, chain.root_sha),
            chain.plan.frames,
            chain.plan.fps,
            knowledge,
        )

    def catalog(self, project_id: str) -> dict[str, object]:
        """List jobs from their status files only.

        Opening a job still runs the full artifact check in ``get``; hashing every saved video
        here made the list take 30-50 seconds once a project had a few dozen renders.
        """
        self.project(project_id)
        states = []
        for path in self.jobs.iterdir():
            if not (path.is_dir() and re.fullmatch("[0-9a-f]{32}", path.name)):
                continue
            state = self.read(path / "status.json")
            if state.get("projectId") != project_id:
                continue
            if state["status"] in {"pending", "running"}:
                # Unfinished jobs may need crash recovery, which get() performs.
                state = self.get(path.name)
            states.append(state)
        states.sort(key=lambda state: state["createdAt"], reverse=True)
        summary = ("jobId", "kind", "status", "createdAt", "updatedAt", "projectId", "error")
        jobs = [{key: state[key] for key in summary if key in state} for state in states[:100]]
        return {"jobs": jobs, "truncated": len(states) > 100}

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

    def voices(self) -> dict[str, Any]:
        return narration_jobs.voices(self.repository)

    def cancel_narration(self, job_id: str) -> dict[str, Any]:
        return narration_jobs.cancel(self, identity(job_id))

    def narration_file(self, job_id: str, name: str) -> MediaResource:
        return narration_jobs.resource(self, identity(job_id), name)

    def narration_text(self, job_id: str) -> MediaResource:
        state = self.get(job_id)
        if (
            state["kind"] != "render"
            or state["status"] != "completed"
            or "narrationTextSha256" not in state.get("artifact", {})
        ):
            raise ValueError("Completed render has no narration text")
        return MediaResource(
            self.safe(self.directory(job_id) / "result/narration.txt"),
            state["artifact"]["narrationTextSha256"],
            "text/plain; charset=utf-8",
        )
