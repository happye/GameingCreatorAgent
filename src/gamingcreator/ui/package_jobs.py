"""Immutable single-platform packages of seven public files and a ZIP."""

import asyncio
import ntpath
import os
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.creation_modes import MODE_LABELS
from gamingcreator.application.package_validation import validate_package
from gamingcreator.cli.creation_render import read_creation
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.platform_profile import profile_digest, validate_profile
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.local_paths import is_link, resolve_existing
from gamingcreator.infrastructure.publication_package import encode
from gamingcreator.ui import publication_jobs
from gamingcreator.ui.media import MediaResource

FILES = {
    "video.mp4": "video/mp4",
    "cover.png": "image/png",
    "title.txt": "text/plain; charset=utf-8",
    "description.txt": "text/plain; charset=utf-8",
    "tags.json": "application/json",
    "platform.json": "application/json",
    "validation.json": "application/json",
}
DOWNLOADS = {**FILES, "package.zip": "application/zip"}
PLATFORM_LABELS = {"bilibili": "B站", "douyin": "抖音", "kuaishou": "快手", "xiaohongshu": "小红书"}


def _download_name(title: str, platform: str, content_type: str, job_id: str) -> str:
    label = MODE_LABELS.get(content_type, "创作视频").replace("/", "-")
    clean = "".join(
        " " if char in '<>:"/\\|?*' or unicodedata.category(char).startswith("C") else char
        for char in title
    )
    title = " ".join(clean.split())[:40].strip(". ") or "创作视频"
    filename = f"{title} - {PLATFORM_LABELS[platform]} - {label} - {job_id[:12]}.zip"
    return f"_{filename}" if ntpath.isreserved(filename) else filename


def profiles() -> dict[str, Any]:
    from gamingcreator.infrastructure.platform_preset_loader import load_platform_profiles

    return {"profiles": load_platform_profiles()}


