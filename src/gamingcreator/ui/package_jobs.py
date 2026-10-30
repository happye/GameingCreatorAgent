"""Immutable single-platform packages of seven public files and a ZIP."""

import asyncio
import json
import zipfile
from pathlib import Path
from typing import Any

from gamingcreator.application.package_validation import validate_package
from gamingcreator.domain.platform_profile import profile_digest, validate_profile
from gamingcreator.infrastructure.ffmpeg_media import hash_file
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


def profiles() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1] / "infrastructure/platform_presets"
    return {
        "profiles": [
            validate_profile(json.loads((root / (name + ".json")).read_text(encoding="utf-8")))
            for name in ("bilibili", "douyin", "kuaishou", "xiaohongshu")
        ]
    }


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
    return state, publication, render


def prepare(jobs: Any, request: dict[str, Any]) -> tuple[str, str]:
    validate_profile(request["profile"])
    state, _, _ = parent(jobs, request)
    return state["projectId"], state["resultReceiptSha256"]


async def save_package(jobs: Any, directory: Path, request: dict[str, Any]) -> None:
    state, publication, render = await asyncio.to_thread(parent, jobs, request)
    target = jobs.safe(directory / "result")
    target.mkdir()
    profile = validate_profile(request["profile"])
    source = jobs.directory(request["publicationJobId"]) / "result"
    video = jobs.safe(jobs.directory(publication["renderJobId"]) / "result/video.mp4")
    facts = await encode(jobs.repository, video, jobs.safe(source / "cover.png"), target, profile)
    for name in ("title.txt", "description.txt", "tags.json"):
        jobs.safe(target / name).write_bytes(jobs.safe(source / name).read_bytes())
    jobs.save(
        target / "platform.json", {"profile": profile, "profileSha256": profile_digest(profile)}
    )
    validation = validate_package(profile, facts, publication, render)
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
    parent_state, publication, render = parent(jobs, request)
    profile = validate_profile(request["profile"])
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
    ):
        raise ValueError("Package identity changed")
    target = directory / "result"
    for name in DOWNLOADS:
        if hash_file(jobs.safe(target / name)) != receipt["files"][name]:
            raise ValueError("Package artifact changed")
    if jobs.read(target / "platform.json") != {
        "profile": profile,
        "profileSha256": profile_digest(profile),
    }:
        raise ValueError("Profile changed")
    validation = validate_package(profile, receipt["facts"], publication, render)
    if jobs.read(target / "validation.json") != validation:
        raise ValueError("Validation changed")
    state["package"] = {
        "publicationJobId": request["publicationJobId"],
        "expectedPublicationReceiptSha256": request["expectedPublicationReceiptSha256"],
        "profile": profile,
        "generationStatus": "completed",
        "localChecks": validation["localChecks"],
        "publicationEligibility": validation["publicationEligibility"],
        "validation": validation,
        "artifacts": {
            name: {
                "url": f"/api/creation/jobs/{directory.name}/package-files/{name}",
                "sha256": receipt["files"][name],
                "mediaType": DOWNLOADS[name],
            }
            for name in DOWNLOADS
        },
    }


def resource(jobs: Any, job_id: str, name: str) -> MediaResource:
    if name not in DOWNLOADS:
        raise ValueError("Unknown package file")
    state = jobs.get(job_id)
    if state["kind"] != "package" or state["status"] != "completed":
        raise ValueError("Package unavailable")
    return MediaResource(
        jobs.safe(jobs.directory(job_id) / "result" / name),
        state["package"]["artifacts"][name]["sha256"],
        DOWNLOADS[name],
    )
