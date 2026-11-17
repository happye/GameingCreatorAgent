"""Pure local completion of a selected immutable AI plan."""

from copy import deepcopy
from typing import Any

from gamingcreator.application.creative_planner import (
    MAX_SHOT_SECONDS,
    _event_frames,
    _segment_range,
)
from gamingcreator.application.material_scoring import score_materials
from gamingcreator.application.plan_proposals import PlanSnapshot, _segment
from gamingcreator.application.plan_topics import compiled_topics, topic_advisories


def _anchor(row: dict[str, Any], originals: list[dict[str, Any]]) -> tuple[int, int, int]:
    choices = [
        (
            min(abs(row["startUs"] - s["endUs"]), abs(row["endUs"] - s["startUs"])),
            0 if row["startUs"] >= s["endUs"] else 1,
            i,
        )
        for i, s in enumerate(originals)
        if row["sourceSha256"] == s["sourceSha256"]
    ]
    return min(choices) if choices else (2, 0, len(originals) - 1)


def complete_duration(
    snapshot: PlanSnapshot,
    report: dict[str, Any],
    plan_id: str,
    parent_job_id: str,
    parent_receipt: str,
) -> dict[str, Any]:
    result = deepcopy(report)
    original = next((p for p in result["plans"] if p["id"] == plan_id), None)
    if original is None or not report.get("reasoningProvenance"):
        raise ValueError("仅支持已保存的 AI 方案。")
    originals = original["segments"]
    target = snapshot.brief.target_duration * snapshot.fps
    remaining = target - sum(s["outputFrames"] for s in originals)
    if remaining <= 0:
        raise ValueError("当前方案已达到目标时长。")
    used = list(originals)
    additions: dict[int, list[dict[str, Any]]] = {}
    added = []
    scores = score_materials(snapshot.brief, list(snapshot.clips))
    candidates = list(zip(snapshot.payload["candidates"], snapshot.clips, strict=True))
    candidates.sort(
        key=lambda pair: (
            *_anchor(pair[0], originals)[:2],
            pair[0]["startUs"],
            pair[0]["candidateId"],
        )
    )
    for candidate, clip in candidates:
        frames = min(remaining, _event_frames(clip, snapshot.fps), MAX_SHOT_SECONDS * snapshot.fps)
        if frames <= 0:
            continue
        source = _segment_range(clip, frames, snapshot.fps)
        if any(
            s["sourceSha256"] == clip.asset.sha256
            and source.start_us < s["endUs"]
            and source.end_us > s["startUs"]
            for s in used
        ):
            continue
        row = _segment(
            clip,
            frames,
            snapshot.fps,
            0,
            "本地补充",
            scores[(clip.event.run_id, clip.event.event_id)],
        )
        if "topicMapping" in snapshot.payload:
            row["topicUses"] = []
        additions.setdefault(_anchor(candidate, originals)[2], []).append(row)
        used.append(row)
        added.append(candidate["candidateId"])
        remaining -= frames
    return _finish(
        snapshot,
        result,
        original,
        additions,
        remaining,
        target,
        added,
        parent_job_id,
        parent_receipt,
        plan_id,
    )


def _finish(
    snapshot: PlanSnapshot,
    result: dict[str, Any],
    original: dict[str, Any],
    additions: dict[int, list[dict[str, Any]]],
    remaining: int,
    target: int,
    added: list[str],
    parent_job_id: str,
    parent_receipt: str,
    plan_id: str,
) -> dict[str, Any]:
    segments = []
    for index, row in enumerate(original["segments"]):
        segments.extend([row, *additions.get(index, [])])
    position = 0
    for row in segments:
        row["outputStartFrame"] = position
        position += row["outputFrames"]
    original.update(
        segments=segments,
        actualFrames=position,
        targetFrames=target,
        frameGap=remaining,
        durationStatus="target-met" if not remaining else "insufficient-candidate-pool",
        advisories=topic_advisories(snapshot, segments),
        **compiled_topics(snapshot, segments),
    )
    if remaining:
        original["gaps"] = [*original.get("gaps", []), f"可用且不重叠素材不足，还差 {remaining} 帧"]
    original["ready"] = not original.get("gaps")
    result.update(
        plans=[original],
        planner="AI+本地补时",
        localCompletion={
            "version": "plan-duration-completion-v1",
            "parentJobId": parent_job_id,
            "parentReceiptSha256": parent_receipt,
            "parentPlanId": plan_id,
            "targetFrames": target,
            "addedCandidateIds": added,
        },
    )
    return result
