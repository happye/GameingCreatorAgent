"""Offline positive AND matching over frozen candidate-local observations."""

from dataclasses import replace
from itertools import combinations

from gamingcreator.domain.actor_details import (
    ActorDetail,
    ActorMatch,
    AttributeConflict,
    AttributeConstraint,
    AttributeKind,
    AttributeStatus,
    CandidateDetail,
    ConstraintSupport,
    DetailAttribute,
    DetailMatch,
    MatchStatus,
    QueryConstraint,
    ShotDetail,
    constraint_hash,
    constraint_sort_key,
    values_are_exclusive,
)
from gamingcreator.domain.time import SourceRange


def _attribute_key(attribute: DetailAttribute) -> tuple[object, ...]:
    return (
        attribute.part_id,
        attribute.kind.value,
        attribute.value,
        attribute.status.value,
        attribute.source_range.start_us,
        attribute.source_range.end_us,
        attribute.evidence_ids,
    )


def _conflicts(
    attributes: tuple[DetailAttribute, ...], order: dict[str, int]
) -> tuple[AttributeConflict, ...]:
    conflicts = []
    observed = sorted(
        (attribute for attribute in attributes if attribute.status == AttributeStatus.OBSERVED),
        key=_attribute_key,
    )
    for left, right in combinations(observed, 2):
        start = max(left.source_range.start_us, right.source_range.start_us)
        end = min(left.source_range.end_us, right.source_range.end_us)
        if (
            left.part_id == right.part_id
            and left.kind == right.kind
            and start < end
            and values_are_exclusive(left.kind, left.value, right.value)
        ):
            conflicts.append(
                AttributeConflict(
                    left.part_id,
                    left.kind,
                    (min(left.value, right.value), max(left.value, right.value)),
                    SourceRange(start, end, left.source_range.duration_us),
                    tuple(
                        sorted(
                            set(left.evidence_ids) | set(right.evidence_ids), key=order.__getitem__
                        )
                    ),
                )
            )
    return tuple(conflicts)


def _conflicted(attribute: DetailAttribute, conflicts: tuple[AttributeConflict, ...]) -> bool:
    return any(
        item.part_id == attribute.part_id
        and item.kind == attribute.kind
        and attribute.value in item.values
        and max(item.source_range.start_us, attribute.source_range.start_us)
        < min(item.source_range.end_us, attribute.source_range.end_us)
        for item in conflicts
    )


def _support(condition: AttributeConstraint, attribute: DetailAttribute) -> ConstraintSupport:
    return ConstraintSupport(
        condition, attribute.part_id, attribute.evidence_ids, attribute.source_range
    )


def _opposition_scope(
    condition: AttributeConstraint,
    group: tuple[AttributeConstraint, ...],
    attributes: list[DetailAttribute],
    conflicts: tuple[AttributeConflict, ...],
) -> bool:
    if condition.kind == AttributeKind.HAIR_COLOR:
        return True
    if condition.kind != AttributeKind.CLOTHING_COLOR:
        return False
    # A scarf's color cannot exclude an unseen coat. A positive shape observation
    # must anchor the requested garment on the same actual part and frame.
    shapes = [item for item in group if item.kind == AttributeKind.CLOTHING_SHAPE]
    return bool(shapes) and all(
        any(
            item.kind == shape.kind
            and item.value == shape.value
            and item.status == AttributeStatus.OBSERVED
            and not _conflicted(item, conflicts)
            for item in attributes
        )
        for shape in shapes
    )


def _part_conditions(
    conditions: tuple[AttributeConstraint, ...],
    attributes: tuple[DetailAttribute, ...],
    part_id: str | None,
    frame_id: str,
    conflicts: tuple[AttributeConflict, ...],
) -> tuple[
    tuple[ConstraintSupport, ...],
    tuple[AttributeConstraint, ...],
    tuple[ConstraintSupport, ...],
    tuple[ConstraintSupport, ...],
]:
    satisfied: list[ConstraintSupport] = []
    missing: list[AttributeConstraint] = []
    uncertain: list[ConstraintSupport] = []
    opposed: list[ConstraintSupport] = []
    at_part = [
        item for item in attributes if item.part_id == part_id and frame_id in item.evidence_ids
    ]
    for condition in conditions:
        candidates = sorted(
            (item for item in at_part if item.kind == condition.kind),
            key=_attribute_key,
        )
        matching = [item for item in candidates if item.value == condition.value]
        observed = [
            item
            for item in matching
            if item.status == AttributeStatus.OBSERVED and not _conflicted(item, conflicts)
        ]
        if observed:
            satisfied.append(_support(condition, observed[0]))
        elif matching:
            uncertain.append(_support(condition, matching[0]))
        else:
            alternatives = [
                item
                for item in candidates
                if item.status == AttributeStatus.OBSERVED
                and not _conflicted(item, conflicts)
                and values_are_exclusive(item.kind, item.value, condition.value)
            ]
            if (
                alternatives
                and not any(item.status == AttributeStatus.UNCERTAIN for item in candidates)
                and _opposition_scope(condition, conditions, at_part, conflicts)
            ):
                opposed.append(_support(condition, alternatives[0]))
            else:
                missing.append(condition)
    return tuple(satisfied), tuple(missing), tuple(uncertain), tuple(opposed)


