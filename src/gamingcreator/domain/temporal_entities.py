"""Immutable, registered-frame entity and continuity evidence; no visual inference or I/O."""

import re
from dataclasses import dataclass
from enum import StrEnum

from gamingcreator.domain.actor_details import (
    MAX_ACTOR_ATTRIBUTES,
    MAX_DETAIL_FRAMES,
    MAX_SHOT_ACTORS,
    AttributeKind,
    AttributeStatus,
    DetailAttribute,
    DetailEvidence,
    source_range_for_evidence,
)

TEMPORAL_SCENE_VERSION = "temporal-scene-v1"
MAX_SCENE_ENTITIES = 72
MAX_SCENE_OWNERS = 72
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class TransitionState(StrEnum):
    CONTINUOUS = "continuous"
    CUT = "cut"
    UNKNOWN = "unknown"


class TransitionBasis(StrEnum):
    VISUAL_CONTINUITY = "visual_continuity"
    SCENE_CHANGE = "scene_change"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EntityKind(StrEnum):
    ACTOR = "actor"
    OBJECT = "object"
    UNKNOWN = "unknown"


class ClassificationBasis(StrEnum):
    CHARACTER_STRUCTURE = "character_structure"
    INDEPENDENT_AGENCY = "independent_agency"
    CARRIED_OBJECT = "carried_object"
    RIGID_OBJECT = "rigid_object"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Visibility(StrEnum):
    VISIBLE = "visible"
    PARTIALLY_OCCLUDED = "partially_occluded"
    OCCLUDED = "occluded"
    UNKNOWN = "unknown"


class EntityPartGroup(StrEnum):
    HAIR = "hair"
    CLOTHING = "clothing"
    HELD_ITEM = "held_item"
    ACTION = "action"
    EFFECT = "effect"


PART_KINDS = {
    EntityPartGroup.HAIR: frozenset({AttributeKind.HAIR_COLOR}),
    EntityPartGroup.CLOTHING: frozenset(
        {AttributeKind.CLOTHING_COLOR, AttributeKind.CLOTHING_SHAPE}
    ),
    EntityPartGroup.HELD_ITEM: frozenset({AttributeKind.HELD_SHAPE, AttributeKind.HELD_CLASS}),
    EntityPartGroup.ACTION: frozenset({AttributeKind.ACTION}),
    EntityPartGroup.EFFECT: frozenset({AttributeKind.EFFECT}),
}
_CLASSIFICATION_BASES = {
    EntityKind.ACTOR: {
        ClassificationBasis.CHARACTER_STRUCTURE,
        ClassificationBasis.INDEPENDENT_AGENCY,
    },
    EntityKind.OBJECT: {ClassificationBasis.CARRIED_OBJECT, ClassificationBasis.RIGID_OBJECT},
    EntityKind.UNKNOWN: {ClassificationBasis.INSUFFICIENT_EVIDENCE},
}
_VISIBLE = {Visibility.VISIBLE, Visibility.PARTIALLY_OCCLUDED}


def _identity(value: object) -> None:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid local temporal entity identity.")


def _text(value: object) -> None:
    if type(value) is not str or not value.strip() or len(value) > 500:
        raise ValueError("Temporal evidence requires bounded nonempty descriptions.")


def _items(value: object, item_type: type[object], maximum: int, *, nonempty: bool = False) -> None:
    if (
        type(value) is not tuple
        or len(value) > maximum
        or (nonempty and not value)
        or any(type(item) is not item_type for item in value)
    ):
        raise ValueError("Invalid bounded temporal collection.")


def _references(value: tuple[str, ...], *, nonempty: bool = True) -> None:
    _items(value, str, MAX_DETAIL_FRAMES, nonempty=nonempty)
    if len(set(value)) != len(value):
        raise ValueError("Temporal references must be unique.")


@dataclass(frozen=True, slots=True)
class FrameTransition:
    before_id: str
    after_id: str
    state: TransitionState
    basis: TransitionBasis
    reason: str

    def __post_init__(self) -> None:
        _references((self.before_id, self.after_id))
        _text(self.reason)
        if type(self.state) is not TransitionState or type(self.basis) is not TransitionBasis:
            raise ValueError("Invalid transition state or basis.")
        expected = {
            TransitionState.CONTINUOUS: TransitionBasis.VISUAL_CONTINUITY,
            TransitionState.CUT: TransitionBasis.SCENE_CHANGE,
            TransitionState.UNKNOWN: TransitionBasis.INSUFFICIENT_EVIDENCE,
        }
        if self.basis != expected[self.state]:
            raise ValueError("Transition basis does not justify its state.")


