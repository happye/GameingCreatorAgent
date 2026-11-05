"""Pure template planner over explicitly loaded, verified saved timelines."""

from dataclasses import dataclass
from fractions import Fraction

from gamingcreator.application.creation_feedback import (
    TRIM_TIP,
    normalize_edit_kinds,
    trim_suggestion,
)
from gamingcreator.application.creation_modes import (
    MODE_HONESTY_SHORT,
    MODE_LABELS,
    mode_structure,
    sample_clips,
)
from gamingcreator.application.material_scoring import advisories, score_materials, scoring_legend
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.media import MediaAsset
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.time import SourceRange

# Generic structures keep shots at two seconds or longer instead of slicing every event.
GENERIC_SHOT_SECONDS = 2


@dataclass(frozen=True, slots=True)
class CreationClip:
    asset: MediaAsset
    event: SemanticEvent
    source_range: SourceRange | None = None

    @property
    def framing(self) -> SourceRange:
        return self.source_range or self.event.source_range


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


def plan_creation(
    brief: CreativeBrief,
    clips: tuple[CreationClip, ...],
    fps: int,
    preferences: dict[str, int] | None = None,
    edit_kinds: dict[str, int] | None = None,
) -> dict[str, object]:
    """Template plans; ``preferences`` (finished videos per plan structure on this machine)
    only reorders the generic structures. The content-mode template stays recommended first.

    ``edit_kinds`` (frozen at plan registration) may cap segment length when trimming is common;
    the decision is always written into ``ordering.editHabits`` when provided.
    """
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError("Output fps must be an integer in 1..120.")
    eligible = [
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
    # A different analysis version is not another shot of the same source interval.
    unique: dict[tuple[str, int, int], CreationClip] = {}
    source_order = {
        sha: index for index, sha in enumerate(dict.fromkeys(clip.asset.sha256 for clip in clips))
    }
    for clip in eligible:
        key = (clip.asset.sha256, clip.framing.start_us, clip.framing.end_us)
        unique.setdefault(key, clip)
    eligible = sorted(
        unique.values(),
        key=lambda clip: (
            source_order[clip.asset.sha256],
            clip.framing.start_us,
            clip.framing.end_us,
        ),
    )
    scores = score_materials(brief, eligible)

    def total(clip: CreationClip) -> float:
        value = scores[(clip.event.run_id, clip.event.event_id)]["total"]
        return float(value) if value is not None else 0.0

    # Across sources retain the explicit input run order; within each source use source time.
    picked = sample_clips(eligible, max(3, brief.target_duration // GENERIC_SHOT_SECONDS), total)
    generic: list[
        tuple[str, str, list[CreationClip], tuple[str, ...] | None, tuple[Fraction, ...] | None]
    ] = [
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
    mode = mode_structure(brief, eligible, total)
    structures = generic
    if mode is not None:
        # The content mode's own template is recommended first; generic orders stay available.
        structures = [
            (mode.identity, mode.description, list(mode.ordered), mode.roles, mode.weights),
            *generic,
        ]
    plans: list[dict[str, object]] = []
    target_frames = brief.target_duration * fps
    for identity, description, ordered, roles, weights in structures:
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
        budgets = _budgets(capacities, list(weights or [Fraction(1)] * len(shots)), target_frames)
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
                            if clip.source_range is not None
                            else {}
                        ),
                        "score": scores[(event.run_id, event.event_id)],
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
        text = " ".join(str(segment["scriptDraft"]) for segment in segments).casefold()
        gaps = [
            f"主题缺少已保存文字证据：{topic}"
            for topic in brief.mandatory_topics
            if topic.casefold() not in text
        ]
        if len(segments) < 3:
            gaps.append("不足三个不同源区间，不能形成完整的三段结构")
        plans.append(
            {
                "id": identity,
                "structure": description,
                "segments": segments,
                "gaps": gaps,
                "ready": not gaps,
                "advisories": (
                    [TRIM_TIP, *advisories(brief, eligible, segments, fps)]
                    if trim_applied
                    else advisories(brief, eligible, segments, fps)
                ),
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
                        "honesty": MODE_HONESTY_SHORT,
                    }
                    if roles is not None
                    else {}
                ),
            }
        )
    return {
        "schemaVersion": "creation-plan-v1",
        "planner": "offline-template-v1",
        "understandingVerified": False,
        **({"modeHonesty": MODE_HONESTY_SHORT} if mode is not None else {}),
        "scoring": scoring_legend(),
        "ordering": {
            "basis": "local-render-history" if moved else "template",
            "renderedByPlan": habits,
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
        "plans": plans,
    }
