"""Pure template planner over explicitly loaded, verified saved timelines."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamingcreator.application.ad_cut import AdTrial, ad_coverage, ad_trials
from gamingcreator.application.creation_feedback import (
    TRIM_TIP,
    CreatorStructureChoice,
    normalize_edit_kinds,
    trim_suggestion,
)
from gamingcreator.application.creation_modes import (
    MODE_HONESTY_SHORT,
    MODE_LABELS,
    Score,
    StructureAllocation,
    mode_structure,
    sample_clips,
)
from gamingcreator.application.highlight_cut import HighlightCut, highlight_coverage, highlight_cut
from gamingcreator.application.live_cut import live_cut
from gamingcreator.application.material_scoring import (
    VisualSample,
    advisories,
    score_materials,
    scoring_legend,
)
from gamingcreator.application.showcase_topics import showcase_coverage, visual_topic_count
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.media import MediaAsset
from gamingcreator.domain.models import SemanticEvent, TranscriptSegment
from gamingcreator.domain.time import SourceRange

# Generic structures keep shots at two seconds or longer instead of slicing every event.
GENERIC_SHOT_SECONDS = 2


def segment_content_key(segment: dict[str, object]) -> tuple[str, str, int, int, int]:
    """Run, footage hash, source span and output length of one final renderable clip."""
    start_us, end_us, output_frames = (
        segment["startUs"],
        segment["endUs"],
        segment["outputFrames"],
    )
    if type(start_us) is not int or type(end_us) is not int or type(output_frames) is not int:
        raise TypeError("片段时钟字段不是整数。")
    return (
        str(segment["runId"]),
        str(segment["sourceSha256"]),
        start_us,
        end_us,
        output_frames,
    )


def plan_content_signature(segments: Sequence[dict[str, object]]) -> str:
    """Identity of the ordered final segments. Template names, IDs and filenames do not count."""
    payload = [
        {
            "runId": run_id,
            "sourceSha256": source,
            "startUs": start,
            "endUs": end,
            "outputFrames": frames,
        }
        for run_id, source, start, end, frames in (segment_content_key(row) for row in segments)
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def unique_rule_plans(plans: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Drop later candidates with the same final content. Incoming preference order is kept."""
    seen: set[str] = set()
    kept: list[dict[str, object]] = []
    for plan in plans:
        signature = str(plan["contentSignature"])
        if signature in seen:
            continue
        seen.add(signature)
        kept.append(plan)
    return kept


def _prefer_structure(
    plans: list[dict[str, object]], feedback: CreatorStructureChoice | None
) -> bool:
    if feedback is None:
        return False
    for index, plan in enumerate(plans):
        if plan["id"] == feedback.source_plan_id and plan["ready"]:
            plan["rankedByCreatorFeedback"] = True
            plans.insert(0, plans.pop(index))
            return True
    return False


def _plan_topic_details(
    brief: CreativeBrief,
    identity: str,
    eligible: list["CreationClip"],
    segments: list[dict[str, Any]],
    *,
    step_seeds: set[tuple[str, str]] | None = None,
    highlight: HighlightCut | None = None,
    ad_trial: AdTrial | None = None,
) -> tuple[list[str], dict[str, object]]:
    if ad_trial is not None:
        return ad_coverage(ad_trial, brief.mandatory_topics, segments)
    if identity in ("showcase", "guide-evidence", "commentary-evidence") and brief.mandatory_topics:
        coverage = showcase_coverage(
            brief.mandatory_topics,
            eligible,
            segments,
            step_seeds=step_seeds,
            facts_only=identity != "showcase",
        )
        if step_seeds is not None:
            steps = (row for row in segments if row.get("topicUses"))
            for number, row in enumerate(steps, 1):
                row["guideStep"] = "、".join(use["topic"] for use in row["topicUses"])
                row["role"] = f"第{number}步"
        if identity == "commentary-evidence":
            for row in segments:
                if row.get("topicUses"):
                    row["role"] = "解说 · " + "、".join(use["topic"] for use in row["topicUses"])
        notes = [
            f"缺少主题映射：{row['topic']}（素材记录中未找到，请补充画面或在旁白说明）"
            if row["status"] == "missing"
            else f"缺少主题映射：{row['topic']}（素材中已有描述，本版未排入，请加镜头或延长时长）"
            for row in coverage
            if row["status"] != "source-matched"
        ]
        return notes, {"topicCoverage": coverage, "topicCoverageBasis": "source-matched"}
    fields = highlight_coverage(highlight, segments) if highlight is not None else {}
    text = " ".join(
        " ".join([segment["scriptDraft"], *(use["topic"] for use in segment.get("topicUses", []))])
        for segment in segments
    ).casefold()
    return [
        f"主题未在画面摘要中找到：{topic}（可在旁白或字幕里讲，或补充画面）"
        for topic in brief.mandatory_topics
        if topic.casefold() not in text
    ], fields