@dataclass(frozen=True, slots=True)
class EntityClassification:
    kind: EntityKind
    status: AttributeStatus
    basis: ClassificationBasis
    evidence_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not EntityKind
            or type(self.status) is not AttributeStatus
            or type(self.basis) is not ClassificationBasis
            or self.basis not in _CLASSIFICATION_BASES[self.kind]
        ):
            raise ValueError("Classification requires the correct kind-specific basis.")
        if self.kind == EntityKind.UNKNOWN and self.status != AttributeStatus.UNCERTAIN:
            raise ValueError("An unknown entity cannot have an observed classification.")
        _references(self.evidence_ids, nonempty=self.kind != EntityKind.UNKNOWN)
        _text(self.reason)


@dataclass(frozen=True, slots=True)
class EntityObservation:
    evidence_id: str
    visibility: Visibility
    location: str

    def __post_init__(self) -> None:
        _references((self.evidence_id,))
        if type(self.visibility) is not Visibility:
            raise ValueError("Invalid entity visibility.")
        _text(self.location)


@dataclass(frozen=True, slots=True)
class EntityPart:
    part_id: str
    part_group: EntityPartGroup
    attributes: tuple[DetailAttribute, ...]

    def __post_init__(self) -> None:
        _identity(self.part_id)
        if type(self.part_group) is not EntityPartGroup:
            raise ValueError("Invalid entity part group.")
        _items(self.attributes, DetailAttribute, MAX_ACTOR_ATTRIBUTES, nonempty=True)
        if len(set(self.attributes)) != len(self.attributes) or any(
            item.part_id != self.part_id or item.kind not in PART_KINDS[self.part_group]
            for item in self.attributes
        ):
            raise ValueError("Part attributes must share their part identity and kind group.")


@dataclass(frozen=True, slots=True)
class TemporalEntity:
    entity_id: str
    description: str
    classification: EntityClassification
    observations: tuple[EntityObservation, ...]
    parts: tuple[EntityPart, ...]

    def __post_init__(self) -> None:
        _identity(self.entity_id)
        _text(self.description)
        if type(self.classification) is not EntityClassification:
            raise ValueError("An entity needs a typed classification.")
        _items(self.observations, EntityObservation, MAX_DETAIL_FRAMES, nonempty=True)
        _items(self.parts, EntityPart, MAX_ACTOR_ATTRIBUTES)
        if (
            len({part.part_id for part in self.parts}) != len(self.parts)
            or sum(len(part.attributes) for part in self.parts) > MAX_ACTOR_ATTRIBUTES
        ):
            raise ValueError("Entity parts require unique identities and bounded attributes.")
        allowed = {
            EntityKind.ACTOR: {
                EntityPartGroup.HAIR,
                EntityPartGroup.CLOTHING,
                EntityPartGroup.ACTION,
                EntityPartGroup.EFFECT,
            },
            EntityKind.OBJECT: {EntityPartGroup.HELD_ITEM},
            EntityKind.UNKNOWN: set(),
        }
        if any(part.part_group not in allowed[self.classification.kind] for part in self.parts):
            raise ValueError("Actors, objects and unknown entities have separate part scopes.")


@dataclass(frozen=True, slots=True)
class OwnerRelation:
    object_id: str
    actor_id: str
    status: AttributeStatus
    evidence_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        _identity(self.object_id)
        _identity(self.actor_id)
        if self.object_id == self.actor_id or type(self.status) is not AttributeStatus:
            raise ValueError("Ownership requires distinct typed entities.")
        _references(self.evidence_ids)
        _text(self.reason)