def _grouped_conditions(
    conditions: tuple[AttributeConstraint, ...],
    attributes: tuple[DetailAttribute, ...],
    frame_id: str,
    conflicts: tuple[AttributeConflict, ...],
) -> tuple[
    tuple[ConstraintSupport, ...],
    tuple[AttributeConstraint, ...],
    tuple[ConstraintSupport, ...],
    tuple[ConstraintSupport, ...],
]:
    satisfied: list[ConstraintSupport] = []
    missing: list[AttributeConstraint] = []
    uncertain: list[ConstraintSupport] = []
    opposed: list[ConstraintSupport] = []
    for group in sorted({item.part_group for item in conditions}):
        grouped = tuple(item for item in conditions if item.part_group == group)
        kinds = {item.kind for item in grouped}
        parts = sorted({item.part_id for item in attributes if item.kind in kinds})
        part_choices: list[str | None] = [*parts] if parts else [None]
        choices = [
            _part_conditions(grouped, attributes, part, frame_id, conflicts)
            for part in part_choices
        ]
        # Parts are already sorted: ties consistently select the same local part.
        best = min(choices, key=lambda value: (-len(value[0]), -len(value[2]), len(value[3])))
        satisfied.extend(best[0])
        missing.extend(best[1])
        uncertain.extend(best[2])
        opposed.extend(best[3])
    return tuple(satisfied), tuple(missing), tuple(uncertain), tuple(opposed)


def _at_frame(
    shot: ShotDetail,
    actor: ActorDetail,
    query: QueryConstraint,
    frame_id: str,
    actor_conflicts: tuple[AttributeConflict, ...],
    environment_conflicts: tuple[AttributeConflict, ...],
    order: dict[str, int],
) -> ActorMatch:
    actor_conditions = _grouped_conditions(
        query.actor_all, actor.attributes, frame_id, actor_conflicts
    )
    environment = _grouped_conditions(
        query.environment_all, shot.environment, frame_id, environment_conflicts
    )
    satisfied = tuple(
        sorted(
            (*actor_conditions[0], *environment[0]),
            key=lambda item: constraint_sort_key(item.condition),
        )
    )
    shared: set[str] = set(satisfied[0].evidence_ids) if satisfied else set()
    for item in satisfied:
        shared.intersection_update(item.evidence_ids)
    interval = None
    ranges = [item.source_range for item in satisfied if item.source_range is not None]
    if ranges:
        start, end = max(item.start_us for item in ranges), min(item.end_us for item in ranges)
        if start < end:
            interval = SourceRange(start, end, shot.source_range.duration_us)
    return ActorMatch(
        shot.shot_id,
        actor.actor_id,
        satisfied,
        tuple(sorted((*actor_conditions[1], *environment[1]), key=constraint_sort_key)),
        tuple(
            sorted(
                (*actor_conditions[2], *environment[2]),
                key=lambda item: constraint_sort_key(item.condition),
            )
        ),
        tuple(
            sorted(
                (*actor_conditions[3], *environment[3]),
                key=lambda item: constraint_sort_key(item.condition),
            )
        ),
        tuple(sorted(shared, key=order.__getitem__)),
        interval,
        (*actor_conflicts, *environment_conflicts),
    )


def _full(match: ActorMatch, count: int) -> bool:
    return (
        len(match.satisfied) == count
        and bool(match.shared_evidence_ids)
        and match.source_range is not None
        and not match.conflicts
    )


