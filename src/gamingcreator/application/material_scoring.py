"""Explicit material scores (master plan §25) with unmeasured dimensions kept unknown.

Weights are the plan's manual V0.1 weights. A dimension without an offline basis is None and
is excluded from the total; the result states how much of the weight was actually measured.
"""

from collections import Counter
from collections.abc import Sequence
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from gamingcreator.domain.creation import CreativeBrief

if TYPE_CHECKING:
    from gamingcreator.application.creative_planner import CreationClip

WEIGHTS = {
    "briefMatch": Fraction(25, 100),
    "visualQuality": Fraction(15, 100),
    "gameplayClarity": Fraction(15, 100),
    "emotionalIntensity": Fraction(10, 100),
    "narrativeValue": Fraction(10, 100),
    "novelty": Fraction(10, 100),
    "platformFit": Fraction(10, 100),
    "technicalQuality": Fraction(5, 100),
}
BASIS = {
    "briefMatch": "已保存描述命中必须主题的比例",
    "gameplayClarity": "代理：可观察事实与玩法标签数量",
    "novelty": "代理：候选中已保存描述的独特程度",
    "platformFit": "代理：可用时长（≥1.5秒为满分），未核对平台规格",
    "technicalQuality": "代理：分析是否标注不确定",
}
UNKNOWN = "暂无离线依据，保持未知"
FULL_SECONDS = Fraction(3, 2)


def _text(clip: "CreationClip") -> str:
    return " ".join(clip.event.observable_facts + clip.event.mechanic_tags).casefold()


def score_materials(
    brief: CreativeBrief, clips: Sequence["CreationClip"]
) -> dict[tuple[str, str], dict[str, Any]]:
    """Scores keyed by (runId, eventId); identical for every plan built from these clips."""
    descriptions = Counter("；".join(clip.event.observable_facts) for clip in clips)
    topics = [topic.casefold() for topic in brief.mandatory_topics]
    scores: dict[tuple[str, str], dict[str, Any]] = {}
    for clip in clips:
        event = clip.event
        seconds = Fraction(clip.framing.end_us - clip.framing.start_us, 1_000_000)
        parts: dict[str, Fraction | None] = {name: None for name in WEIGHTS}
        if topics:
            parts["briefMatch"] = Fraction(
                sum(topic in _text(clip) for topic in topics), len(topics)
            )
        parts["gameplayClarity"] = min(
            Fraction(1), Fraction(len(event.observable_facts) + len(event.mechanic_tags), 3)
        )
        parts["novelty"] = Fraction(1, descriptions["；".join(event.observable_facts)])
        parts["platformFit"] = min(Fraction(1), seconds / FULL_SECONDS)
        parts["technicalQuality"] = Fraction(1, 2) if event.uncertainty else Fraction(1)
        known = {name: value for name, value in parts.items() if value is not None}
        coverage = sum((WEIGHTS[name] for name in known), Fraction(0))
        total = sum((WEIGHTS[name] * value for name, value in known.items()), Fraction(0))
        scores[(event.run_id, event.event_id)] = {
            "version": "material-score-v1",
            "total": round(float(total / coverage), 3) if coverage else None,
            "coverage": round(float(coverage), 2),
            "parts": {
                name: None if value is None else round(float(value), 3)
                for name, value in parts.items()
            },
        }
    return scores


def scoring_legend() -> dict[str, Any]:
    return {
        "version": "material-score-v1",
        "weights": {name: float(weight) for name, weight in WEIGHTS.items()},
        "basis": {name: BASIS.get(name, UNKNOWN) for name in WEIGHTS},
        "note": "权重为总方案V0.1人工权重；未知维度不计入总分，coverage为已测维度权重之和。",
    }


def advisories(
    brief: CreativeBrief,
    clips: Sequence["CreationClip"],
    segments: Sequence[dict[str, Any]],
    fps: int,
) -> list[str]:
    """Non-blocking material gaps with concrete suggestions (blocking gaps stay elsewhere)."""
    notes: list[str] = []
    wanted = max(3, int(brief.target_duration / FULL_SECONDS))
    if len(clips) < wanted:
        notes.append(
            f"素材偏少：只有{len(clips)}个可用片段，按约1.5秒一个镜头建议至少{wanted}个；"
            "可在分析时多选录像或补拍更多玩法。"
        )
    available = sum(
        (Fraction(c.framing.end_us - c.framing.start_us, 1_000_000) for c in clips),
        Fraction(0),
    )
    if available < brief.target_duration:
        notes.append(
            f"时长不足：全部可用片段合计约{float(available):.1f}秒，少于目标{brief.target_duration}秒，"
            "成片会短于目标；可补充录像或调低目标秒数。"
        )
    output = sum(int(s["outputFrames"]) for s in segments) / fps if segments else 0.0
    if segments and output < brief.target_duration * 0.8:
        notes.append(f"成片约{output:.1f}秒，明显短于目标{brief.target_duration}秒。")
    if len({c.asset.sha256 for c in clips}) == 1 and len(clips) > 1:
        notes.append("单一来源：全部片段来自同一段录像，画面可能单调；可多选不同录像。")
    for topic in brief.mandatory_topics:
        hits = sum(topic.casefold() in _text(c) for c in clips)
        if hits == 1:
            notes.append(f"主题“{topic}”只有1个片段，无法换镜头；可补充相关录像。")
    return notes