def distinct_source_intervals(clips: Sequence[Any]) -> int:
    """Count usable source ranges, not template names or run copies of the same interval."""
    return len({(clip.asset.sha256, clip.framing.start_us, clip.framing.end_us) for clip in clips})


def candidate_count_reason(
    plans: Sequence[dict[str, object]], distinct_intervals: int
) -> str | None:
    """Explain why fewer than three content-distinct rule plans remain; never invent a pad."""
    count = len(plans)
    if count >= 3:
        return None
    no_pad = "不会用重复画面、缩短时长或丢掉观察点来凑满 3 套。"
    if distinct_intervals <= 0:
        return f"没有可用的不同素材，所以现在只有 {count} 套方案。{no_pad}"
    if distinct_intervals < 3:
        return (
            f"可用素材只有 {distinct_intervals} 条不同内容，最多只能给出 {count} 套方案。{no_pad}"
        )
    return f"按最终可渲染内容去重后只剩 {count} 套不同方案。{no_pad}"


@dataclass(frozen=True, slots=True)
class CreationClip:
    asset: MediaAsset
    event: SemanticEvent
    source_range: SourceRange | None = None

    @property
    def framing(self) -> SourceRange:
        return self.source_range or self.event.source_range


PlanTemplate = tuple[
    str, str, list[CreationClip], tuple[str, ...] | None, tuple[Fraction, ...] | None
]


