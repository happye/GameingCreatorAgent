"""Validate source-bound editing decisions before any renderer receives local media."""

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.media import MediaAsset
from gamingcreator.domain.time import SourceRange


@dataclass(frozen=True, slots=True)
class RenderClip:
    asset: MediaAsset
    source_range: SourceRange
    output_frames: int
    speed: Fraction = Fraction(1, 1)

    def __post_init__(self) -> None:
        if type(self.speed) is not Fraction or self.speed not in (
            Fraction(1, 2),
            Fraction(1),
            Fraction(2),
        ):
            raise ValueError("Clip speed must be Fraction 1/2, 1 or 2.")


@dataclass(frozen=True, slots=True)
class RenderPlan:
    clips: tuple[RenderClip, ...]
    fps: int
    transition_frames: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.transition_frames) is not tuple:
            raise ValueError("Transition frames must be an immutable tuple.")
        if self.transition_frames:
            output_start_frames(tuple(c.output_frames for c in self.clips), self.transition_frames)

    @property
    def start_frames(self) -> tuple[int, ...]:
        return output_start_frames(
            tuple(c.output_frames for c in self.clips), self.transition_frames
        )

    @property
    def frames(self) -> int:
        return self.start_frames[-1] + self.clips[-1].output_frames if self.clips else 0


def output_start_frames(
    lengths: tuple[int, ...], transitions: tuple[int, ...] = ()
) -> tuple[int, ...]:
    """One exact output layout shared by revisions, rendering and subtitles."""
    incoming = transitions or (0,) * len(lengths)
    if len(incoming) != len(lengths) or any(type(n) is not int or n <= 0 for n in lengths):
        raise ValueError("Invalid clip lengths or transition count.")
    if any(type(n) is not int or n < 0 for n in incoming) or (incoming and incoming[0] != 0):
        raise ValueError("Transitions need nonnegative integer frames and an initial cut.")
    for index, length in enumerate(lengths):
        outgoing = incoming[index + 1] if index + 1 < len(lengths) else 0
        if incoming[index] + outgoing >= length:
            raise ValueError("Transitions must leave one exclusive frame in each clip.")
    starts: list[int] = []
    offset = 0
    for length, overlap in zip(lengths, incoming, strict=True):
        offset -= overlap
        starts.append(offset)
        offset += length
    return tuple(starts)


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
