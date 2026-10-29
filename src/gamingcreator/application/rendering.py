"""Validate source-bound editing decisions before any renderer receives local media."""

from dataclasses import dataclass
from typing import Any

from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.media import MediaAsset
from gamingcreator.domain.time import SourceRange


@dataclass(frozen=True, slots=True)
class RenderClip:
    asset: MediaAsset
    source_range: SourceRange
    output_frames: int


@dataclass(frozen=True, slots=True)
class RenderPlan:
    clips: tuple[RenderClip, ...]
    fps: int

    @property
    def frames(self) -> int:
        return sum(clip.output_frames for clip in self.clips)


def validate_render_plan(
    edl: dict[str, Any], plans: dict[str, Any], timelines: tuple[StoredTimeline, ...]
) -> RenderPlan:
    if (
        edl.get("schemaVersion") != "edit-decision-v1"
        or plans.get("schemaVersion") != "creation-plan-v1"
    ):
        raise ValueError("Unsupported creation schema.")
    fps = edl.get("fpsNumerator")
    if (
        type(fps) is not int
        or not 1 <= fps <= 120
        or edl.get("fpsDenominator") != 1
        or plans.get("fps") != fps
    ):
        raise ValueError("Invalid output clock.")
    selected = [
        plan for plan in plans.get("plans", []) if plan.get("id") == edl.get("selectedPlan")
    ]
    rows = edl.get("segments")
    if (
        len(selected) != 1
        or selected[0].get("ready") is not True
        or selected[0].get("gaps")
        or not isinstance(rows, list)
        or not rows
        or rows != selected[0].get("segments")
    ):
        raise ValueError("EDL must match exactly one ready saved plan.")
    runs = {timeline.run.run_id: timeline for timeline in timelines}
    clips: list[RenderClip] = []
    seen: set[tuple[str, int, int]] = set()
    frames = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("runId") not in runs:
            raise ValueError("Unknown source run.")
        timeline = runs[row["runId"]]
        asset = timeline.run.asset
        event = next(
            (event for event in timeline.events if event.event_id == row.get("eventId")), None
        )
        if event is None or event.media_id != asset.media_id or event.run_id != timeline.run.run_id:
            raise ValueError("Unknown or cross-source event.")
        for key in ("startUs", "endUs", "sourceDurationUs", "outputStartFrame", "outputFrames"):
            if type(row.get(key)) is not int:
                raise ValueError("Source and output times must be integers.")
        if (
            row.get("mediaId") != asset.media_id
            or row.get("sourceSha256") != asset.sha256
            or row.get("sourcePath") != str(asset.source_path)
            or row["sourceDurationUs"] != asset.duration_us
            or not event.source_range.start_us
            <= row["startUs"]
            < row["endUs"]
            <= event.source_range.end_us
            or row["outputFrames"] <= 0
            or row["outputStartFrame"] != frames
            or row["endUs"] - row["startUs"] != (row["outputFrames"] * 1_000_000 + fps - 1) // fps
            or row.get("evidenceIds") != list(event.evidence_ids)
        ):
            raise ValueError("EDL source binding, range or frame mapping is invalid.")
        interval_key = (asset.sha256, row["startUs"], row["endUs"])
        if interval_key in seen:
            raise ValueError("Duplicate source interval.")
        seen.add(interval_key)
        clips.append(
            RenderClip(
                asset,
                SourceRange(row["startUs"], row["endUs"], asset.duration_us),
                row["outputFrames"],
            )
        )
        frames += row["outputFrames"]
    brief = plans.get("brief", {})
    duration = brief.get("targetDuration")
    if type(duration) is not int or duration <= 0 or frames > duration * fps:
        raise ValueError("EDL exceeds Brief duration.")
    return RenderPlan(tuple(clips), fps)