def candidates(
    timelines: tuple[StoredTimeline, ...], event_ids: tuple[str, ...], clip_ranges: object = None
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
    ranges = validate_clip_ranges(clip_ranges, event_ids)
    result = []
    for key, clip in found.items():
        if event_ids and key not in event_ids:
            continue
        if key in ranges:
            row = ranges[key]
            if row["runId"] != clip.event.run_id:
                raise ValueError("Selected range belongs to another run.")
            source = selected_source_range(row, clip.event, clip.asset.duration_us)
            clip = CreationClip(clip.asset, clip.event, source)
        result.append(clip)
    return tuple(result)


def validate_clip_ranges(value: object, event_ids: tuple[str, ...]) -> dict[str, dict[str, object]]:
    if value is None:
        return {}
    if not isinstance(value, list) or not value or len(value) != len(event_ids):
        raise ValueError("Clip ranges must match selected events.")
    result: dict[str, dict[str, object]] = {}
    for row in value:
        if (
            not isinstance(row, dict)
            or set(row) != {"runId", "eventId", "startUs", "endUs"}
            or not isinstance(row["eventId"], str)
            or not isinstance(row["runId"], str)
            or type(row["startUs"]) is not int
            or type(row["endUs"]) is not int
            or not 0 <= row["startUs"] < row["endUs"]
            or row["eventId"] in result
        ):
            raise ValueError("Invalid or duplicate clip range.")
        result[row["eventId"]] = row
    if set(result) != set(event_ids):
        raise ValueError("Clip ranges must match selected events.")
    return result


def selected_source_range(
    row: dict[str, object], event: SemanticEvent, duration: int
) -> SourceRange:
    start, end = row.get("startUs"), row.get("endUs")
    if type(start) is not int or type(end) is not int:
        raise ValueError("Selected source times must be integers.")
    source = SourceRange(start, end, duration)
    original = event.source_range
    if (
        original.duration_us != duration
        or not 0 <= original.start_us <= original.end_us <= duration
    ):
        raise ValueError("Invalid analysed range.")
    if not overlaps_observation(start, end, original.start_us, original.end_us, duration):
        raise ValueError("Selected range must intersect original event.")
    return source


def overlaps_observation(
    start: int, end: int, observed_start: int, observed_end: int, duration: int
) -> bool:
    if observed_start == observed_end:
        return start <= observed_start < end or start < observed_start == end == duration
    return start < observed_end and end > observed_start


def _segment_range(clip: CreationClip, frames: int, fps: int) -> SourceRange:
    framing, observed = clip.framing, clip.event.source_range
    length = (frames * 1_000_000 + fps - 1) // fps
    start = framing.start_us
    if clip.source_range is not None:
        left, right = max(start, observed.start_us), min(framing.end_us, observed.end_us)
        anchor = left if left == right else (left + right - 1) // 2
        start = min(max(start, anchor - length // 2), framing.end_us - length)
    return SourceRange(start, start + length, framing.duration_us)


# Neighbouring analysed events closer than this count as one continuous stretch of footage.
CONTIGUOUS_GAP_US = 250_000
# Longest single shot; a weighted opening hook may run a little longer.
MAX_SHOT_SECONDS = 4
MAX_OPENING_SECONDS = 6


def _event_frames(clip: CreationClip, fps: int) -> int:
    source = clip.framing
    return (source.end_us - source.start_us) * fps // 1_000_000


def _shots(
    ordered: list[CreationClip], eligible: list[CreationClip], shot_us: int
) -> list[list[CreationClip]]:
    """Each picked clip plus the analysed events directly after it, up to ``shot_us``.

    Played back to back these are continuous footage, while every segment stays inside its
    own event. ``eligible`` is sorted by source then start time.
    """
    position = {id(clip): index for index, clip in enumerate(eligible)}
    used = {id(clip) for clip in ordered}
    shots = []
    for clip in ordered:
        group = [clip]
        length = clip.framing.end_us - clip.framing.start_us
        cursor = position[id(clip)] + 1
        while length < shot_us and cursor < len(eligible):
            following, last = eligible[cursor], group[-1].framing
            start = following.framing.start_us
            if (
                id(following) in used
                or following.asset.sha256 != clip.asset.sha256
                or not last.end_us <= start <= last.end_us + CONTIGUOUS_GAP_US
            ):
                break
            group.append(following)
            used.add(id(following))
            length += following.framing.end_us - start
            cursor += 1
        shots.append(group)
    return shots


def _budgets(capacities: list[int], weights: list[Fraction], target: int) -> list[int]:
    """Share ``target`` frames by weight; a shot never exceeds its capacity and what it
    cannot take goes to the others."""
    budgets = [0] * len(capacities)
    active = [i for i, capacity in enumerate(capacities) if capacity > 0]
    left = target
    while left > 0 and active:
        total = sum(weights[i] for i in active)
        shares = {i: int(left * weights[i] / total) for i in active}
        if not any(shares.values()):
            shares = dict.fromkeys(active[:left], 1)
        for i, share in shares.items():
            add = min(share, capacities[i] - budgets[i])
            budgets[i] += add
            left -= add
        active = [i for i in active if budgets[i] < capacities[i]]
    return budgets


def _fill_showcase_duration(
    shots: list[list[CreationClip]],
    capacities: list[int],
    eligible: list[CreationClip],
    missing_frames: int,
    fps: int,
    cap: int,
) -> tuple[list[list[CreationClip]], list[int]]:
    """Fill remaining time with unused footage while keeping the opening and topic seeds."""
    used = {id(clip) for shot in shots for clip in shot}
    order = {id(clip): index for index, clip in enumerate(eligible)}
    available = sorted(
        (clip for clip in eligible if id(clip) not in used),
        key=lambda clip: min(cap, _event_frames(clip, fps)),
        reverse=True,
    )
    middle = list(zip(shots[1:], capacities[1:], strict=True))
    for clip in available:
        capacity = min(cap, _event_frames(clip, fps))
        middle.append(([clip], capacity))
        missing_frames -= capacity
        if missing_frames <= 0:
            break
    middle.sort(key=lambda item: order[id(item[0][0])])
    return [shots[0], *(shot for shot, _ in middle)], [capacities[0], *(n for _, n in middle)]


def _allocate_structure(
    ordered: list[CreationClip],
    eligible: list[CreationClip],
    roles: tuple[str, ...] | None,
    weights: tuple[Fraction, ...] | None,
    fps: int,
    target_frames: int,
    *,
    trim_applied: bool,
    fill_duration: bool,
) -> tuple[list[list[CreationClip]], tuple[str, ...] | None, list[int]]:
    if trim_applied or not ordered:
        # Trimming habits keep one-second segments, one event each.
        shots = [[clip] for clip in ordered]
    else:
        # Chains reach the longest allowed shot; budgets below decide how much plays.
        shots = _shots(ordered, eligible, MAX_SHOT_SECONDS * 1_000_000)
    # One second of output when trimming is common: see ordering.editHabits.
    cap = fps if trim_applied else MAX_SHOT_SECONDS * fps
    capacities = [
        min(
            sum(_event_frames(clip, fps) for clip in shot),
            MAX_OPENING_SECONDS * fps if index == 0 and weights and not trim_applied else cap,
        )
        for index, shot in enumerate(shots)
    ]
    missing_frames = target_frames - sum(capacities)
    if fill_duration and shots and missing_frames > 0:
        shots, capacities = _fill_showcase_duration(
            shots, capacities, eligible, missing_frames, fps, cap
        )
        middle_count = len(shots) - 1
        weights = (max(Fraction(1), Fraction(middle_count, 3)), *[Fraction(1)] * middle_count)
        if middle_count >= 2:
            roles = ("开场高光", *["玩法展示"] * (middle_count - 1), "收尾")
        elif middle_count == 1:
            roles = ("开场高光", "玩法展示")
    budgets = _budgets(capacities, list(weights or [Fraction(1)] * len(shots)), target_frames)
    return shots, roles, budgets


def _sized_clips(
    brief: CreativeBrief, clips: tuple[CreationClip, ...], fps: int
) -> list[CreationClip]:
    return [
        clip
        for clip in clips
        if not any(
            word.casefold()
            in " ".join(clip.event.observable_facts + clip.event.mechanic_tags).casefold()
            for word in brief.exclude
        )
        and clip.event.observable_facts
        and (clip.framing.end_us - clip.framing.start_us) * fps >= 1_000_000
    ]


def eligible_clips(
    brief: CreativeBrief, clips: tuple[CreationClip, ...], fps: int
) -> list[CreationClip]:
    """Shared exclusion, source deduplication and minimum-frame policy."""
    eligible = _sized_clips(brief, clips, fps)
    # A different analysis version is not another shot of the same source interval.
    unique: dict[tuple[str, int, int], CreationClip] = {}
    source_order = {
        sha: index for index, sha in enumerate(dict.fromkeys(clip.asset.sha256 for clip in clips))
    }
    for clip in eligible:
        key = (clip.asset.sha256, clip.framing.start_us, clip.framing.end_us)
        previous = unique.setdefault(key, clip)
        if (
            brief.content_type in ("guide", "commentary")
            and previous is not clip
            and visual_topic_count(clip, brief.mandatory_topics)
            > visual_topic_count(previous, brief.mandatory_topics)
        ):
            unique[key] = clip
    eligible = sorted(
        unique.values(),
        key=lambda clip: (
            source_order[clip.asset.sha256],
            clip.framing.start_us,
            clip.framing.end_us,
        ),
    )
    return _without_overlaps(eligible)


def scoring_candidates(
    brief: CreativeBrief, clips: tuple[CreationClip, ...], fps: int
) -> list[CreationClip]:
    """Scope local visual measurement to footage eligible for a recommendation."""
    if brief.content_type == "highlight":
        return _sized_clips(brief, clips, fps)
    return eligible_clips(brief, clips, fps)


MIN_REMNANT_US = 1_000_000


def _without_overlaps(clips: list[CreationClip]) -> list[CreationClip]:
    """Each source second plays at most once (J1 2026-11-11: overlapping basket picks repeated
    footage). Per recording, in source order, a clip starts where the earlier coverage ended; a
    clip that is covered, leaves under a second, or no longer meets its analysed event is dropped.
    The caller's order is kept."""
    kept: dict[int, CreationClip] = {}
    covered: dict[str, int] = {}
    order = sorted(
        range(len(clips)), key=lambda i: (clips[i].asset.sha256, clips[i].framing.start_us)
    )
    for index in order:
        clip = clips[index]
        frame, end = clip.framing, covered.get(clip.asset.sha256)
        if end is not None and frame.start_us < end:
            observed = clip.event.source_range
            if frame.end_us - end < MIN_REMNANT_US or not overlaps_observation(
                end, frame.end_us, observed.start_us, observed.end_us, frame.duration_us
            ):
                continue
            clip = CreationClip(
                clip.asset, clip.event, SourceRange(end, frame.end_us, frame.duration_us)
            )
        kept[index] = clip
        covered[clip.asset.sha256] = max(end or 0, clip.framing.end_us)
    return [kept[i] for i in sorted(kept)]


def _material_gaps(segment_count: int, allocated: bool) -> list[str]:
    if allocated:
        return (
            [] if segment_count else ["目标时长内没有可完整保留的片段，请预览其他方案或调整时长。"]
        )
    return ["不足三个不同源区间，不能形成完整的三段结构"] if segment_count < 3 else []


def _recommendations(
    brief: CreativeBrief,
    eligible: list[CreationClip],
    highlight_candidates: list[CreationClip],
    transcripts: Mapping[str, tuple[TranscriptSegment, ...]],
    fps: int,
    score: Score,
) -> tuple[
    list[PlanTemplate], dict[str, StructureAllocation], HighlightCut | None, dict[str, AdTrial]
]:
    if brief.content_type == "live_cut" and eligible:
        layout = live_cut(brief, eligible, transcripts, fps, score)
        layouts = {layout.identity: layout}
        return [(layout.identity, layout.description, [], None, None)], layouts, None, {}
    if brief.content_type == "ad" and eligible:
        trials = {trial.layout.identity: trial for trial in ad_trials(brief, eligible, fps, score)}
        if trials:
            layouts = {name: trial.layout for name, trial in trials.items()}
            return (
                [(name, layout.description, [], None, None) for name, layout in layouts.items()],
                layouts,
                None,
                trials,
            )
    highlight = (
        highlight_cut(brief, highlight_candidates, fps, score) if highlight_candidates else None
    )
    if highlight is not None:
        layout = highlight.allocation
        return (
            [(layout.identity, layout.description, [], None, None)],
            {layout.identity: layout},
            highlight,
            {},
        )
    mode = mode_structure(brief, eligible, score, target_frames=brief.target_duration * fps)
    recommended: list[PlanTemplate] = (
        []
        if mode is None
        else [(mode.identity, mode.description, list(mode.ordered), mode.roles, mode.weights)]
    )
    return recommended, {}, None, {}


def plan_creation(
    brief: CreativeBrief,
    clips: tuple[CreationClip, ...],
    fps: int,
    preferences: dict[str, int] | None = None,
    edit_kinds: dict[str, int] | None = None,
    creator_feedback: CreatorStructureChoice | None = None,
    *,
    transcripts: Mapping[str, tuple[TranscriptSegment, ...]] | None = None,
    visual_samples: Mapping[tuple[str, str], VisualSample] | None = None,
) -> dict[str, object]:
    """Template plans; ``preferences`` (finished videos per plan structure on this machine)
    only reorders the generic structures. An explicit creator choice can recommend any ready
    structure. Otherwise the content-mode template stays recommended first.

    ``edit_kinds`` (frozen at plan registration) may cap segment length when trimming is common;
    the decision is always written into ``ordering.editHabits`` when provided.
    """
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError("Output fps must be an integer in 1..120.")
    eligible = eligible_clips(brief, clips, fps)
    highlight_candidates = (
        scoring_candidates(brief, clips, fps) if brief.content_type == "highlight" else []
    )
    scores = score_materials(brief, highlight_candidates or eligible, visual_samples)
    visual_measured = any(score.get("visualSamples") for score in scores.values())
    mode_honesty = (
        MODE_HONESTY_SHORT + "。可用取帧补充亮度对比。" if visual_measured else MODE_HONESTY_SHORT
    )
    generic_scores = (
        score_materials(brief, eligible, visual_samples)
        if highlight_candidates and visual_samples
        else scores
    )

    def total(clip: CreationClip) -> float:
        value = scores[(clip.event.run_id, clip.event.event_id)]["total"]
        return float(value) if value is not None else 0.0

    # Across sources retain the explicit input run order; within each source use source time.
    picked = sample_clips(
        eligible,
        max(3, brief.target_duration // GENERIC_SHOT_SECONDS),
        lambda clip: float(
            generic_scores[(clip.event.run_id, clip.event.event_id)]["total"] or 0.0
        ),
    )
    generic: list[PlanTemplate] = [
        ("chronological", "按来源顺序展开", picked, None, None),
        ("hook-first", "最后一条先作开场，再回溯", picked[-1:] + picked[:-1], None, None),
        ("reverse", "倒序逐条回顾", list(reversed(picked)), None, None),
    ]
    habits = {
        key: value
        for key, value in (preferences or {}).items()
        if isinstance(key, str) and type(value) is int and value > 0
    }
    template_order = [structure[0] for structure in generic]
    # Stable: structures the user finished more often come first, ties keep template order.
    generic.sort(key=lambda structure: -habits.get(structure[0], 0))
    moved = {
        structure[0]
        for index, structure in enumerate(generic)
        if index < template_order.index(structure[0])
    }
    suggestion = trim_suggestion(edit_kinds) if edit_kinds is not None else None
    trim_applied = bool(suggestion and suggestion["applied"])
    target_frames = brief.target_duration * fps
    recommended, layouts, highlight, trials = _recommendations(
        brief, eligible, highlight_candidates, transcripts or {}, fps, total
    )
    plans: list[dict[str, object]] = []
    for identity, description, ordered, roles, weights in [*recommended, *generic]:
        plan_scores = generic_scores if identity in template_order else scores
        layout = layouts.get(identity)
        if layout is not None:
            shots, roles, budgets = layout.shots, layout.roles, layout.budgets
        else:
            shots, roles, budgets = _allocate_structure(
                ordered,
                eligible,
                roles,
                weights,
                fps,
                target_frames,
                trim_applied=trim_applied,
                fill_duration=identity == "showcase" and bool(brief.mandatory_topics),
            )
        segments: list[dict[str, object]] = []
        segment_shots: list[int] = []
        used_intervals: set[tuple[str, int, int]] = set()
        position = 0
        for index, (shot, budget) in enumerate(zip(shots, budgets, strict=True)):
            for clip in shot:
                # Earlier events of a shot play whole so the footage stays continuous.
                frames = min(budget, _event_frames(clip, fps))
                if frames <= 0:
                    break
                event = clip.event
                selected_range = _segment_range(clip, frames, fps)
                start_us, end_us = selected_range.start_us, selected_range.end_us
                interval_key = (clip.asset.sha256, start_us, end_us)
                if interval_key in used_intervals:
                    continue
                used_intervals.add(interval_key)
                segments.append(
                    {
                        "runId": event.run_id,
                        "eventId": event.event_id,
                        "mediaId": clip.asset.media_id,
                        "sourceSha256": clip.asset.sha256,
                        "sourcePath": str(clip.asset.source_path),
                        "startUs": start_us,
                        "endUs": end_us,
                        "sourceDurationUs": clip.asset.duration_us,
                        "outputStartFrame": position,
                        "outputFrames": frames,
                        "evidenceIds": list(event.evidence_ids),
                        "scriptDraft": "；".join(event.observable_facts),
                        "uncertainty": event.uncertainty,
                        **(
                            {
                                "rangeProvenance": {
                                    "schemaVersion": "user-framing-v1",
                                    "analysisStartUs": event.source_range.start_us,
                                    "analysisEndUs": event.source_range.end_us,
                                    "startUs": clip.framing.start_us,
                                    "endUs": clip.framing.end_us,
                                }
                            }
                            if clip.source_range is not None and identity != "highlight-evidence"
                            else {}
                        ),
                        "score": plan_scores[(event.run_id, event.event_id)],
                        **({"role": roles[index]} if roles is not None else {}),
                    }
                )
                segment_shots.append(index)
                position += frames
                budget -= frames
        if identity == "guide-steps":
            # One step per shot; skipped shots must not leave holes in the step numbers.
            numbers = {shot_no: n for n, shot_no in enumerate(dict.fromkeys(segment_shots), 1)}
            for segment, shot_no in zip(segments, segment_shots, strict=True):
                segment["role"] = f"第{numbers[shot_no]}步"
        step_seeds = (
            {(clip.event.run_id, clip.event.event_id) for clip in ordered}
            if identity == "guide-evidence"
            else None
        )
        topic_notes, topic_fields = _plan_topic_details(
            brief,
            identity,
            eligible,
            segments,
            step_seeds=step_seeds,
            highlight=highlight if identity == "highlight-evidence" else None,
            ad_trial=trials.get(identity),
        )
        gaps = _material_gaps(len(segments), layout is not None)
        plans.append(
            {
                "id": identity,
                "structure": description,
                "segments": segments,
                "contentSignature": plan_content_signature(segments),
                "gaps": gaps,
                "ready": not gaps,
                **topic_fields,
                "advisories": [
                    *topic_notes,
                    *(layout.notes if layout is not None else [TRIM_TIP] if trim_applied else []),
                    *advisories(brief, eligible, segments, fps),
                ],
                "scriptStatus": "saved-descriptions-draft-human-review-required",
                **(
                    {"localRenders": habits[identity], "rankedByHistory": identity in moved}
                    if identity in habits and roles is None
                    else {}
                ),
                **(
                    {
                        "mode": brief.content_type,
                        "modeLabel": MODE_LABELS[brief.content_type],
                        "honesty": mode_honesty,
                    }
                    if roles is not None
                    else {}
                ),
            }
        )
    applied_feedback = _prefer_structure(plans, creator_feedback)
    kept = unique_rule_plans(plans)
    reason = candidate_count_reason(kept, distinct_source_intervals(eligible))
    return {
        "schemaVersion": "creation-plan-v1",
        "planner": "offline-template-v1",
        "understandingVerified": False,
        **({"modeHonesty": mode_honesty} if recommended else {}),
        "scoring": scoring_legend(visual_measured),
        "ordering": {
            "basis": "creator-feedback"
            if applied_feedback
            else "local-render-history"
            if moved
            else "template",
            "renderedByPlan": habits,
            **(
                {"creatorFeedback": {**creator_feedback.to_json(), "applied": applied_feedback}}
                if creator_feedback is not None
                else {}
            ),
            **(
                {
                    "editHabits": {
                        "editKinds": normalize_edit_kinds(edit_kinds),
                        "trimSuggestion": suggestion,
                    }
                }
                if suggestion is not None
                else {}
            ),
        },
        "fps": fps,
        "plans": kept,
        **({"candidateCountReason": reason} if reason else {}),
    }
