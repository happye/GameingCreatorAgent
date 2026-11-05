"""Frozen text-only planning proposals compiled against trusted local candidates."""

import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
from typing import Any

from gamingcreator.application.creation_proposals import canonical
from gamingcreator.application.creative_planner import (
    MAX_SHOT_SECONDS,
    CreationClip,
    _budgets,
    _event_frames,
    _segment_range,
    candidates,
    eligible_clips,
)
from gamingcreator.application.material_scoring import score_materials
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.creation import CreativeBrief

SCHEMA_VERSION = "plan-proposal-v1"
SNAPSHOT_VERSION = "plan-snapshot-v1"


@dataclass(frozen=True)
class PlanSnapshot:
    """Backend-only frozen binding; payload copies cannot mutate its identity."""

    payload_json: str
    clips: tuple[CreationClip, ...]
    brief: CreativeBrief
    fps: int

    @property
    def fingerprint(self) -> str:
        return sha256(self.payload_json.encode()).hexdigest()

    @property
    def payload(self) -> dict[str, Any]:
        return dict(json.loads(self.payload_json))


def create_plan_snapshot(
    brief: CreativeBrief,
    timelines: tuple[StoredTimeline, ...],
    fps: int,
    event_ids: tuple[str, ...] = (),
    clip_ranges: object = None,
) -> PlanSnapshot:
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError("Invalid output fps.")
    clips = tuple(eligible_clips(brief, candidates(timelines, event_ids, clip_ranges), fps))
    rows = []
    for index, clip in enumerate(clips):
        event = clip.event
        rows.append(
            {
                "candidateId": f"candidate-{index + 1}",
                "runId": event.run_id,
                "eventId": event.event_id,
                "sourceSha256": clip.asset.sha256,
                "sourceDurationUs": clip.asset.duration_us,
                "mediaId": clip.asset.media_id,
                "evidenceIds": list(event.evidence_ids),
                "facts": list(event.observable_facts),
                "tags": list(event.mechanic_tags),
                "uncertainty": event.uncertainty,
                "analysisStartUs": event.source_range.start_us,
                "analysisEndUs": event.source_range.end_us,
                "startUs": clip.framing.start_us,
                "endUs": clip.framing.end_us,
            }
        )
    payload = {
        "schemaVersion": SNAPSHOT_VERSION,
        "brief": asdict(brief),
        "fps": fps,
        "runIds": [t.run.run_id for t in timelines],
        "eventIds": list(event_ids),
        "clipRanges": clip_ranges,
        "candidates": rows,
    }
    return PlanSnapshot(canonical(payload), clips, brief, fps)


@dataclass(frozen=True)
class PlanProposal:
    snapshot_fingerprint: str
    response_json: str

    @property
    def response(self) -> dict[str, Any]:
        return dict(json.loads(self.response_json))


