"""Pure projection of qualified entities and supported ownership into actor matching shots."""

from dataclasses import dataclass, replace

from gamingcreator.domain.actor_details import (
    ActorDetail,
    AttributeKind,
    AttributeStatus,
    DetailAttribute,
    ShotDetail,
    source_range_for_evidence,
)
from gamingcreator.domain.temporal_entities import EntityKind, TemporalScene, TransitionState


@dataclass(frozen=True, slots=True)
class TemporalProjection:
    shots: tuple[ShotDetail, ...]
    has_unresolved_entities: bool
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.shots) is not tuple
            or len(self.shots) > 9
            or any(type(item) is not ShotDetail for item in self.shots)
            or type(self.has_unresolved_entities) is not bool
            or type(self.notes) is not tuple
            or len(self.notes) > 16
            or any(
                type(item) is not str or not item.strip() or len(item) > 500 for item in self.notes
            )
        ):
            raise ValueError("Invalid bounded temporal projection.")


def project_temporal_scene(scene: TemporalScene) -> TemporalProjection:
    if type(scene) is not TemporalScene:
        raise ValueError("A validated temporal scene is required.")
    registered = {item.evidence_id: item for item in scene.evidence}
    order = {item.evidence_id: index for index, item in enumerate(scene.evidence)}
    groups: list[list[str]] = [[scene.evidence[0].evidence_id]]
    for transition in scene.transitions:
        if transition.state == TransitionState.CONTINUOUS:
            groups[-1].append(transition.after_id)
        else:
            groups.append([transition.after_id])
    entities = {item.entity_id: item for item in scene.entities}
    part_ids = {
        (entity.entity_id, part.part_id): f"e{entity_index + 1}p{part_index + 1}"
        for entity_index, entity in enumerate(scene.entities)
        for part_index, part in enumerate(entity.parts)
    }
    shots = []
    for group_index, refs_list in enumerate(groups):
        refs = tuple(refs_list)
        shot_id = f"s{group_index + 1}"
        actors = []
        for entity in scene.entities:
            if (
                entity.classification.kind != EntityKind.ACTOR
                or entity.classification.status != AttributeStatus.OBSERVED
                or entity.observations[0].evidence_id not in refs
            ):
                continue
            attributes = [
                replace(item, part_id=part_ids[entity.entity_id, part.part_id])
                for part in entity.parts
                for item in part.attributes
            ]
            owned: dict[tuple[str, AttributeKind, str, AttributeStatus], set[str]] = {}
            for relation in scene.owners:
                if relation.actor_id != entity.entity_id:
                    continue
                item_entity = entities[relation.object_id]
                for part in item_entity.parts:
                    for attribute in part.attributes:
                        support = set(attribute.evidence_ids) & set(relation.evidence_ids)
                        if not support:
                            continue
                        status = (
                            AttributeStatus.OBSERVED
                            if relation.status == AttributeStatus.OBSERVED
                            and item_entity.classification.status == AttributeStatus.OBSERVED
                            and attribute.status == AttributeStatus.OBSERVED
                            else AttributeStatus.UNCERTAIN
                        )
                        key = (
                            part_ids[item_entity.entity_id, part.part_id],
                            attribute.kind,
                            attribute.value,
                            status,
                        )
                        owned.setdefault(key, set()).update(support)
            for (part_id, kind, value, status), support in owned.items():
                support_refs = tuple(sorted(support, key=order.__getitem__))
                attributes.append(
                    DetailAttribute(
                        part_id,
                        kind,
                        value,
                        status,
                        support_refs,
                        source_range_for_evidence(tuple(registered[ref] for ref in support_refs)),
                    )
                )
            actors.append(
                ActorDetail(shot_id, entity.entity_id, entity.description, tuple(attributes))
            )
        environment = tuple(item for item in scene.environment if item.evidence_ids[0] in refs)
        shots.append(
            ShotDetail(
                shot_id,
                source_range_for_evidence(tuple(registered[ref] for ref in refs)),
                refs,
                environment,
                tuple(actors),
            )
        )
    unresolved = (
        any(transition.state == TransitionState.UNKNOWN for transition in scene.transitions)
        or any(
            entity.classification.kind == EntityKind.UNKNOWN
            or entity.classification.status == AttributeStatus.UNCERTAIN
            for entity in scene.entities
        )
        or any(relation.status == AttributeStatus.UNCERTAIN for relation in scene.owners)
    )
    return TemporalProjection(tuple(shots), unresolved, scene.notes)
