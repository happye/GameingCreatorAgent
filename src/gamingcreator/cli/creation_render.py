"""Public receipt-checked local render entry point."""

import hashlib
import json
from pathlib import Path
from typing import Any

from gamingcreator.application.creation_subtitles import build_subtitles
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import validate_render_plan
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.infrastructure.local_paths import is_link, resolve_existing
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def read_creation(directory: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    root = resolve_existing(directory)

    def read(name: str) -> bytes:
        path = directory / name
        if (
            is_link(path)
            or resolve_existing(path).parent != root
            or path.stat().st_size > 32_000_000
        ):
            raise ValueError("Invalid creation file path or size.")
        return path.read_bytes()

    receipt_bytes = read("receipt.json")
    receipt = json.loads(receipt_bytes)
    if receipt.get("schemaVersion") != "creation-receipt-v1" or set(receipt.get("files", {})) != {
        "plans.json",
        "edit-decision.json",
    }:
        raise ValueError("Creation needs a completed receipt with an explicitly selected EDL.")
    documents = {}
    for name in ("plans.json", "edit-decision.json"):
        data = read(name)
        if hashlib.sha256(data).hexdigest() != receipt["files"][name]:
            raise ValueError("Creation receipt hash mismatch.")
        document = json.loads(data)
        if not isinstance(document, dict):
            raise ValueError("Invalid creation document.")
        documents[name] = document
    return (
        documents["edit-decision.json"],
        documents["plans.json"],
        hashlib.sha256(receipt_bytes).hexdigest(),
    )


async def execute_render_creation(
    project: Path,
    creation: Path,
    output: Path,
    renderer: FfmpegCreationRenderer,
    width: int,
    height: int,
    subtitle_mode: str = "none",
) -> dict[str, object]:
    try:
        if subtitle_mode not in ("none", "sidecar", "burn"):
            raise ValueError("Unknown subtitle mode.")
        edl, plans, digest = read_creation(creation)
        rows = edl.get("segments")
        if (
            not isinstance(rows, list)
            or not rows
            or any(
                not isinstance(row, dict) or not isinstance(row.get("runId"), str) for row in rows
            )
        ):
            raise ValueError("Invalid EDL segments.")
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            timelines = tuple(
                [
                    await store.load_completed_timeline(run)
                    for run in dict.fromkeys(row["runId"] for row in rows)
                ]
            )
        finally:
            await store.close()
        plan = validate_render_plan(edl, plans, timelines)
        runs = {timeline.run.run_id: timeline for timeline in timelines}
        cues = (
            ()
            if subtitle_mode == "none"
            else build_subtitles(
                plan, (), per_clip=(runs[row["runId"]].transcripts for row in rows)
            )
        )
        return await renderer.render(
            plan,
            output,
            (project, creation, *(clip.asset.source_path for clip in plan.clips)),
            CancellationContext("creation-render", 3600),
            width,
            height,
            digest,
            cues,
            subtitle_mode,
        )
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        raise AppError("creation.render_invalid", str(error), ExitCode.INPUT) from error
