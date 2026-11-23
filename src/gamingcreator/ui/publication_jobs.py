"""Immutable publication versions bound to verified completed render output."""

import asyncio
import json
import unicodedata
from pathlib import Path
from typing import Any

from gamingcreator.application.ad_cut import AD_ACTIONS
from gamingcreator.application.creation_modes import MODE_LABELS
from gamingcreator.application.showcase_topics import retained_source_topics
from gamingcreator.cli.creation_render import read_creation
from gamingcreator.domain.publication import user_input_message as user_input_message  # noqa: F401
from gamingcreator.domain.publication import validate_metadata
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.publication_assets import extract_cover, validate_png
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
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


def copy_inputs(jobs: Any, job_id: str) -> tuple[str, dict[str, Any], list[Any], float]:
    """Project, brief, rendered segments and output fps of a completed render (AI copy)."""
    state, receipt, _ = render_parent(jobs, job_id)
    edl, report, _ = read_creation(jobs.safe(jobs.directory(job_id) / "selection"))
    fps = receipt["fpsNumerator"] / receipt["fpsDenominator"]
    return state["projectId"], report["brief"], list(edl.get("segments") or []), fps


def snapshot(jobs: Any, job_id: str) -> dict[str, Any]:
    directory = jobs.directory(job_id)
    state = jobs.read(directory / "status.json")
    if state["kind"] == "publication":
        if state["status"] != "completed":
            raise ValueError("Publication is not complete")
        verified = jobs.verify(directory, state)
        publication = verified["publication"]
        render_dir = jobs.directory(publication["renderJobId"])
        receipt = jobs.read(render_dir / "result/receipt.json")
        edl, report, digest = read_creation(jobs.safe(render_dir / "selection"))
        if digest != receipt["creationReceiptSha256"]:
            raise ValueError("Render selection changed")
        return {
            **publication,
            "publicationJobId": job_id,
            "publicationReceiptSha256": verified["resultReceiptSha256"],
            "contentShots": asyncio.run(content_shots(jobs.project(state["projectId"]), edl)),
            "targetPlatforms": report["brief"].get("platforms", []),
            **_campaign_context(report),
        }
    _, receipt, digest = render_parent(jobs, job_id)
    edl, report, selection_digest = read_creation(jobs.safe(directory / "selection"))
    if selection_digest != receipt["creationReceiptSha256"]:
        raise ValueError("Render selection changed")
    brief = report["brief"]
    fps = receipt["fpsNumerator"] / receipt["fpsDenominator"]
    copy = draft_copy(
        brief,
        edl.get("segments") or [],
        fps,
        evidenced_guide=edl.get("selectedPlan") == "guide-evidence",
        evidenced_commentary=edl.get("selectedPlan") == "commentary-evidence",
        evidenced_highlight=brief.get("contentType") == "highlight",
        ad_plan=edl.get("selectedPlan", ""),
    )
    campaign = _campaign_context(report)
    if campaign:
        tags = campaign["campaignRules"]["fields"].get("requiredTopics", [])
        copy["tags"] = list(dict.fromkeys([*(row["value"] for row in tags), *copy["tags"]]))[:20]
    return {
        "publicationJobId": None,
        "publicationReceiptSha256": None,
        "renderJobId": job_id,
        "expectedRenderReceiptSha256": digest,
        "coverFrame": 0,
        "targetPlatforms": brief.get("platforms", []),
        **copy,
        **campaign,
        **clock(receipt),
        "videoUrl": "/api/creation/jobs/" + job_id + "/video",
        "draftStatus": "editable-template-not-ai",
        "generationMode": "local_template",
        "draft": True,
        "metadataOrigin": "brief_template",
        "qualityStatus": "unreviewed",
    }


def _campaign_context(report: dict[str, Any]) -> dict[str, Any]:
    if "campaignRules" not in report:
        return {}
    return {
        "campaignRules": report["campaignRules"],
        "campaignPlatform": report["brief"]["platforms"][0],
    }


def _within(source: SourceInstant | SourceRange, start: int, end: int) -> bool:
    if isinstance(source, SourceInstant):
        return start <= source.time_us < end
    return start <= source.start_us and source.end_us <= end


def recommend_shots(jobs: Any, request: Any) -> dict[str, Any]:
    from gamingcreator.application.publication_shot_ranking import rank_shots
    from gamingcreator.infrastructure.local_embeddings import LocalEmbeddingProvider

    if (
        not isinstance(request, dict)
        or set(request) != {"publicationJobId", "expectedPublicationReceiptSha256", "theme"}
        or not all(isinstance(value, str) for value in request.values())
        or not 0 < len(request["theme"].strip()) <= 160
    ):
        raise ValueError("请输入 1–160 字主题，并选择已保存的发布版本。")
    job_id = request["publicationJobId"]
    saved = snapshot(jobs, job_id)
    if (
        saved["publicationJobId"] != job_id
        or saved["publicationReceiptSha256"] != request["expectedPublicationReceiptSha256"]
    ):
        raise ValueError("发布版本已更改，请重新打开。")
    shots = [row for row in saved["contentShots"] if row["description"]]
    ranked = (
        asyncio.run(
            rank_shots(
                LocalEmbeddingProvider.from_manifest(jobs.repository),
                job_id,
                request["theme"].strip(),
                shots,
            )
        )
        if shots
        else []
    )
    return {
        "publicationJobId": job_id,
        "publicationReceiptSha256": saved["publicationReceiptSha256"],
        "shots": ranked,
    }