def _frame_opposition(
    actor: ActorDetail,
    query: QueryConstraint,
    frame: str,
    conflicts: tuple[AttributeConflict, ...],
) -> tuple[ConstraintSupport, ...]:
    for condition in query.actor_all:
        if condition.kind != AttributeKind.HAIR_COLOR:
            continue
        hair_parts = {item.part_id for item in actor.attributes if item.kind == condition.kind}
        values = sorted(
            (
                item
                for item in actor.attributes
                if item.kind == condition.kind and frame in item.evidence_ids
            ),
            key=_attribute_key,
        )
        if (
            values
            and {item.part_id for item in values} == hair_parts
            and all(
                item.status == AttributeStatus.OBSERVED
                and not _conflicted(item, conflicts)
                and values_are_exclusive(item.kind, item.value, condition.value)
                for item in values
            )
        ):
            return tuple(_support(condition, item) for item in values)
    for group in sorted({item.part_group for item in query.actor_all}):
        conditions = tuple(item for item in query.actor_all if item.part_group == group)
        shapes = tuple(item for item in conditions if item.kind == AttributeKind.CLOTHING_SHAPE)
        if not shapes:
            continue
        kinds = {item.kind for item in conditions}
        parts = sorted({item.part_id for item in actor.attributes if item.kind in kinds})
        proofs: list[ConstraintSupport] = []
        anchored = False
        for part in parts:
            values = [
                item
                for item in actor.attributes
                if item.part_id == part and frame in item.evidence_ids
            ]
            observed_shapes = [
                item
                for item in values
                if item.kind == AttributeKind.CLOTHING_SHAPE
                and item.status == AttributeStatus.OBSERVED
                and not _conflicted(item, conflicts)
            ]
            if any(
                any(
                    values_are_exclusive(shape.kind, shape.value, item.value)
                    for item in observed_shapes
                )
                for shape in shapes
            ) and not any(
                item.kind == AttributeKind.CLOTHING_SHAPE
                and item.status == AttributeStatus.UNCERTAIN
                for item in values
            ):
                continue
            result = _part_conditions(conditions, actor.attributes, part, frame, conflicts)
            if not result[3]:
                break
            anchored = True
            proofs.extend(result[3])
        else:
            if anchored:
                return tuple(proofs)
    return ()


def match_actor_details(detail: CandidateDetail | None, constraint: QueryConstraint) -> DetailMatch:
    """Match a typed positive query without combining actors, parts, shots or clocks."""
    if type(constraint) is not QueryConstraint or (
        detail is not None and type(detail) is not CandidateDetail
    ):
        raise ValueError("Matching requires validated typed details and query constraints.")
    identity = constraint_hash(constraint)
    if detail is None:
        return DetailMatch(MatchStatus.UNVERIFIED, identity, (), ("detail_missing",))
    order = {item.evidence_id: index for index, item in enumerate(detail.evidence)}
    count = len(constraint.actor_all) + len(constraint.environment_all)
    matches = []
    ruled_out = []
    for shot in detail.shots:
        environment_conflicts = _conflicts(shot.environment, order)
        for actor in sorted(shot.actors, key=lambda item: item.actor_id):
            actor_conflicts = _conflicts(actor.attributes, order)
            choices = [
                _at_frame(
                    shot, actor, constraint, frame, actor_conflicts, environment_conflicts, order
                )
                for frame in shot.evidence_ids
            ]
            best = min(
                choices,
                key=lambda item: (
                    not _full(item, count),
                    -len(item.satisfied),
                    -len(item.uncertain),
                    len(item.opposed),
                ),
            )
            opposition = tuple(
                _frame_opposition(actor, constraint, frame, actor_conflicts)
                for frame in shot.evidence_ids
            )
            counter_evidence = tuple(dict.fromkeys(item for proof in opposition for item in proof))
            best = replace(best, counter_evidence=counter_evidence)
            matches.append(best)
            ruled_out.append(all(opposition))
    result = tuple(
        sorted(
            matches,
            key=lambda item: (
                not _full(item, count),
                -len(item.satisfied),
                -len(item.uncertain),
                item.shot_id,
                item.actor_id,
            ),
        )
    )
    notes = detail.notes
    if any(_full(item, count) for item in result):
        status = MatchStatus.FULL
    elif (
        ruled_out
        and all(ruled_out)
        and not detail.unassigned_evidence_ids
        and not notes
        and all(shot.actors for shot in detail.shots)
    ):
        status = MatchStatus.NO_MATCH
    elif any(item.satisfied for item in result):
        status = MatchStatus.PARTIAL
    else:
        status = MatchStatus.UNVERIFIED
    if detail.unassigned_evidence_ids:
        notes += ("unassigned_evidence",)
    if any(item.conflicts for item in result):
        notes += ("observed_attribute_conflict",)
    return DetailMatch(status, identity, result, notes)