@dataclass(frozen=True, slots=True)
class TemporalScene:
    evidence: tuple[DetailEvidence, ...]
    transitions: tuple[FrameTransition, ...]
    entities: tuple[TemporalEntity, ...]
    owners: tuple[OwnerRelation, ...]
    environment: tuple[DetailAttribute, ...]
    notes: tuple[str, ...]
    schema_version: str = TEMPORAL_SCENE_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not str or self.schema_version != TEMPORAL_SCENE_VERSION:
            raise ValueError("Unsupported temporal scene version.")
        source_range_for_evidence(self.evidence)
        namespace = self.evidence[0].evidence_id.rsplit(":image:", 1)[0]
        if any(item.evidence_id.rsplit(":image:", 1)[0] != namespace for item in self.evidence):
            raise ValueError("Temporal evidence must belong to one registered run/media.")
        _items(self.transitions, FrameTransition, MAX_DETAIL_FRAMES - 1)
        if len(self.transitions) != len(self.evidence) - 1:
            raise ValueError("Every adjacent frame pair requires exactly one transition.")
        segment = 0
        segments = {self.evidence[0].evidence_id: 0}
        for before, after, transition in zip(
            self.evidence, self.evidence[1:], self.transitions, strict=False
        ):
            if (transition.before_id, transition.after_id) != (
                before.evidence_id,
                after.evidence_id,
            ):
                raise ValueError("Transitions must follow all adjacent registered frames in order.")
            if (
                transition.state == TransitionState.CUT
                and before.image_sha256 == after.image_sha256
            ):
                raise ValueError("Identical images cannot establish a scene cut.")
            if transition.state != TransitionState.CONTINUOUS:
                segment += 1
            segments[after.evidence_id] = segment
        _items(self.entities, TemporalEntity, MAX_SCENE_ENTITIES)
        _items(self.owners, OwnerRelation, MAX_SCENE_OWNERS)
        _items(self.environment, DetailAttribute, MAX_ACTOR_ATTRIBUTES)
        _items(self.notes, str, MAX_ACTOR_ATTRIBUTES)
        for note in self.notes:
            _text(note)
        if len({entity.entity_id for entity in self.entities}) != len(self.entities):
            raise ValueError("Temporal entity identities must be unique.")
        if len(set(self.owners)) != len(self.owners) or len(set(self.environment)) != len(
            self.environment
        ):
            raise ValueError("Repeated relations or environment attributes are invalid.")
        registered = {item.evidence_id: item for item in self.evidence}
        order = {item.evidence_id: index for index, item in enumerate(self.evidence)}
        entities = {item.entity_id: item for item in self.entities}
        visible: dict[str, set[str]] = {}
        actor_counts: dict[int, int] = {}
        for entity in self.entities:
            refs = tuple(item.evidence_id for item in entity.observations)
            self._support(refs, registered, segments)
            positions = [order[ref] for ref in refs]
            if positions != list(range(positions[0], positions[-1] + 1)):
                raise ValueError("Entity observations cannot silently skip intervening frames.")
            visible[entity.entity_id] = {
                item.evidence_id for item in entity.observations if item.visibility in _VISIBLE
            }
            classification = entity.classification
            if classification.evidence_ids:
                self._support(classification.evidence_ids, registered, segments)
                if not set(classification.evidence_ids).issubset(visible[entity.entity_id]):
                    raise ValueError(
                        "Classification cannot borrow occluded or unobserved evidence."
                    )
            if classification.basis == ClassificationBasis.INDEPENDENT_AGENCY:
                self._different_images(classification.evidence_ids, registered)
            if classification.kind == EntityKind.ACTOR:
                group = segments[refs[0]]
                actor_counts[group] = actor_counts.get(group, 0) + 1
                if actor_counts[group] > MAX_SHOT_ACTORS:
                    raise ValueError("Too many actors in one continuous segment.")
            for part in entity.parts:
                for attribute in part.attributes:
                    self._attribute(attribute, registered, segments)
                    if not set(attribute.evidence_ids).issubset(visible[entity.entity_id]):
                        raise ValueError(
                            "Entity attributes require visible supporting observations."
                        )
        for attribute in self.environment:
            if attribute.kind != AttributeKind.ENVIRONMENT:
                raise ValueError("Scene environment cannot contain entity attributes.")
            self._attribute(attribute, registered, segments)
        for relation in self.owners:
            if relation.object_id not in entities or relation.actor_id not in entities:
                raise ValueError("Ownership references unknown entities.")
            if (
                entities[relation.object_id].classification.kind,
                entities[relation.actor_id].classification.kind,
            ) != (EntityKind.OBJECT, EntityKind.ACTOR):
                raise ValueError("Ownership must connect an object to an actor.")
            self._support(relation.evidence_ids, registered, segments)
            if not set(relation.evidence_ids).issubset(
                visible[relation.object_id] & visible[relation.actor_id]
            ):
                raise ValueError("Both owner and object must be visible in ownership evidence.")

    @staticmethod
    def _support(
        refs: tuple[str, ...], registered: dict[str, DetailEvidence], segments: dict[str, int]
    ) -> None:
        _references(refs)
        if any(ref not in registered for ref in refs):
            raise ValueError("Temporal evidence references an unregistered frame.")
        source_range_for_evidence(tuple(registered[ref] for ref in refs))
        if len({segments[ref] for ref in refs}) != 1:
            raise ValueError("An entity or observation cannot cross a cut or unknown boundary.")

    @staticmethod
    def _different_images(refs: tuple[str, ...], registered: dict[str, DetailEvidence]) -> None:
        if len(refs) < 2 or len({registered[ref].image_sha256 for ref in refs}) < 2:
            raise ValueError(
                "Agency and action require different images at different source times."
            )

    @classmethod
    def _attribute(
        cls,
        attribute: DetailAttribute,
        registered: dict[str, DetailEvidence],
        segments: dict[str, int],
    ) -> None:
        cls._support(attribute.evidence_ids, registered, segments)
        if attribute.source_range != source_range_for_evidence(
            tuple(registered[ref] for ref in attribute.evidence_ids)
        ):
            raise ValueError(
                "Temporal attributes must retain their actual registered source clocks."
            )
        if attribute.kind == AttributeKind.ACTION:
            cls._different_images(attribute.evidence_ids, registered)
