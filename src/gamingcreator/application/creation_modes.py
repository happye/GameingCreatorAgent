"""Offline structure templates for the first-product content modes (no model understanding)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from gamingcreator.domain.creation import CreativeBrief

if TYPE_CHECKING:
    from gamingcreator.application.creative_planner import CreationClip

MODE_LABELS = {
    "feature_showcase": "玩法展示",
    "guide": "攻略",
    "campaign": "活动投稿",
    "commentary": "游戏解说",
    "live_cut": "实况精剪",
    "highlight": "高光",
    "ad": "广告/买量",
}
MIN_STEP_SECONDS = Fraction(3, 2)
COMMENTARY_SECONDS = 3


@dataclass(frozen=True, slots=True)
class ModeStructure:
    identity: str
    description: str
    ordered: tuple["CreationClip", ...]
    roles: tuple[str, ...]
    weights: tuple[Fraction, ...]


def _richness(clip: "CreationClip") -> tuple[int, int]:
    """Saved-description detail only; it does not prove visual importance."""
    event = clip.event
    return len(event.observable_facts) + len(event.mechanic_tags), len(
        "".join(event.observable_facts)
    )


Score = Callable[["CreationClip"], float]


def _richest(clips: Sequence["CreationClip"], score: Score) -> "CreationClip":
    # Highest material score, then description detail; max() keeps the earliest on ties.
    return max(clips, key=lambda clip: (score(clip), _richness(clip)))


def _framed(
    opening: "CreationClip",
    middle: list["CreationClip"],
    opening_role: str,
    middle_role: str,
    middle_roles: list[str] | None = None,
) -> tuple[tuple["CreationClip", ...], tuple[str, ...], tuple[Fraction, ...]]:
    ordered = (opening, *middle)
    roles = [opening_role, *(middle_roles or [middle_role] * len(middle))]
    # Only a generic closing clip is relabelled; a topic label is never overwritten.
    if len(ordered) >= 3 and roles[-1] == middle_role:
        roles[-1] = "收尾"
    # The opening hook gets about a quarter of the duration when there is enough material.
    hook = max(Fraction(1), Fraction(len(middle), 3))
    return ordered, tuple(roles), (hook, *[Fraction(1)] * len(middle))


def _cap(brief: CreativeBrief) -> int:
    """How many segments fit at about 1.5 seconds each (at least three)."""
    return max(3, int(brief.target_duration / MIN_STEP_SECONDS))


def _sample(clips: Sequence["CreationClip"], count: int, score: Score) -> list["CreationClip"]:
    """Evenly spaced slots over the existing order; each slot takes the best-scored clip nearby.

    With equal scores every slot keeps its exact evenly spaced clip.
    """
    if count <= 0:
        return []
    if len(clips) <= count:
        return list(clips)
    if count == 1:
        return [max(clips, key=score)]
    slots = sorted({round(i * (len(clips) - 1) / (count - 1)) for i in range(count)})
    radius = (len(clips) - 1) // (count - 1) // 2
    picked: list[int] = []
    for number, slot in enumerate(slots):
        # The first and last slots stay at the recording's ends; only inner slots move.
        reach = 0 if number in (0, len(slots) - 1) else radius
        low = max(slot - reach, picked[-1] + 1 if picked else 0)
        # Leave room for the remaining slots so order and count are preserved.
        high = min(slot + reach, len(clips) - (len(slots) - number))
        window = range(low, max(low, high) + 1)
        picked.append(max(window, key=lambda i: (score(clips[i]), -abs(i - slot))))
    return [clips[i] for i in picked]


def mode_structure(
    brief: CreativeBrief, eligible: Sequence["CreationClip"], score: Score = lambda clip: 0.0
) -> ModeStructure | None:
    if not eligible:
        return None
    if brief.content_type == "feature_showcase":
        opening = _richest(eligible, score)
        middle = _sample([clip for clip in eligible if clip is not opening], _cap(brief) - 1, score)
        ordered, roles, weights = _framed(opening, middle, "开场高光", "玩法展示")
        return ModeStructure(
            "showcase",
            "玩法展示模板：描述最丰富的片段作开场高光，其余按录像顺序展示玩法，最后一段收尾",
            ordered,
            roles,
            weights,
        )
    if brief.content_type == "guide":
        picked = _sample(eligible, _cap(brief), score)
        seconds = brief.target_duration / len(picked)
        return ModeStructure(
            "guide-steps",
            f"攻略模板：按录像先后均匀取{len(picked)}步，每步目标约{seconds:.1f}秒",
            tuple(picked),
            tuple(f"第{i + 1}步" for i in range(len(picked))),
            tuple(Fraction(1) for _ in picked),
        )
    if brief.content_type == "campaign":
        used: list[CreationClip] = []
        topic_roles: list[str] = []
        for topic in brief.mandatory_topics:
            match = next(
                (
                    clip
                    for clip in eligible
                    if clip not in used
                    and topic.casefold()
                    in " ".join(clip.event.observable_facts + clip.event.mechanic_tags).casefold()
                ),
                None,
            )
            if match is not None:
                used.append(match)
                topic_roles.append(f"活动主题：{topic}")
        rest = [clip for clip in eligible if clip not in used]
        opening = _richest(rest, score) if rest else used.pop(0)
        if not rest:
            topic_roles.pop(0)
        remaining = _sample(
            [clip for clip in rest if clip is not opening], _cap(brief) - 1 - len(used), score
        )
        middle = used + remaining
        middle_roles = topic_roles + ["活动亮点"] * len(remaining)
        ordered, final_roles, weights = _framed(opening, middle, "开场", "活动亮点", middle_roles)
        return ModeStructure(
            "campaign-topics",
            "活动投稿模板：开场后先放命中必须主题的片段（按主题顺序），再放其他亮点，最后一段收尾",
            ordered,
            final_roles,
            weights,
        )
    if brief.content_type == "commentary":
        # Longer shots leave room for spoken commentary over each segment.
        count = max(3, int(brief.target_duration / COMMENTARY_SECONDS))
        picked = _sample(eligible, count, score)
        segment_roles = ["开场", *[f"解说段{i}" for i in range(1, len(picked) - 1)], "结尾"][
            : len(picked)
        ]
        if len(picked) == 2:
            segment_roles = ["开场", "结尾"]
        return ModeStructure(
            "commentary-segments",
            f"游戏解说模板：按录像顺序取{len(picked)}段较长镜头（约{COMMENTARY_SECONDS}秒/段），给解说留出说话时间",
            tuple(picked),
            tuple(segment_roles),
            tuple(Fraction(1) for _ in picked),
        )
    if brief.content_type == "live_cut":
        picked = _sample(eligible, _cap(brief), score)
        return ModeStructure(
            "live-cut",
            f"实况精剪模板：保持录像先后顺序，紧凑取{len(picked)}段（约1.5秒/段），每段取附近评分最高的片段",
            tuple(picked),
            tuple(f"实况{i + 1}" for i in range(len(picked))),
            tuple(Fraction(1) for _ in picked),
        )
    if brief.content_type == "highlight":
        # Best-scored clips, shown in recording order, with the single best saved for last.
        best = sorted(eligible, key=lambda clip: (-score(clip), eligible.index(clip)))[
            : _cap(brief)
        ]
        climax = best[0]
        rest = sorted((clip for clip in best[1:]), key=eligible.index)
        ordered_clips = (*rest, climax)
        return ModeStructure(
            "highlight-climax",
            f"高光模板：取评分最高的{len(ordered_clips)}段，按录像顺序播放，最高分片段放在最后作高潮",
            ordered_clips,
            tuple([*[f"高光{i + 1}" for i in range(len(rest))], "高潮"]),
            tuple([*[Fraction(1)] * len(rest), Fraction(3, 2)]),
        )
    if brief.content_type == "ad":
        hook = _richest(eligible, score)
        topic_clips = [
            clip
            for topic in brief.mandatory_topics
            for clip in eligible
            if clip is not hook
            and topic.casefold()
            in " ".join(clip.event.observable_facts + clip.event.mechanic_tags).casefold()
        ]
        selling: list[CreationClip] = []
        for clip in topic_clips:
            if clip not in selling:
                selling.append(clip)
        others = sorted(
            (clip for clip in eligible if clip is not hook and clip not in selling),
            key=lambda clip: (-score(clip), eligible.index(clip)),
        )
        # Short ads: hook, up to three selling points, a call to action.
        points = (selling + others)[:3]
        closing = [clip for clip in others if clip not in points][:1]
        ordered_clips = (hook, *points, *closing)
        ad_roles = ["开场钩子", *["卖点"] * len(points), *["行动号召"] * len(closing)]
        hook_weight = max(Fraction(1), Fraction(len(ordered_clips) - 1, 3))
        return ModeStructure(
            "ad-hook",
            "广告/买量模板：最高分片段作开场钩子，接最多3个卖点（优先命中必须主题），最后一段行动号召",
            ordered_clips,
            tuple(ad_roles),
            (hook_weight, *[Fraction(1)] * (len(ordered_clips) - 1)),
        )
    return None
