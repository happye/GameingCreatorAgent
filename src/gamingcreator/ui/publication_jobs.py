"""Immutable publication versions bound to verified completed render output."""

import asyncio
import json
import unicodedata
from pathlib import Path
from typing import Any

from gamingcreator.cli.creation_render import read_creation
from gamingcreator.domain.publication import validate_metadata
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.publication_assets import extract_cover, validate_png
from gamingcreator.ui.media import MediaResource

FILES = {
    "cover.png": "image/png",
    "title.txt": "text/plain; charset=utf-8",
    "description.txt": "text/plain; charset=utf-8",
    "tags.json": "application/json",
    "publication.json": "application/json",
}


def render_parent(jobs: Any, job_id: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    directory = jobs.directory(job_id)
    state = jobs.read(directory / "status.json")
    if state.get("kind") != "render" or state.get("status") != "completed":
        raise ValueError("Publication requires a completed render")
    verified = jobs.verify(directory, state)
    receipt = jobs.read(directory / "result/receipt.json")
    for key in ("frames", "fpsNumerator", "fpsDenominator", "width", "height"):
        if type(receipt.get(key)) is not int or receipt[key] <= 0:
            raise ValueError("Render has no valid output clock")
    return verified, receipt, verified["resultReceiptSha256"]


def prepare(jobs: Any, request: dict[str, Any]) -> tuple[str, str]:
    state, receipt, digest = render_parent(jobs, request["renderJobId"])
    if request["expectedRenderReceiptSha256"] != digest:
        raise ValueError("Render receipt changed")
    validate_metadata(request, receipt["frames"])
    return state["projectId"], digest


def snapshot(jobs: Any, job_id: str) -> dict[str, Any]:
    directory = jobs.directory(job_id)
    state = jobs.read(directory / "status.json")
    if state["kind"] == "publication":
        if state["status"] != "completed":
            raise ValueError("Publication is not complete")
        verified = jobs.verify(directory, state)
        return {
            **verified["publication"],
            "publicationJobId": job_id,
            "publicationReceiptSha256": verified["resultReceiptSha256"],
        }
    _, receipt, digest = render_parent(jobs, job_id)
    _, report, _ = read_creation(jobs.safe(directory / "selection"))
    brief = report["brief"]

    def clean(value: str, limit: int) -> str:
        return "".join(c for c in value if unicodedata.category(c) != "Cc")[:limit]

    return {
        "publicationJobId": None,
        "publicationReceiptSha256": None,
        "renderJobId": job_id,
        "expectedRenderReceiptSha256": digest,
        "coverFrame": 0,
        "title": clean(brief["game"] + " · " + brief["objective"], 200) or "创作视频",
        "description": clean(brief["objective"], 5000),
        "tags": list(
            dict.fromkeys(
                clean(tag, 50)
                for tag in [brief["game"], brief["contentType"]]
                if clean(tag, 50).strip()
            )
        ),
        **clock(receipt),
        "videoUrl": "/api/creation/jobs/" + job_id + "/video",
        "draftStatus": "editable-template-not-ai",
        "generationMode": "local_template",
        "draft": True,
        "metadataOrigin": "brief_template",
        "qualityStatus": "unreviewed",
    }


def clock(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "frames": receipt["frames"],
        "fps": {"numerator": receipt["fpsNumerator"], "denominator": receipt["fpsDenominator"]},
        "width": receipt["width"],
        "height": receipt["height"],
    }


def expected_snapshot(request: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        **{
            key: request[key]
            for key in (
                "renderJobId",
                "expectedRenderReceiptSha256",
                "coverFrame",
                "title",
                "description",
                "tags",
            )
        },
        **clock(receipt),
        "videoUrl": "/api/creation/jobs/" + request["renderJobId"] + "/video",
        "draftStatus": "editable-template-not-ai",
        "generationMode": "local_template",
        "draft": False,
        "metadataOrigin": "user_edited_template",
        "qualityStatus": "unreviewed",
    }


async def save_publication(jobs: Any, directory: Path, request: dict[str, Any]) -> None:
    # Revision verification runs its own source-check loop; keep it off this loop.
    _, parent, digest = await asyncio.to_thread(render_parent, jobs, request["renderJobId"])
    validate_metadata(request, parent["frames"])
    if digest != request["expectedRenderReceiptSha256"]:
        raise ValueError("Render changed")
    target = jobs.safe(directory / "result")
    target.mkdir()
    video = jobs.safe(jobs.directory(request["renderJobId"]) / "result/video.mp4")
    await extract_cover(
        jobs.repository,
        video,
        jobs.safe(target / "cover.png"),
        request["coverFrame"],
        parent["width"],
        parent["height"],
    )
    for name, text in (
        ("title.txt", request["title"]),
        ("description.txt", request["description"]),
        ("tags.json", json.dumps(request["tags"], ensure_ascii=False)),
    ):
        with jobs.safe(target / name).open("x", encoding="utf-8", newline="") as handle:
            handle.write(text)
    jobs.save(target / "publication.json", expected_snapshot(request, parent))
    # Check again after decoding: the parent cannot silently change during extraction.
    _, current, current_digest = await asyncio.to_thread(
        render_parent, jobs, request["renderJobId"]
    )
    if current_digest != digest or current != parent:
        raise ValueError("Render changed during cover extraction")
    result = {
        "schemaVersion": "creation-publication-receipt-v1",
        "status": "completed",
        "parentRenderReceiptSha256": digest,
        "renderVideoSha256": parent["files"]["video.mp4"],
        "coverFrame": request["coverFrame"],
        **clock(parent),
        "files": {name: hash_file(jobs.safe(target / name)) for name in FILES},
    }
    jobs.save(target / "receipt.json", result)


def verify_publication(
    jobs: Any,
    directory: Path,
    state: dict[str, Any],
    stored: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    request = stored["request"]
    parent_state, parent, digest = render_parent(jobs, request["renderJobId"])
    validate_metadata(request, parent["frames"])
    if (
        state["parentJobId"] != request["renderJobId"]
        or state["projectId"] != parent_state["projectId"]
        or stored["parentReceiptSha256"] != digest
        or request["expectedRenderReceiptSha256"] != digest
        or receipt.get("schemaVersion") != "creation-publication-receipt-v1"
        or receipt.get("status") != "completed"
        or receipt.get("parentRenderReceiptSha256") != digest
        or receipt.get("renderVideoSha256") != parent["files"]["video.mp4"]
        or receipt.get("coverFrame") != request["coverFrame"]
        or any(receipt.get(key) != value for key, value in clock(parent).items())
        or set(receipt.get("files", {})) != set(FILES)
    ):
        raise ValueError("Publication identity changed")
    target = directory / "result"
    for name in FILES:
        if hash_file(jobs.safe(target / name)) != receipt["files"][name]:
            raise ValueError("Publication artifact changed")
    expected = expected_snapshot(request, parent)
    if jobs.read(target / "publication.json") != expected:
        raise ValueError("Publication metadata changed")
    for name, value in (
        ("title.txt", request["title"]),
        ("description.txt", request["description"]),
        ("tags.json", json.dumps(request["tags"], ensure_ascii=False)),
    ):
        if jobs.safe(target / name).read_bytes().decode("utf-8") != value:
            raise ValueError("Publication text changed")
    validate_png(jobs.safe(target / "cover.png"), parent["width"], parent["height"])
    state["publication"] = expected
    state["publicationArtifacts"] = {
        name: {
            "url": f"/api/creation/jobs/{directory.name}/publication-files/{name}",
            "sha256": receipt["files"][name],
            "mediaType": FILES[name],
        }
        for name in FILES
    }


def resource(jobs: Any, job_id: str, name: str) -> MediaResource:
    if name not in FILES:
        raise ValueError("Unknown publication file")
    state = jobs.get(job_id)
    if state["kind"] != "publication" or state["status"] != "completed":
        raise ValueError("Publication has no valid artifacts")
    return MediaResource(
        jobs.safe(jobs.directory(job_id) / "result" / name),
        state["publicationArtifacts"][name]["sha256"],
        FILES[name],
    )
