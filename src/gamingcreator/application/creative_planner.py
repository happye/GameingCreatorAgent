"""Pure template planner over explicitly loaded, verified saved timelines."""

from dataclasses import dataclass

from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.media import MediaAsset
from gamingcreator.domain.models import SemanticEvent


@dataclass(frozen=True, slots=True)
class CreationClip:
    asset: MediaAsset
    event: SemanticEvent


def candidates(
    timelines: tuple[StoredTimeline, ...], event_ids: tuple[str, ...]
) -> tuple[CreationClip, ...]:
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("Duplicate selected events.")
    found: dict[str, CreationClip] = {}
    for timeline in timelines:
        asset = timeline.run.asset
        evidence = {item.evidence_id for item in timeline.evidence}
        for event in timeline.events:
            if (
                event.run_id != timeline.run.run_id
                or event.media_id != asset.media_id
                or event.source_range.duration_us != asset.duration_us
                or event.source_range.end_us > asset.duration_us
                or event.event_id in found
                or not event.evidence_ids
                or not set(event.evidence_ids) <= evidence
            ):
                raise ValueError("Invalid event source or evidence identity.")
            found[event.event_id] = CreationClip(asset, event)
    if set(event_ids) - found.keys():
        raise ValueError("Unknown selected event.")
    return tuple(clip for key, clip in found.items() if not event_ids or key in event_ids)


def plan_creation(
    brief: CreativeBrief, clips: tuple[CreationClip, ...], fps: int
) -> dict[str, object]:
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError("Output fps must be an integer in 1..120.")
    eligible = [
        clip
        for clip in clips
        if not any(
            word.casefold()
            in " ".join(clip.event.observable_facts + clip.event.mechanic_tags).casefold()
            for word in brief.exclude
        )
        and clip.event.observable_facts
        and (clip.event.source_range.end_us - clip.event.source_range.start_us) * fps >= 1_000_000
    ]
    # A different analysis version is not another shot of the same source interval.
    unique: dict[tuple[str, int, int], CreationClip] = {}
    source_order = {
        sha: index for index, sha in enumerate(dict.fromkeys(clip.asset.sha256 for clip in clips))
    }
    for clip in eligible:
        key = (clip.asset.sha256, clip.event.source_range.start_us, clip.event.source_range.end_us)
        unique.setdefault(key, clip)
    eligible = sorted(
        unique.values(),
        key=lambda clip: (
            source_order[clip.asset.sha256],
            clip.event.source_range.start_us,
            clip.event.source_range.end_us,
        ),
    )
    # Across sources retain the explicit input run order; within each source use source time.
    structures = (
        ("chronological", "按来源顺序展开", eligible),
        ("hook-first", "最后一条先作开场，再回溯", eligible[-1:] + eligible[:-1]),
        ("reverse", "倒序逐条回顾", list(reversed(eligible))),
    )
    plans: list[dict[str, object]] = []
    for identity, description, ordered in structures:
        remaining = brief.target_duration * fps
        segments: list[dict[str, object]] = []
        for index, clip in enumerate(ordered):
            event = clip.event
            frames = min(
                remaining // (len(ordered) - index),
                (event.source_range.end_us - event.source_range.start_us) * fps // 1_000_000,
            )
            if frames <= 0:
                continue
            segments.append(
                {
                    "runId": event.run_id,
                    "eventId": event.event_id,
                    "mediaId": clip.asset.media_id,
                    "sourceSha256": clip.asset.sha256,
                    "sourcePath": str(clip.asset.source_path),
                    "startUs": event.source_range.start_us,
                    "endUs": event.source_range.start_us + (frames * 1_000_000 + fps - 1) // fps,
                    "sourceDurationUs": clip.asset.duration_us,
                    "outputStartFrame": brief.target_duration * fps - remaining,
                    "outputFrames": frames,
                    "evidenceIds": list(event.evidence_ids),
                    "scriptDraft": "；".join(event.observable_facts),
                    "uncertainty": event.uncertainty,
                }
            )
            remaining -= frames
        text = " ".join(str(segment["scriptDraft"]) for segment in segments).casefold()
        gaps = [
            f"主题缺少已保存文字证据：{topic}"
            for topic in brief.mandatory_topics
            if topic.casefold() not in text
        ]
        if len(segments) < 3:
            gaps.append("不足三个不同源区间，不能形成完整的三段结构")
        plans.append(
            {
                "id": identity,
                "structure": description,
                "segments": segments,
                "gaps": gaps,
                "ready": not gaps,
                "scriptStatus": "saved-descriptions-draft-human-review-required",
            }
        )
    return {
        "schemaVersion": "creation-plan-v1",
        "planner": "offline-template-v1",
        "understandingVerified": False,
        "fps": fps,
        "plans": plans,
    }
