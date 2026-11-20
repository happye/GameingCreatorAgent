"""Offline ad trials with source-bound selling points and editable calls to action."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from gamingcreator.application.creation_modes import StructureAllocation
from gamingcreator.application.showcase_topics import (
    gameplay_opening,
    retained_source_topics,
    topic_matches,
)
from gamingcreator.domain.creation import CreativeBrief

if TYPE_CHECKING:
    from gamingcreator.application.creation_modes import Score
    from gamingcreator.application.creative_planner import CreationClip

AD_ACTIONS = {
    "ad-evidence-hook": "现在就来体验",
    "ad-evidence-demo": "打开游戏，试试这些玩法",
}
_UNCERTAIN = re.compile(r"未|无法|不确定|可能|疑似|没有|并非|不是|或")


@dataclass(slots=True)
class AdTrial:
    layout: StructureAllocation
    proof: dict[tuple[str, str], list[tuple[str, str]]]
    available: set[str]


def _key(clip: "CreationClip") -> tuple[str, str]:
    return clip.event.run_id, clip.event.event_id


def _frames(clip: "CreationClip", fps: int) -> int:
    return (clip.framing.end_us - clip.framing.start_us) * fps // 1_000_000


def _quote(clip: "CreationClip", topic: str, fps: int) -> str:
    event = clip.event
    source, observed = clip.framing, event.source_range
    span_us = observed.end_us - observed.start_us
    frames = span_us * fps // 1_000_000
    if (
        event.modality == "audio"
        or event.uncertainty
        or source.start_us > observed.start_us
        or source.end_us < observed.end_us
        or frames <= 0
        or (frames * 1_000_000 + fps - 1) // fps != span_us
    ):
        return ""
    return next(
        (
            fact
            for fact in event.observable_facts
            if not _UNCERTAIN.search(fact) and topic_matches(fact, topic)
        ),
        "",
    )


def _selling_points(
    brief: CreativeBrief, clips: Sequence["CreationClip"], fps: int, score: "Score"
) -> tuple[list["CreationClip"], dict[tuple[str, str], list[tuple[str, str]]], set[str]]:
    matches = {
        topic: [(clip, quote) for clip in clips if (quote := _quote(clip, topic, fps))]
        for topic in dict.fromkeys(brief.mandatory_topics)
    }
    selected: list[CreationClip] = []
    proof: dict[tuple[str, str], list[tuple[str, str]]] = {}
    frames_left = brief.target_duration * fps
    for topic, options in matches.items():
        fitted = [
            (replace(clip, source_range=None), quote)
            for clip, quote in options
            if _key(clip) in proof
            or (clip.event.source_range.end_us - clip.event.source_range.start_us)
            * fps
            // 1_000_000
            <= frames_left
        ]
        if not fitted:
            continue
        clip, quote = max(fitted, key=lambda item: (_key(item[0]) in proof, score(item[0])))
        key = _key(clip)
        if key not in proof:
            selected.append(clip)
            proof[key] = []
            frames_left -= _frames(clip, fps)
        proof[key].append((topic, quote))
        if sum(map(len, proof.values())) == 3:
            break
    return selected, proof, {topic for topic, options in matches.items() if options}


def _context_order(clip: "CreationClip", anchors: Sequence["CreationClip"]) -> tuple[int, int]:
    return min(
        (
            int(clip.event.run_id != point.event.run_id),
            abs(clip.framing.start_us - point.framing.start_us),
        )
        for point in anchors
    )


def _layout(
    anchors: list["CreationClip"],
    candidates: list["CreationClip"],
    brief: CreativeBrief,
    fps: int,
    *,
    different_opening: bool,
) -> StructureAllocation:
    target = brief.target_duration * fps
    available = target - sum(_frames(clip, fps) for clip in anchors)
    end = candidates[-1] if candidates and available else None
    end_frames = min(_frames(end, fps), 2 * fps, available) if end is not None else 0
    available -= end_frames
    extras: list[tuple[CreationClip, int, str]] = []
    limit = (2 if different_opening else 3) * fps
    for clip in candidates[: -1 if end is not None else None]:
        frames = min(_frames(clip, fps), limit, available)
        if frames <= 0:
            break
        extras.append((clip, frames, "展示画面"))
        available -= frames
    points = [(clip, _frames(clip, fps), "卖点") for clip in anchors]
    if different_opening and len(points) > 1:
        points = [*points[1:], points[0]]
    if different_opening and extras:
        first, *rest = points
        staged = [first, extras[0], *rest, *extras[1:]] if rest else [extras[0], first, *extras[1:]]
    else:
        staged = [*points, *extras]
    hook, frames, _ = staged[0]
    staged[0] = (hook, frames, "开场钩子")
    if end is not None:
        staged.append((end, end_frames, "号召背景"))
    identity = "ad-evidence-demo" if different_opening else "ad-evidence-hook"
    description = (
        "广告演示版：更换开场，穿插演示画面"
        if different_opening
        else "广告卖点版：集中展示有原片依据的卖点"
    )
    notes = [f"建议行动号召「{AD_ACTIONS[identity]}」，可在声音页起草并合成。"]
    if available:
        notes.append("可用画面短于目标时长。")
    return StructureAllocation(
        identity,
        description,
        [[clip] for clip, _, _ in staged],
        [frames for _, frames, _ in staged],
        tuple(role for _, _, role in staged),
        notes,
    )


def ad_trials(
    brief: CreativeBrief, clips: Sequence["CreationClip"], fps: int, score: "Score"
) -> list[AdTrial]:
    anchors, proof, available = _selling_points(brief, clips, fps, score)
    if not anchors:
        return []
    candidates = [clip for clip in clips if _key(clip) not in proof]
    candidates.sort(key=lambda clip: (_context_order(clip, anchors), not gameplay_opening(clip)))
    if candidates:
        # Reserve a visibly active backdrop when there is spare time for an end card.
        closing = next(
            (clip for clip in reversed(candidates) if gameplay_opening(clip)), candidates[-1]
        )
        candidates = [clip for clip in candidates if clip is not closing] + [closing]
    return [
        AdTrial(
            _layout(anchors, candidates, brief, fps, different_opening=alternate), proof, available
        )
        for alternate in (False, True)
    ]


def ad_coverage(
    trial: AdTrial, topics: Sequence[str], rows: Sequence[dict[str, Any]]
) -> tuple[list[str], dict[str, object]]:
    indexes: dict[str, list[int]] = {}
    for index, row in enumerate(rows, 1):
        for topic, quote in trial.proof.get((row["runId"], row["eventId"]), []):
            indexes.setdefault(topic, []).append(index)
            row.setdefault("topicUses", []).append(
                {
                    "topic": topic,
                    "evidenceKind": "fact",
                    "observationQuote": quote,
                    "rationale": "保留了支持卖点的原录像分析区间。",
                    "sourceStartUs": row["startUs"],
                    "sourceEndUs": row["endUs"],
                }
            )
    coverage = [
        {
            "topic": topic,
            "status": "source-matched"
            if topic in indexes
            else "available"
            if topic in trial.available
            else "missing",
            "shotIndexes": indexes.get(topic, []),
        }
        for topic in dict.fromkeys(topics)
    ]
    notes = [
        f"卖点缺少画面依据：{topic}"
        for topic in dict.fromkeys(topics)
        if topic not in trial.available
    ]
    return notes, {"topicCoverage": coverage, "topicCoverageBasis": "source-matched"}


def stale_spoken_selling_points(
    text: str, original: Sequence[dict[str, Any]], current: Sequence[dict[str, Any]]
) -> tuple[str, ...]:
    retained = {topic for row in current for topic in retained_source_topics(row)}
    return tuple(
        topic
        for topic in dict.fromkeys(
            topic for row in original for topic in retained_source_topics(row)
        )
        if topic not in retained and topic_matches(text, topic)
    )
