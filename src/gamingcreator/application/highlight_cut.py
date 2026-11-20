"""Select bounded gameplay highlights from saved observations and neighboring footage."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from gamingcreator.application.creation_modes import StructureAllocation
from gamingcreator.application.showcase_topics import topic_matches
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.time import SourceRange

if TYPE_CHECKING:
    from gamingcreator.application.creation_modes import Score
    from gamingcreator.application.creative_planner import CreationClip

_RULES = tuple(
    (label, re.compile(fact, re.I), re.compile(tag, re.I))
    for label, fact, tag in (
        ("反杀", r"反杀", r"反杀|counter.?kill"),
        ("连杀", r"连杀|双杀|三杀|四杀|五杀", r"连杀|双杀|三杀|四杀|五杀|multi.?kill"),
        ("击杀", r"击杀|击毙", r"击杀|kill"),
        ("稀有掉落", r"稀有掉落|掉落.{0,8}(?:稀有|传说|史诗)", r"稀有掉落|rare.?drop"),
        ("极限操作", r"极限(?:闪避|操作|反应)|丝血存活", r"极限操作|极限闪避"),
        ("Boss 攻击", r"(?<![a-z])boss.{0,12}(?:攻击|挥|扑|释放)", r"boss\s*攻击"),
        (
            "击倒",
            r"击倒|(?:击中|命中|攻击).{0,14}(?:后仰|随后|向侧方)?倒地",
            r"击倒|敌人倒地|knockdown",
        ),
        ("主播反应", r"(?:主播|玩家).{0,8}(?:大笑|欢呼|惊呼|尖叫)", r"主播反应|主播欢呼"),
        ("搞笑事件", r"搞笑事件|意外.{0,12}(?:引发笑声|惹得主播大笑)", r"搞笑事件"),
    )
)
_AMBIGUOUS = re.compile(
    r"未|无法|不确定|不曾|并非|不是|可能|疑似|似乎|没有|没被|或|"
    r"(?:击杀|连杀|掉落)(?:数|数量)?\s*[：:=]?\s*(?:为|是)?\s*[0０](?!\d)|[0０](?:次|个)?击杀"
)
_CUT = re.compile(r"(?:画面|场景|镜头)(?:又|随后)?切换|转场|过场动画")
_MAX_GAP_US = 600_000
_CONTEXT_SECONDS = 2


@dataclass(frozen=True, slots=True)
class Highlight:
    label: str
    kind: str
    quote: str
    priority: int


@dataclass(slots=True)
class HighlightCut:
    allocation: StructureAllocation
    hints: dict[tuple[str, str], Highlight]


def _matches(clip: "CreationClip") -> Highlight | None:
    event = clip.event
    clauses = [
        (fact, clause)
        for fact in event.observable_facts
        for clause in re.split(r"[，,；;。！？]", fact)
        if clause.strip() and not _AMBIGUOUS.search(clause)
    ]
    for priority, (label, fact_pattern, tag_pattern) in enumerate(_RULES):
        if event.modality == "audio" and label not in ("主播反应", "搞笑事件"):
            continue
        if fact_pattern.search(event.uncertainty or ""):
            continue
        fact = next((fact for fact, clause in clauses if fact_pattern.search(clause)), "")
        if fact:
            return Highlight(label, "fact", fact, priority)
        tag = next((tag for tag in event.mechanic_tags if tag_pattern.fullmatch(tag.strip())), "")
        if tag and not any(
            fact_pattern.search(fact) and _AMBIGUOUS.search(fact) for fact in event.observable_facts
        ):
            return Highlight(label, "tag", tag, priority)
    return None


def _frames(clip: "CreationClip", fps: int) -> int:
    return (clip.framing.end_us - clip.framing.start_us) * fps // 1_000_000


def _overlaps(candidate: "CreationClip", chosen: Sequence["CreationClip"]) -> bool:
    range_ = candidate.framing
    return any(
        candidate.asset.sha256 == clip.asset.sha256
        and range_.start_us < clip.framing.end_us
        and clip.framing.start_us < range_.end_us
        for clip in chosen
    )


def _fit_context(
    clip: "CreationClip", edge: int, before: bool, frames: int, fps: int
) -> "CreationClip | None":
    bounded = clip.framing
    observed = clip.event.source_range
    start, end = max(bounded.start_us, observed.start_us), min(bounded.end_us, observed.end_us)
    length = (frames * 1_000_000 + fps - 1) // fps
    # A neighbor contributes only the part on its own side of the highlight.
    if before:
        end = min(end, edge)
        start = max(start, end - length)
        gap = edge - end
    else:
        start = max(start, edge)
        end = min(end, start + length)
        gap = start - edge
    if gap > _MAX_GAP_US or (end - start) * fps < 1_000_000:
        return None
    return replace(clip, source_range=SourceRange(start, end, bounded.duration_us))


def _context(
    center: "CreationClip",
    candidates: Sequence["CreationClip"],
    chosen: Sequence["CreationClip"],
    before: bool,
    frames: int,
    fps: int,
) -> "CreationClip | None":
    if not frames:
        return None
    edge = center.framing.start_us if before else center.framing.end_us
    options = [
        bounded
        for clip in candidates
        if clip.event.run_id == center.event.run_id
        and clip.event.event_id != center.event.event_id
        and not any(_CUT.search(fact) for fact in clip.event.observable_facts)
        and (bounded := _fit_context(clip, edge, before, frames, fps)) is not None
        and not _overlaps(bounded, chosen)
    ]
    return max(
        options,
        key=lambda clip: (
            clip.framing.end_us if before else -clip.framing.start_us,
            _frames(clip, fps),
        ),
        default=None,
    )


def highlight_cut(
    brief: CreativeBrief, candidates: Sequence["CreationClip"], fps: int, score: "Score"
) -> HighlightCut | None:
    matches = []
    for clip in candidates:
        observation = clip.event.source_range
        if (
            clip.framing.start_us <= observation.start_us
            and clip.framing.end_us >= observation.end_us
        ):
            hint = _matches(clip)
            if hint is not None:
                matches.append((replace(clip, source_range=None), hint))

    def rank(item: tuple["CreationClip", Highlight]) -> tuple[int, int, bool, float]:
        clip, hint = item
        text = "；".join((hint.label, *clip.event.observable_facts))
        covered = sum(topic_matches(text, topic) for topic in brief.mandatory_topics)
        return covered, -hint.priority, hint.kind == "fact", score(clip)

    remaining = brief.target_duration * fps
    selected: list[CreationClip] = []
    roles: dict[int, str] = {}
    hints: dict[tuple[str, str], Highlight] = {}
    for center, hint in sorted(matches, key=rank, reverse=True):
        frames = _frames(center, fps)
        if not 0 < frames <= remaining or _overlaps(center, selected):
            continue
        selected.append(center)
        roles[id(center)] = f"高光 · {hint.label}"
        hints[(center.event.run_id, center.event.event_id)] = hint
        remaining -= frames
        for before, role in ((True, "铺垫"), (False, "后续画面")):
            allowance = (remaining + 1) // 2 if before else remaining
            neighbor = _context(
                center, candidates, selected, before, min(_CONTEXT_SECONDS * fps, allowance), fps
            )
            if neighbor is not None:
                selected.append(neighbor)
                roles[id(neighbor)] = role
                remaining -= _frames(neighbor, fps)
    if not selected:
        return None
    order = {
        run: index for index, run in enumerate(dict.fromkeys(c.event.run_id for c in candidates))
    }
    selected.sort(key=lambda clip: (order[clip.event.run_id], clip.framing.start_us))
    notes = ["高光按完整分析区间取材。前后镜头来自同一录像，间隙或转场请在预览中核对。"]
    if len(selected) < 3 * len(hints):
        notes.append("部分高光缺少可用铺垫或后续画面。")
    if remaining:
        notes.append("有明确依据的高光和相邻画面短于目标时长，可补素材或手动加镜头。")
    return HighlightCut(
        StructureAllocation(
            "highlight-evidence",
            "高光精选：按已保存的事件证据取材，保留可用的前后画面",
            [[clip] for clip in selected],
            [_frames(clip, fps) for clip in selected],
            tuple(roles[id(clip)] for clip in selected),
            notes,
        ),
        hints,
    )


def highlight_coverage(
    selection: HighlightCut, segments: Sequence[dict[str, Any]]
) -> dict[str, object]:
    coverage: dict[str, list[int]] = {}
    for index, row in enumerate(segments, 1):
        hint = selection.hints.get((row["runId"], row["eventId"]))
        if hint is None or row.get("role") != f"高光 · {hint.label}":
            continue
        coverage.setdefault(hint.label, []).append(index)
        row["topicUses"] = [
            {
                "topic": hint.label,
                "evidenceKind": hint.kind,
                "observationQuote": hint.quote,
                "rationale": "已保存的素材记录支持这类高光。",
                "sourceStartUs": row["startUs"],
                "sourceEndUs": row["endUs"],
            }
        ]
    return {
        "topicCoverageBasis": "source-matched",
        "topicCoverage": [
            {"topic": label, "status": "source-matched", "shotIndexes": indexes}
            for label, indexes in coverage.items()
        ],
    }


def retained_highlights(row: dict[str, Any]) -> list[str]:
    """A trimmed or replaced highlight no longer supports its original category label."""
    return [
        use["topic"]
        for use in row.get("topicUses", [])
        if (use.get("sourceStartUs"), use.get("sourceEndUs")) == (row["startUs"], row["endUs"])
    ]