def parent(
    jobs: Any, request: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    directory = jobs.directory(request["publicationJobId"])
    state = jobs.read(directory / "status.json")
    if state.get("kind") != "publication" or state.get("status") != "completed":
        raise ValueError("Package requires completed publication")
    state = jobs.verify(directory, state)
    if state["resultReceiptSha256"] != request["expectedPublicationReceiptSha256"]:
        raise ValueError("Publication receipt changed")
    publication = state["publication"]
    _, render, _ = publication_jobs.render_parent(jobs, publication["renderJobId"])
    profiles = request["profiles"] if "profiles" in request else [request["profile"]]
    for profile in profiles:
        fields = profile["Fields"]
        variant = fields.get("variant")
        frames = render["frames"] if variant is None else variant["durationFrames"]
        if variant is not None and frames >= render["frames"]:
            raise ValueError("短版帧数必须少于原成片帧数。")
        if variant is not None:
            ranges = variant.get("ranges")
            end = ranges[-1]["endFrame"] if ranges else variant.get("startFrame", 0) + frames
            if end > render["frames"]:
                raise ValueError("短版区间超出原成片。")
        if frames < 2 and len(fields.get("publicationText", {})) == 2:
            raise ValueError("成片至少需要两帧才能同时显示开场和结尾。")
    return state, publication, render


def prepare(jobs: Any, request: dict[str, Any]) -> tuple[str, str]:
    validate_profile(request["profile"])
    state, _, _ = parent(jobs, request)
    return state["projectId"], state["resultReceiptSha256"]


async def save_package(jobs: Any, directory: Path, request: dict[str, Any]) -> None:
    profile = validate_profile(request["profile"])
    state, publication, render = await asyncio.to_thread(parent, jobs, request)
    target = jobs.safe(directory / "result")
    target.mkdir()
    source = jobs.directory(request["publicationJobId"]) / "result"
    video = jobs.safe(jobs.directory(publication["renderJobId"]) / "result/video.mp4")
    watermark = render.get("watermark")
    fields = profile["Fields"]
    variant = fields.get("variant")
    publication_text = "publicationText" in fields
    frames = render["frames"] if variant is None else variant["durationFrames"]
    fps = Fraction(render["fpsNumerator"], render["fpsDenominator"])
    duration = frames / fps
    encode_options = (
        {"output_clock": (frames, fps)} if variant is not None or publication_text else {}
    )
    facts = await encode(
        jobs.repository,
        video,
        jobs.safe(source / "cover.png"),
        target,
        profile,
        watermark,
        duration,
        **encode_options,
    )
    validation = _validate_output(profile, facts, publication, render)
    for name in ("title.txt", "description.txt", "tags.json"):
        jobs.safe(target / name).write_bytes(jobs.safe(source / name).read_bytes())
    jobs.save(
        target / "platform.json", {"profile": profile, "profileSha256": profile_digest(profile)}
    )
    jobs.save(target / "validation.json", validation)
    with zipfile.ZipFile(jobs.safe(target / "package.zip"), "x", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(jobs.safe(target / name), name)
    current, _, current_render = await asyncio.to_thread(parent, jobs, request)
    if current["resultReceiptSha256"] != state["resultReceiptSha256"] or current_render != render:
        raise ValueError("Parent changed during encoding")
    jobs.save(
        target / "receipt.json",
        {
            "schemaVersion": "creation-package-receipt-v1",
            "status": "completed",
            "profileSha256": profile_digest(profile),
            "parentPublicationReceiptSha256": state["resultReceiptSha256"],
            "parentRenderReceiptSha256": publication["expectedRenderReceiptSha256"],
            "renderVideoSha256": render["files"]["video.mp4"],
            "watermark": watermark,
            "facts": facts,
            "files": {name: hash_file(jobs.safe(target / name)) for name in DOWNLOADS},
        },
    )


def verify(
    jobs: Any,
    directory: Path,
    state: dict[str, Any],
    stored: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    request = stored["request"]
    profile = validate_profile(request["profile"])
    parent_state, publication, render = parent(jobs, request)
    if (
        state["parentJobId"] != request["publicationJobId"]
        or state["projectId"] != parent_state["projectId"]
        or stored["parentReceiptSha256"] != parent_state["resultReceiptSha256"]
        or receipt.get("schemaVersion") != "creation-package-receipt-v1"
        or receipt.get("status") != "completed"
        or receipt.get("profileSha256") != profile_digest(profile)
        or receipt.get("parentPublicationReceiptSha256") != parent_state["resultReceiptSha256"]
        or receipt.get("parentRenderReceiptSha256") != publication["expectedRenderReceiptSha256"]
        or receipt.get("renderVideoSha256") != render["files"]["video.mp4"]
        or set(receipt.get("files", {})) != set(DOWNLOADS)
        # Missing watermark on old packages/renders is None; a mismatch is tampering.
        or receipt.get("watermark") != render.get("watermark")
    ):
        raise ValueError("Package identity changed")
    target = directory / "result"
    for name in DOWNLOADS:
        path = target / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"缺少平台包文件 {name}")
        if hash_file(jobs.safe(path)) != receipt["files"][name]:
            raise ValueError(f"平台包文件 {name} 已损坏")
    if jobs.read(target / "platform.json") != {
        "profile": profile,
        "profileSha256": profile_digest(profile),
    }:
        raise ValueError("Profile changed")
    validation = _validate_output(profile, receipt["facts"], publication, render)
    if jobs.read(target / "validation.json") != validation:
        raise ValueError("Validation changed")
    selection = jobs.directory(publication["renderJobId"]) / "selection"
    _, report, selection_digest = read_creation(jobs.safe(selection))
    if selection_digest != render["creationReceiptSha256"]:
        raise ValueError("Render selection changed")
    state["package"] = {
        "publicationJobId": request["publicationJobId"],
        "expectedPublicationReceiptSha256": request["expectedPublicationReceiptSha256"],
        "profile": profile,
        "generationStatus": "completed",
        "localChecks": validation["localChecks"],
        "publicationEligibility": validation["publicationEligibility"],
        "validation": validation,
        "watermark": receipt.get("watermark"),
        "localPath": str(jobs.safe(target / "package.zip")),
        "downloadName": _download_name(
            publication["title"],
            profile["Platform"],
            report["brief"]["contentType"],
            directory.name,
        ),
        "artifacts": {
            name: {
                "url": f"/api/creation/jobs/{directory.name}/package-files/{name}",
                "sha256": receipt["files"][name],
                "mediaType": DOWNLOADS[name],
            }
            for name in DOWNLOADS
        },
    }


def _validate_output(
    profile: dict[str, Any],
    facts: dict[str, Any],
    publication: dict[str, Any],
    render: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_package(profile, facts, publication, render)
    checks = validation["checks"]
    if (checks["frames"], checks["fps"]) != ("pass", "pass"):
        if "variant" in profile["Fields"]:
            raise ValueError("短版实测帧数或帧率与原成片时钟不符。")
        if "publicationText" in profile["Fields"]:
            raise ValueError("平台包实测帧数或帧率与预期输出时钟不符。")
    return validation


def _completed(jobs: Any, job_id: str) -> dict[str, Any]:
    state: dict[str, Any] = jobs.get(job_id)
    if state["kind"] != "package" or state["status"] != "completed":
        error = state.get("error") or {}
        if error.get("code") == "creation.artifact_invalid":
            raise AppError(
                "creation.artifact_invalid",
                str(error.get("message") or "任务产物已更改，不能预览或下载。"),
                ExitCode.STORAGE,
            )
        raise ValueError("Package unavailable")
    return state


@dataclass(frozen=True, slots=True)
class PackageResource(MediaResource):
    download_name: str


def resource(jobs: Any, job_id: str, name: str) -> PackageResource:
    if name not in DOWNLOADS:
        raise ValueError("Unknown package file")
    package = _completed(jobs, job_id)["package"]
    return PackageResource(
        jobs.safe(jobs.directory(job_id) / "result" / name),
        package["artifacts"][name]["sha256"],
        DOWNLOADS[name],
        package["downloadName"] if name == "package.zip" else name,
    )


def _export_path(path: Path, repository: Path) -> Path:
    if resolve_existing(path) != path or any(
        is_link(entry) for entry in (path, *path.parents) if entry.is_relative_to(repository)
    ):
        raise AppError("creation.package_export", "导出位置不能使用链接。", ExitCode.STORAGE)
    return path


def export(jobs: Any, project_id: str, job_id: str) -> dict[str, object]:
    project = jobs.project(project_id)
    state = _completed(jobs, job_id)
    if state["projectId"] != project_id:
        raise AppError("creation.not_found", "找不到此项目的平台包。", ExitCode.INPUT)
    package = state["package"]
    directory = jobs.repository / project_id / "exports"
    if directory.parent != project:
        raise AppError("creation.package_export", "导出项目位置已更改。", ExitCode.STORAGE)
    filename = package["downloadName"]
    target = directory / filename
    digest = package["artifacts"]["package.zip"]["sha256"]
    result = {"filename": filename, "path": str(target), "directory": str(directory)}
    try:
        directory = _export_path(directory, jobs.repository)
        directory.mkdir(exist_ok=True)
        temporary = directory / f".{uuid4().hex}.tmp"
        _export_path(target, jobs.repository)
        if not target.exists():
            source = jobs.safe(Path(package["localPath"]))
            try:
                with temporary.open("xb") as output, source.open("rb") as original:
                    shutil.copyfileobj(original, output, length=1024 * 1024)
                if hash_file(temporary) != digest:
                    raise AppError(
                        "creation.artifact_invalid",
                        "平台包文件 package.zip 已损坏。",
                        ExitCode.STORAGE,
                    )
                _export_path(target, jobs.repository)
                try:
                    # Windows rename fails if the target exists. POSIX rename replaces it.
                    if os.name == "nt":
                        temporary.rename(target)
                    else:
                        os.link(temporary, target)
                except FileExistsError:
                    pass
            finally:
                _export_path(temporary, jobs.repository).unlink(missing_ok=True)
        if not _export_path(target, jobs.repository).is_file() or hash_file(target) != digest:
            raise AppError(
                "creation.package_export",
                "导出目录已有同名文件，内容与平台包不同。",
                ExitCode.STORAGE,
            )
    except OSError as error:
        raise AppError(
            "creation.package_export", "无法写入项目的 exports 文件夹。", ExitCode.STORAGE
        ) from error
    return result