async def content_shots(project: Path, edl: dict[str, Any]) -> list[dict[str, Any]]:
    """Project only descriptions whose evidence still lies inside the rendered shot."""
    rows = edl["segments"]
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timelines = [
            await store.load_completed_timeline(run)
            for run in dict.fromkeys(row["runId"] for row in rows)
        ]
    finally:
        await store.close()
    evidence = {item.evidence_id: item.source_time for t in timelines for item in t.evidence}
    events = {event.event_id: event for t in timelines for event in t.events}
    shots = []
    for row in rows:
        event = events.get(row["eventId"])
        if (
            event is None
            or not event.evidence_ids
            or not all(
                key in evidence and _within(evidence[key], row["startUs"], row["endUs"])
                for key in event.evidence_ids
            )
        ):
            continue
        start = row["outputStartFrame"]
        shots.append(
            {
                "startFrame": start,
                "endFrame": start + row["outputFrames"],
                "description": _clean("；".join(event.observable_facts), 300),
            }
        )
    return shots


HIGHLIGHT_LIMIT = 6


def _clean(value: object, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    return "".join(c for c in text if unicodedata.category(c) != "Cc")[:limit]


NEWCOMER = ("新玩家", "新手", "萌新", "小白")


def _timestamp(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def _commentary_topics(row: dict[str, Any]) -> list[str]:
    return [use["topic"] for use in row.get("topicUses", []) if use.get("evidenceKind") == "fact"]


def draft_copy(
    brief: dict[str, Any],
    segments: list[Any],
    fps: float | None = None,
    *,
    evidenced_guide: bool = False,
    evidenced_commentary: bool = False,
    evidenced_highlight: bool = False,
    ad_plan: str = "",
) -> dict[str, Any]:
    """Editable local template from the structured brief and the rendered shots.

    J1 2026-11-11: the title is no longer the raw brief sentence and the description is an
    intro plus a timestamped chapter list instead of piled-up analysis text. No model writes
    anything here.
    """
    game = _clean(brief["game"], 100).strip()
    label = MODE_LABELS.get(brief["contentType"], brief["contentType"])
    topics = [t for t in (_clean(x, 50).strip() for x in brief.get("mandatoryTopics") or []) if t]
    if evidenced_guide:
        topics = list(
            dict.fromkeys(
                _clean(row["guideStep"], 50).strip()
                for row in segments
                if isinstance(row, dict) and row.get("guideStep")
            )
        )
    is_ad = brief.get("contentType") == "ad"
    source_bound = evidenced_highlight or is_ad
    evidenced_scenes = evidenced_commentary or source_bound
    scene_topics = retained_source_topics if source_bound else _commentary_topics
    if evidenced_scenes:
        topics = list(
            dict.fromkeys(
                _clean(topic, 50).strip()
                for row in segments
                if isinstance(row, dict)
                for topic in scene_topics(row)
            )
        )
    audience = _clean(brief.get("audience"), 20).strip()
    title = f"{game}｜{label}" + (f"：{'、'.join(topics[:3])}" if topics else "")
    if audience in NEWCOMER:
        title = "【新手向】" + title
    intro = (
        f"这期{('给' + audience) if audience else ''}带来{f'《{game}》的' if game else ''}{label}"
    )
    intro += f"，重点讲{'、'.join(topics)}。" if topics else "。"
    if is_ad:
        intro += f"\n{AD_ACTIONS.get(ad_plan, '现在就来体验')}。"
    chapters: list[str] = []
    elapsed = 0.0
    for segment in segments:
        row = segment if isinstance(segment, dict) else {}
        role = _clean(row.get("role"), 40).strip()
        fact = _clean(row.get("scriptDraft"), 400).split("；")[0].strip().rstrip("。")[:40]
        name = role if role and role != "镜头" else fact
        stamp = _timestamp(elapsed) + " " if fps else ""
        if evidenced_guide:
            topic = _clean(row.get("guideStep"), 100).strip()
            name = f"第{len(chapters) + 1}步 {topic}" if topic else ""
        if evidenced_scenes:
            name = _clean("、".join(scene_topics(row)), 60).strip()
        if evidenced_guide or evidenced_scenes:
            if fps and type(row.get("outputStartFrame")) is int:
                stamp = _timestamp(row["outputStartFrame"] / fps) + " "
        chapter = stamp + name
        duplicate = (
            chapter in chapters
            if evidenced_highlight
            else any(line.endswith(" " + name) or line == name for line in chapters)
        )
        if name and not duplicate:
            chapters.append(chapter)
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
        **({"coverTitle": request["coverTitle"]} if "coverTitle" in request else {}),
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
    title = request.get("coverTitle", "").strip()
    cover_options = {"title": title} if title else {}
    await extract_cover(
        jobs.repository,
        video,
        jobs.safe(target / "cover.png"),
        request["coverFrame"],
        parent["width"],
        parent["height"],
        **cover_options,
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
        **({"coverTitle": request["coverTitle"]} if "coverTitle" in request else {}),
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
        or ("coverTitle" in receipt) != ("coverTitle" in request)
        or receipt.get("coverTitle") != request.get("coverTitle")
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
