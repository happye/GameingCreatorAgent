"""Immutable publication versions bound to verified completed render output."""

import asyncio
import json
import unicodedata
from pathlib import Path
from typing import Any

from gamingcreator.application.creation_modes import MODE_LABELS
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
    edl, report, _ = read_creation(jobs.safe(directory / "selection"))
    brief = report["brief"]
    fps = receipt["fpsNumerator"] / receipt["fpsDenominator"]
    copy = draft_copy(brief, edl.get("segments") or [], fps)
    return {
        "publicationJobId": None,
        "publicationReceiptSha256": None,
        "renderJobId": job_id,
        "expectedRenderReceiptSha256": digest,
        "coverFrame": 0,
        **copy,
        **clock(receipt),
        "videoUrl": "/api/creation/jobs/" + job_id + "/video",
        "draftStatus": "editable-template-not-ai",
        "generationMode": "local_template",
        "draft": True,
        "metadataOrigin": "brief_template",
        "qualityStatus": "unreviewed",
    }


HIGHLIGHT_LIMIT = 6


def _clean(value: object, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    return "".join(c for c in text if unicodedata.category(c) != "Cc")[:limit]


NEWCOMER = ("新玩家", "新手", "萌新", "小白")


def _timestamp(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def draft_copy(
    brief: dict[str, Any], segments: list[Any], fps: float | None = None
) -> dict[str, Any]:
    """Editable local template from the structured brief and the rendered shots.

    J1 2026-11-11: the title is no longer the raw brief sentence and the description is an
    intro plus a timestamped chapter list instead of piled-up analysis text. No model writes
    anything here.
    """
    game = _clean(brief["game"], 100).strip()
    label = MODE_LABELS.get(brief["contentType"], brief["contentType"])
    topics = [t for t in (_clean(x, 50).strip() for x in brief.get("mandatoryTopics") or []) if t]
    audience = _clean(brief.get("audience"), 20).strip()
    title = f"{game}｜{label}" + (f"：{'、'.join(topics[:3])}" if topics else "")
    if audience in NEWCOMER:
        title = "【新手向】" + title
    intro = (
        f"这期{('给' + audience) if audience else ''}带来{f'《{game}》的' if game else ''}{label}"
    )
    intro += f"，重点讲{'、'.join(topics)}。" if topics else "。"
    chapters: list[str] = []
    elapsed = 0.0
    for segment in segments:
        row = segment if isinstance(segment, dict) else {}
        role = _clean(row.get("role"), 40).strip()
        fact = _clean(row.get("scriptDraft"), 400).split("；")[0].strip().rstrip("。")[:40]
        name = role if role and role != "镜头" else fact
        stamp = _timestamp(elapsed) + " " if fps else ""
        if name and not any(line.endswith(" " + name) or line == name for line in chapters):
            chapters.append(stamp + name)
        frames = row.get("outputFrames")
        elapsed += frames / fps if fps and isinstance(frames, int) else 0
        if len(chapters) == HIGHLIGHT_LIMIT:
            break
    description = intro + ("\n\n本期内容：\n" + "\n".join(chapters) if chapters else "")
    tags = [game, label, *topics]
    return {
        "title": _clean(title, 80) or "创作视频",
        "description": description[:5000],
        "tags": list(dict.fromkeys(t for t in (_clean(x, 50).strip() for x in tags) if t))[:20],
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
