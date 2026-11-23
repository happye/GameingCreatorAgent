"""Evidence-backed topic placement for the offline gameplay showcase."""

import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gamingcreator.application.creative_planner import CreationClip
    from gamingcreator.application.storage import StoredTimeline
    from gamingcreator.domain.models import SemanticEvent

_GAMEPLAY_MARKERS = (
    "技能释放",
    "技能特效",
    "伤害数字",
    "驾驶操作",
    "零件切换",
    "参数变化",
    "释放技能",
)
FACTS_ONLY_PLAN_IDS = frozenset({"guide-evidence", "commentary-evidence"})


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def topic_matches(text: str, topic: str) -> bool:
    wanted = _normalize(topic).strip()
    source = _normalize(text)
    if re.fullmatch(r"[a-z0-9]+", wanted):
        return re.search(rf"(?<![a-z0-9]){re.escape(wanted)}(?![a-z0-9])", source) is not None
    return bool(wanted and wanted in source)


def same_topic_label(text: str, topic: str) -> bool:
    return _normalize(text).strip() == _normalize(topic).strip()


def retained_source_uses(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Original claims that still have their full saved source span."""
    start, end = row.get("startUs"), row.get("endUs")
    if type(start) is not int or type(end) is not int:
        return []
    return [
        use
        for use in row.get("topicUses", [])
        if (use.get("sourceStartUs"), use.get("sourceEndUs")) == (start, end)
    ]


def retained_source_topics(row: dict[str, Any]) -> list[str]:
    return [use["topic"] for use in retained_source_uses(row)]


def mentions_gameplay(text: str) -> bool:
    return any(marker in text for marker in _GAMEPLAY_MARKERS)


def _evidence(clip: "CreationClip", topic: str, facts_only: bool) -> tuple[str, str] | None:
    return _event_evidence(clip.event, topic, facts_only)


def _event_evidence(event: "SemanticEvent", topic: str, facts_only: bool) -> tuple[str, str] | None:
    if event.modality == "audio":
        return None
    fact = next((text for text in event.observable_facts if topic_matches(text, topic)), None)
    if fact is not None:
        return "fact", fact
    if facts_only:
        return None
    tag = next(
        (tag for tag in event.mechanic_tags if same_topic_label(tag, topic)),
        None,
    )
    if tag is not None:
        return "tag", tag
    return None


def candidate_source_identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return row["runId"], row["eventId"], row["mediaId"], row["sourceSha256"]


def candidate_topic_projector(
    timelines: Sequence["StoredTimeline"], topics: Sequence[str], *, plan_id: str
) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Bind exact required-topic quotes to candidate intervals in verified timelines."""
    facts_only = plan_id in FACTS_ONLY_PLAN_IDS
    events = (
        {
            (
                timeline.run.run_id,
                event.event_id,
                timeline.run.asset.media_id,
                timeline.run.asset.sha256,
            ): event
            for timeline in timelines
            for event in timeline.events
            if event.run_id == timeline.run.run_id and event.media_id == timeline.run.asset.media_id
        }
        if topics
        else {}
    )

    def project(row: dict[str, Any]) -> dict[str, Any] | None:
        if not events:
            return None
        run, event_id, media, sha256 = candidate_source_identity(row)
        event = events.get((run, event_id, media, sha256))
        if event is None or event.modality == "audio":
            return None
        start, end = row["startUs"], row["endUs"]
        span = event.source_range
        if not span.start_us <= start < end <= span.end_us:
            return None
        matches = [
            {"topic": topic, "evidenceKind": evidence[0], "observationQuote": evidence[1]}
            for topic in topics
            if (evidence := _event_evidence(event, topic, facts_only)) is not None
        ]
        if not matches:
            return None
        return {
            "runId": run,
            "eventId": event_id,
            "mediaId": media,
            "sourceSha256": sha256,
            "sourceStartUs": span.start_us,
            "sourceEndUs": span.end_us,
            "matches": matches,
        }

    return project


def gameplay_opening(clip: "CreationClip") -> bool:
    event = clip.event
    if event.modality == "audio" or event.uncertainty:
        return False
    return any(mentions_gameplay(text) for text in (*event.mechanic_tags, *event.observable_facts))


def visual_topic_count(clip: "CreationClip", topics: Sequence[str]) -> int:
    return sum(_evidence(clip, topic, True) is not None for topic in topics)


def reserve_topics(
    topics: Sequence[str],
    clips: Sequence["CreationClip"],
    opening: "CreationClip | None",
    limit: int,
    score: Callable[["CreationClip"], float],
    *,
    facts_only: bool = False,
) -> list["CreationClip"]:
    remaining = [
        topic
        for topic in topics
        if opening is None or _evidence(opening, topic, facts_only) is None
    ]
    available = {
        id(clip): {topic for topic in remaining if _evidence(clip, topic, facts_only) is not None}
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
    topics: Sequence[str],
    candidates: Sequence["CreationClip"],
    segments: list[dict[str, Any]],
    *,
    step_seeds: set[tuple[str, str]] | None = None,
    facts_only: bool = False,
) -> list[dict[str, Any]]:
    by_event = {(clip.event.run_id, clip.event.event_id): clip for clip in candidates}
    coverage: list[dict[str, Any]] = []
    for topic in topics:
        indexes = []
        for index, segment in enumerate(segments, 1):
            key = (segment["runId"], segment["eventId"])
            if step_seeds is not None and key not in step_seeds:
                continue
            match = _evidence(by_event[key], topic, facts_only)
            if match is not None:
                kind, quote = match
                indexes.append(index)
                segment.setdefault("topicUses", []).append(
                    {
                        "topic": topic,
                        "evidenceKind": kind,
                        "observationQuote": quote,
                        "rationale": "原录像摘要包含此主题。"
                        if facts_only
                        else "原分析区间的摘要或标签与主题匹配。",
                    }
                )
                if facts_only:
                    break
        status = (
            "source-matched"
            if indexes
            else "available"
            if any(_evidence(clip, topic, facts_only) for clip in candidates)
            else "missing"
        )
        coverage.append({"topic": topic, "status": status, "shotIndexes": indexes})
    return coverage
