"""Evidence-backed topic placement for the offline gameplay showcase."""

import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gamingcreator.application.creative_planner import CreationClip


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _topic_match(text: str, topic: str) -> bool:
    wanted = _normalize(topic).strip()
    source = _normalize(text)
    if re.fullmatch(r"[a-z0-9]+", wanted):
        return re.search(rf"(?<![a-z0-9]){re.escape(wanted)}(?![a-z0-9])", source) is not None
    return bool(wanted and wanted in source)


def _evidence(clip: "CreationClip", topic: str) -> tuple[str, str] | None:
    event = clip.event
    if event.modality == "audio":
        return None
    fact = next((text for text in event.observable_facts if _topic_match(text, topic)), None)
    if fact is not None:
        return "fact", fact
    tag = next(
        (
            tag
            for tag in event.mechanic_tags
            if _normalize(tag).strip() == _normalize(topic).strip()
        ),
        None,
    )
    if tag is not None:
        return "tag", tag
    return None


def gameplay_opening(clip: "CreationClip") -> bool:
    event = clip.event
    if event.modality == "audio" or event.uncertainty:
        return False
    markers = ("技能释放", "技能特效", "伤害数字", "驾驶操作", "零件切换", "参数变化", "释放技能")
    return any(
        marker in text
        for text in (*event.mechanic_tags, *event.observable_facts)
        for marker in markers
    )


def reserve_topics(
    topics: Sequence[str],
    clips: Sequence["CreationClip"],
    opening: "CreationClip",
    limit: int,
    score: Callable[["CreationClip"], float],
) -> list["CreationClip"]:
    remaining = [topic for topic in topics if _evidence(opening, topic) is None]
    available = {
        id(clip): {topic for topic in remaining if _evidence(clip, topic) is not None}
        for clip in clips
        if clip is not opening
    }
    chosen: list[CreationClip] = []
    for topic in remaining:
        if len(chosen) >= limit:
            break
        options = [clip for clip in clips if topic in available.get(id(clip), ())]
        if not options:
            continue
        pick = max(
            options,
            key=lambda clip: (len(available[id(clip)]), not clip.event.uncertainty, score(clip)),
        )
        chosen.append(pick)
        covered = available.pop(id(pick))
        for matches in available.values():
            matches.difference_update(covered)
    return chosen


def showcase_coverage(
    topics: Sequence[str], candidates: Sequence["CreationClip"], segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_event = {(clip.event.run_id, clip.event.event_id): clip for clip in candidates}
    coverage: list[dict[str, Any]] = []
    for topic in topics:
        indexes = []
        for index, segment in enumerate(segments, 1):
            clip = by_event[(segment["runId"], segment["eventId"])]
            match = _evidence(clip, topic)
            if match is not None:
                kind, quote = match
                indexes.append(index)
                segment.setdefault("topicUses", []).append(
                    {
                        "topic": topic,
                        "evidenceKind": kind,
                        "observationQuote": quote,
                        "rationale": "原分析区间的摘要或标签与主题匹配。",
                    }
                )
        status = (
            "source-matched"
            if indexes
            else "available"
            if any(_evidence(clip, topic) for clip in candidates)
            else "missing"
        )
        coverage.append({"topic": topic, "status": status, "shotIndexes": indexes})
    return coverage
