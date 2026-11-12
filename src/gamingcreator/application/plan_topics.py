"""Versioned topic suggestions bound to verbatim candidate observations."""

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from gamingcreator.application.creation_proposals import canonical

if TYPE_CHECKING:
    from gamingcreator.application.plan_proposals import PlanSnapshot


def with_topics(snapshot: "PlanSnapshot") -> "PlanSnapshot":
    if not snapshot.brief.mandatory_topics:
        return snapshot
    payload = snapshot.payload
    payload.update(
        schemaVersion="plan-snapshot-v3",
        topicMapping={
            "schemaVersion": "plan-topics-v1",
            "topics": list(snapshot.brief.mandatory_topics),
        },
    )
    return replace(snapshot, payload_json=canonical(payload))


def validate_topic_uses(snapshot: "PlanSnapshot", shot: dict[str, Any]) -> None:
    topics = snapshot.brief.mandatory_topics
    uses = shot["topicUses"]
    if not isinstance(uses, list) or len(uses) > len(topics):
        raise ValueError("Invalid topic references.")
    candidate = next(
        row for row in snapshot.payload["candidates"] if row["candidateId"] == shot["candidateId"]
    )
    observations = candidate["facts"] + candidate["tags"]
    seen = set()
    for use in uses:
        if not isinstance(use, dict) or set(use) != {"topic", "rationale", "observationQuote"}:
            raise ValueError("Invalid topic reference fields.")
        topic = use["topic"]
        if not isinstance(topic, str) or topic not in topics or topic in seen:
            raise ValueError("Unknown or repeated topic.")
        for key in ("rationale", "observationQuote"):
            text = use[key]
            if not isinstance(text, str) or not text.strip() or len(text) > 500:
                raise ValueError("Invalid bounded topic text.")
        if not any(use["observationQuote"] in text for text in observations):
            raise ValueError("Topic observation quote is not verbatim candidate evidence.")
        seen.add(topic)


def compiled_topics(snapshot: "PlanSnapshot", segments: list[dict[str, Any]]) -> dict[str, Any]:
    if "topicMapping" not in snapshot.payload:
        return {}
    coverage = []
    for topic in snapshot.brief.mandatory_topics:
        indexes = [
            index
            for index, segment in enumerate(segments, 1)
            if any(use["topic"] == topic for use in segment["topicUses"])
        ]
        coverage.append(
            {
                "topic": topic,
                "status": "ai-suggested" if indexes else "missing",
                "shotIndexes": indexes,
            }
        )
    return {"topicCoverage": coverage}


def topic_advisories(snapshot: "PlanSnapshot", segments: list[dict[str, Any]]) -> list[str]:
    if "topicMapping" in snapshot.payload:
        return [
            f"缺少主题映射：{row['topic']}（请预览核对或补充镜头）"
            for row in compiled_topics(snapshot, segments)["topicCoverage"]
            if row["status"] == "missing"
        ]
    text = " ".join(s["scriptDraft"] for s in segments).casefold()
    return [
        f"主题未在画面摘要中找到：{topic}（可在旁白或字幕里讲，或补充画面）"
        for topic in snapshot.brief.mandatory_topics
        if topic.casefold() not in text
    ]