def _text(value: Any, limit: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Invalid bounded text.")


def validate_plan_proposal(snapshot: PlanSnapshot, value: dict[str, Any]) -> PlanProposal:
    if not isinstance(value, dict) or len(canonical(value)) > 200_000:
        raise ValueError("Invalid or oversized proposal.")
    if set(value) != {"schemaVersion", "snapshotFingerprint", "kind", "questions", "plans"}:
        raise ValueError("Unexpected proposal fields.")
    if value["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("Unsupported proposal schema.")
    if value["snapshotFingerprint"] != snapshot.fingerprint:
        raise ValueError("Snapshot fingerprint changed.")
    questions, plans = value["questions"], value["plans"]
    if not isinstance(questions, list) or len(questions) > 8:
        raise ValueError("Invalid questions.")
    for question in questions:
        _text(question, 500)
    if value["kind"] == "clarification":
        if not questions or plans != []:
            raise ValueError("Clarification requires questions and no plans.")
    elif value["kind"] == "plan_proposal":
        if questions or not isinstance(plans, list) or not 1 <= len(plans) <= 3:
            raise ValueError("Expected one to three plans without questions.")
        _validate_plans(snapshot, plans)
    else:
        raise ValueError("Unknown proposal kind.")
    return PlanProposal(snapshot.fingerprint, canonical(value))


def _validate_plans(snapshot: PlanSnapshot, plans: list[Any]) -> None:
    allowed = {r["candidateId"] for r in snapshot.payload["candidates"]}
    selections = set()
    for plan in plans:
        if not isinstance(plan, dict) or set(plan) != {"title", "structure", "shots"}:
            raise ValueError("Unexpected plan fields.")
        _text(plan["title"], 200)
        _text(plan["structure"], 2000)
        shots = plan["shots"]
        if not isinstance(shots, list) or not 1 <= len(shots) <= min(200, len(allowed)):
            raise ValueError("Invalid shots.")
        ids = []
        for shot in shots:
            if not isinstance(shot, dict) or set(shot) != {"candidateId", "role"}:
                raise ValueError("Unexpected shot fields; source ranges belong to backend.")
            if not isinstance(shot["candidateId"], str) or shot["candidateId"] not in allowed:
                raise ValueError("Unknown candidate.")
            _text(shot["role"], 200)
            ids.append(shot["candidateId"])
        if len(set(ids)) != len(ids) or tuple(ids) in selections:
            raise ValueError("Repeated candidate or duplicate plan selection.")
        selections.add(tuple(ids))


def _segment(
    clip: CreationClip, frames: int, fps: int, position: int, role: str, score: Any
) -> dict[str, Any]:
    event, source = clip.event, _segment_range(clip, frames, fps)
    row = {
        "runId": event.run_id,
        "eventId": event.event_id,
        "mediaId": clip.asset.media_id,
        "sourceSha256": clip.asset.sha256,
        "sourcePath": str(clip.asset.source_path),
        "startUs": source.start_us,
        "endUs": source.end_us,
        "sourceDurationUs": clip.asset.duration_us,
        "outputStartFrame": position,
        "outputFrames": frames,
        "evidenceIds": list(event.evidence_ids),
        "scriptDraft": "；".join(event.observable_facts),
        "uncertainty": event.uncertainty,
        "role": role,
        "score": score,
    }
    if clip.source_range is not None:
        row["rangeProvenance"] = {
            "schemaVersion": "user-framing-v1",
            "analysisStartUs": event.source_range.start_us,
            "analysisEndUs": event.source_range.end_us,
            "startUs": clip.framing.start_us,
            "endUs": clip.framing.end_us,
        }
    return row


def compile_plan_proposal(snapshot: PlanSnapshot, proposal: PlanProposal) -> dict[str, Any]:
    if proposal.snapshot_fingerprint != snapshot.fingerprint:
        raise ValueError("Snapshot fingerprint changed.")
    response = validate_plan_proposal(snapshot, proposal.response).response
    if response["kind"] != "plan_proposal":
        raise ValueError("Clarification cannot be compiled.")
    lookup = dict(
        zip((r["candidateId"] for r in snapshot.payload["candidates"]), snapshot.clips, strict=True)
    )
    scores = score_materials(snapshot.brief, list(snapshot.clips))
    plans = [
        _compile_one(snapshot, row, lookup, scores, index)
        for index, row in enumerate(response["plans"], 1)
    ]
    return {
        "schemaVersion": "creation-plan-v1",
        "planner": SCHEMA_VERSION,
        "understandingVerified": False,
        "snapshotFingerprint": snapshot.fingerprint,
        "fps": snapshot.fps,
        "brief": {
            "game": snapshot.brief.game,
            "contentType": snapshot.brief.content_type,
            "platforms": list(snapshot.brief.platforms),
            "targetDuration": snapshot.brief.target_duration,
            "objective": snapshot.brief.objective,
            "audience": snapshot.brief.audience,
            "tone": snapshot.brief.tone,
            "mandatoryTopics": list(snapshot.brief.mandatory_topics),
            "exclude": list(snapshot.brief.exclude),
        },
        "plans": plans,
    }


def _compile_one(
    snapshot: PlanSnapshot,
    row: dict[str, Any],
    lookup: dict[str, CreationClip],
    scores: Any,
    index: int,
) -> dict[str, Any]:
    fps, target = snapshot.fps, snapshot.brief.target_duration * snapshot.fps
    picked = [lookup[s["candidateId"]] for s in row["shots"]]
    capacities = [min(_event_frames(c, fps), MAX_SHOT_SECONDS * fps) for c in picked]
    budgets = _budgets(capacities, [Fraction(1)] * len(picked), target)
    segments, position = [], 0
    used: set[tuple[str, int, int]] = set()
    for clip, shot, frames in zip(picked, row["shots"], budgets, strict=True):
        if frames and _claim_interval(clip, frames, fps, used):
            segments.append(
                _segment(
                    clip,
                    frames,
                    fps,
                    position,
                    shot["role"],
                    scores[(clip.event.run_id, clip.event.event_id)],
                )
            )
            position += frames
    text = " ".join(s["scriptDraft"] for s in segments).casefold()
    gaps = [
        f"主题缺少已保存文字证据：{topic}"
        for topic in snapshot.brief.mandatory_topics
        if topic.casefold() not in text
    ]
    if not segments:
        gaps.append("没有可渲染素材")
    pool_intervals: set[tuple[str, int, int]] = set()
    pool = 0
    for clip in snapshot.clips:
        frames = min(_event_frames(clip, fps), MAX_SHOT_SECONDS * fps)
        if _claim_interval(clip, frames, fps, pool_intervals):
            pool += frames
    return {
        "id": f"dynamic-{index}",
        "title": row["title"],
        "structure": row["structure"],
        "segments": segments,
        "gaps": gaps,
        "ready": not gaps,
        "targetFrames": target,
        "actualFrames": position,
        "frameGap": target - position,
        "durationStatus": "target-met"
        if position == target
        else ("insufficient-candidate-pool" if pool < target else "insufficient-selection"),
        "advisories": [],
        "scriptStatus": "saved-descriptions-draft-human-review-required",
    }


def _claim_interval(
    clip: CreationClip, frames: int, fps: int, used: set[tuple[str, int, int]]
) -> bool:
    """Deduplicate final framing, since distinct observations can compile identically."""
    source = _segment_range(clip, frames, fps)
    key = (clip.asset.sha256, source.start_us, source.end_us)
    if key in used:
        return False
    used.add(key)
    return True
