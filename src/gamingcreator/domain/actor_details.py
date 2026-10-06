"""Immutable candidate-local visual detail contracts; no inference or I/O."""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from gamingcreator.domain.time import SourceInstant, SourceRange

if TYPE_CHECKING:
    from gamingcreator.domain.temporal_entities import TemporalScene

DETAIL_SCHEMA_VERSION = "actor-details-v1"
DETAIL_TEMPORAL_SCHEMA_VERSION = "actor-details-v2"
DETAIL_VOCABULARY_VERSION = "actor-detail-vocabulary-v1"
QUERY_SCHEMA_VERSION = "actor-detail-query-schema-v1"
QUERY_VERSION = "actor-detail-query-v1"
MATCHER_VERSION = "actor-detail-matcher-v1"
TEMPORAL_MATCHER_VERSION = "actor-detail-matcher-v2"
MAX_DETAIL_FRAMES = 9
MAX_DETAIL_SHOTS = 9
MAX_SHOT_ACTORS = 8
MAX_ACTOR_ATTRIBUTES = 16
MAX_QUERY_CONDITIONS = 16


class AttributeKind(StrEnum):
    HAIR_COLOR = "hair_color"
    CLOTHING_COLOR = "clothing_color"
    CLOTHING_SHAPE = "clothing_shape"
    HELD_SHAPE = "held_shape"
    HELD_CLASS = "held_class"
    ACTION = "action"
    EFFECT = "effect"
    ENVIRONMENT = "environment"


class AttributeStatus(StrEnum):
    OBSERVED = "observed"
    UNCERTAIN = "uncertain"


class MatchStatus(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NO_MATCH = "no_match"
    UNVERIFIED = "unverified"


_COLORS: dict[str, tuple[str, ...]] = {
    "white": ("白", "白色"),
    "black": ("黑", "黑色"),
    "red": ("红", "红色"),
    "blue": ("蓝", "蓝色"),
    "brown": ("棕", "棕色"),
    "orange": ("橙", "橙色"),
    "gray": ("灰", "灰色", "grey"),
    "green": ("绿", "绿色"),
    "yellow": ("黄", "黄色"),
    "purple": ("紫", "紫色"),
    "light": ("浅色", "light-colored"),
    "dark": ("深色", "dark-colored"),
}
_VALUES: dict[AttributeKind, dict[str, tuple[str, ...]]] = {
    AttributeKind.HAIR_COLOR: {
        **_COLORS,
        "white": (*_COLORS["white"], "白发", "white hair"),
        "black": (*_COLORS["black"], "黑发", "black hair"),
        "blue": (*_COLORS["blue"], "蓝发", "blue hair"),
    },
    AttributeKind.CLOTHING_COLOR: _COLORS,
    AttributeKind.CLOTHING_SHAPE: {
        "upper_garment": ("上装", "top"),
        "coat": ("外套", "jacket"),
        "scarf": ("围巾",),
        "shorts": ("短裤",),
        "trousers": ("长裤", "pants"),
        "armor": ("盔甲", "armour"),
        "gloves": ("手套",),
    },
    AttributeKind.HELD_SHAPE: {
        "flat_object": ("扁平物体", "扁平物", "flat object"),
        "blue_flat_object": ("蓝色扁平物体", "蓝色扁平物", "blue flat object"),
        "long_rod": ("长杆", "long rod"),
        "curved_object": ("弯曲物体", "curved object"),
    },
    AttributeKind.HELD_CLASS: {
        "weapon": ("武器",),
        "staff": ("权杖",),
        "tool": ("工具",),
    },
    AttributeKind.ACTION: {
        "look_up": ("抬头", "look up", "looking up"),
        "move": ("移动", "moving"),
        "run": ("奔跑", "running"),
        "jump": ("跳跃", "jumping"),
        "raise_item": ("举起持有物", "raise item"),
        "shoot": ("射击", "shooting"),
    },
    AttributeKind.EFFECT: {
        "light_arc": ("光弧", "light arc"),
        "light_ring": ("光环", "light ring"),
        "projectile": ("投射物",),
    },
    AttributeKind.ENVIRONMENT: {
        "water": ("水面",),
        "stone_platform": ("石块平台", "stone platform"),
        "sandy_ground": ("沙地", "sandy ground"),
        "indoors": ("室内",),
        "outdoors": ("室外",),
    },
}
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_EVIDENCE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}:[A-Za-z0-9_-]{1,128}:image:[0-9]{6}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _identifier(value: object) -> None:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid local detail identity.")


def _hash(value: object) -> None:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("Detail identities require lowercase SHA-256 hashes.")


def _version(value: object, expected: str) -> None:
    if type(value) is not str or value != expected:
        raise ValueError("Unsupported typed detail version.")


def _items(value: object, item_type: type[object], maximum: int, *, nonempty: bool = False) -> None:
    if (
        type(value) is not tuple
        or len(value) > maximum
        or (nonempty and not value)
        or any(type(item) is not item_type for item in value)
    ):
        raise ValueError("Invalid bounded detail collection.")


def _references(value: tuple[str, ...]) -> None:
    _items(value, str, MAX_DETAIL_FRAMES, nonempty=True)
    if len(set(value)) != len(value) or any(not _EVIDENCE_ID.fullmatch(item) for item in value):
        raise ValueError("Detail references must be unique registered image identities.")


def normalize_attribute_value(kind: AttributeKind, value: str) -> str:
    """Only this frozen explicit vocabulary supplies equivalence; no text guessing."""
    if type(kind) is not AttributeKind or type(value) is not str:
        raise ValueError("Detail kind/value types are invalid.")
    token = value.strip().casefold()
    for canonical, aliases in _VALUES[kind].items():
        if token == canonical or token in aliases:
            return canonical
    raise ValueError("Unsupported attribute value in this vocabulary version.")


def attribute_value_options(kind: AttributeKind) -> tuple[tuple[str, str], ...]:
    """Canonical values and display aliases from the frozen query vocabulary."""
    if type(kind) is not AttributeKind:
        raise ValueError("Expected a typed attribute kind.")
    return tuple((value, aliases[0]) for value, aliases in _VALUES[kind].items())


def values_are_exclusive(kind: AttributeKind, left: str, right: str) -> bool:
    """Explicit visual alternatives; different mechanics or shapes are not negations."""
    if (
        normalize_attribute_value(kind, left) != left
        or normalize_attribute_value(kind, right) != right
    ):
        raise ValueError("Exclusion requires canonical values from the frozen vocabulary.")
    if left == right:
        return False
    if kind in (AttributeKind.HAIR_COLOR, AttributeKind.CLOTHING_COLOR):
        hues = frozenset(_COLORS) - {"light", "dark"}
        return (left in hues and right in hues) or {left, right} == {"light", "dark"}
    if kind == AttributeKind.CLOTHING_SHAPE:
        # A generic upper garment can also be a coat or armor.
        garments = {"coat", "scarf", "shorts", "trousers", "armor", "gloves"}
        return left in garments and right in garments
    return False


@dataclass(frozen=True, slots=True)
class DetailEvidence:
    evidence_id: str
    image_sha256: str
    source_time: SourceInstant

    def __post_init__(self) -> None:
        _references((self.evidence_id,))
        _hash(self.image_sha256)
        if type(self.source_time) is not SourceInstant:
            raise ValueError("Detail evidence needs a typed source instant.")


@dataclass(frozen=True, slots=True)
class DetailAttribute:
    part_id: str
    kind: AttributeKind
    value: str
    status: AttributeStatus
    evidence_ids: tuple[str, ...]
    source_range: SourceRange

    def __post_init__(self) -> None:
        _identifier(self.part_id)
        if type(self.status) is not AttributeStatus or type(self.source_range) is not SourceRange:
            raise ValueError("Attribute status/range types are invalid.")
        object.__setattr__(self, "value", normalize_attribute_value(self.kind, self.value))
        _references(self.evidence_ids)
        if self.kind == AttributeKind.ACTION and len(self.evidence_ids) < 2:
            raise ValueError("An action requires multiple source frames.")


@dataclass(frozen=True, slots=True)
class ActorDetail:
    shot_id: str
    actor_id: str
    description: str
    attributes: tuple[DetailAttribute, ...]

    def __post_init__(self) -> None:
        _identifier(self.shot_id)
        _identifier(self.actor_id)
        if (
            type(self.description) is not str
            or not self.description.strip()
            or len(self.description) > 500
        ):
            raise ValueError("An actor needs a bounded neutral visible description.")
        _items(self.attributes, DetailAttribute, MAX_ACTOR_ATTRIBUTES)
        if len(set(self.attributes)) != len(self.attributes):
            raise ValueError("Repeated actor attributes are invalid.")
        if any(item.kind == AttributeKind.ENVIRONMENT for item in self.attributes):
            raise ValueError("Environment attributes cannot belong to an actor.")


@dataclass(frozen=True, slots=True)
class ShotDetail:
    shot_id: str
    source_range: SourceRange
    evidence_ids: tuple[str, ...]
    environment: tuple[DetailAttribute, ...]
    actors: tuple[ActorDetail, ...]

    def __post_init__(self) -> None:
        _identifier(self.shot_id)
        if type(self.source_range) is not SourceRange:
            raise ValueError("A shot needs a typed source range.")
        _references(self.evidence_ids)
        _items(self.environment, DetailAttribute, MAX_ACTOR_ATTRIBUTES)
        _items(self.actors, ActorDetail, MAX_SHOT_ACTORS)
        if len(set(self.environment)) != len(self.environment):
            raise ValueError("Repeated environment attributes are invalid.")
        if any(item.kind != AttributeKind.ENVIRONMENT for item in self.environment):
            raise ValueError("Shot environment contains a non-environment attribute.")
        if len({actor.actor_id for actor in self.actors}) != len(self.actors):
            raise ValueError("Actor identities must be unique within their shot.")
        if any(actor.shot_id != self.shot_id for actor in self.actors):
            raise ValueError("An actor cannot borrow another shot's identity.")


def source_range_for_evidence(evidence: tuple[DetailEvidence, ...]) -> SourceRange:
    """Derive a supported half-open hull from actual source clocks, not model times."""
    _items(evidence, DetailEvidence, MAX_DETAIL_FRAMES, nonempty=True)
    times = tuple(item.source_time.time_us for item in evidence)
    duration = evidence[0].source_time.duration_us
    if (
        len({item.evidence_id for item in evidence}) != len(evidence)
        or any(item.source_time.duration_us != duration for item in evidence)
        or any(left >= right for left, right in zip(times, times[1:], strict=False))
    ):
        raise ValueError("Evidence needs unique increasing clocks in one media duration.")
    return SourceRange(times[0], times[-1] + 1, duration)


@dataclass(frozen=True, slots=True)
class CandidateDetail:
    run_id: str
    media_id: str
    event_id: str
    candidate_id: str
    event_fingerprint: str
    media_sha256: str
    configuration_hash: str
    pipeline_version: str
    base_prompt_version: str
    base_prompt_hash: str
    detail_identity_hash: str
    source_range: SourceRange
    evidence: tuple[DetailEvidence, ...]
    shots: tuple[ShotDetail, ...]
    notes: tuple[str, ...] = ()
    unassigned_evidence_ids: tuple[str, ...] = ()
    schema_version: str = DETAIL_SCHEMA_VERSION
    vocabulary_version: str = DETAIL_VOCABULARY_VERSION
    temporal_scene: "TemporalScene | None" = None

    def __post_init__(self) -> None:
        for identity in (
            self.run_id,
            self.media_id,
            self.pipeline_version,
            self.base_prompt_version,
        ):
            _identifier(identity)
        for value in (
            self.event_fingerprint,
            self.media_sha256,
            self.configuration_hash,
            self.base_prompt_hash,
            self.detail_identity_hash,
        ):
            _hash(value)
        if type(self.event_id) is not str or not re.fullmatch(
            re.escape(f"{self.run_id}:{self.media_id}:event:") + r"[0-9a-f]{24}", self.event_id
        ):
            raise ValueError("Detail base event belongs to a different run/media.")
        candidate_id = (
            "clip-"
            + hashlib.sha256(f"{self.run_id}:event:{self.event_id}".encode()).hexdigest()[:24]
        )
        if type(self.candidate_id) is not str or self.candidate_id != candidate_id:
            raise ValueError("Detail candidate identity does not match the registered event.")
        if self.temporal_scene is None:
            _version(self.schema_version, DETAIL_SCHEMA_VERSION)
        else:
            from gamingcreator.domain.temporal_entities import TemporalScene

            _version(self.schema_version, DETAIL_TEMPORAL_SCHEMA_VERSION)
            if type(self.temporal_scene) is not TemporalScene:
                raise ValueError("Temporal details require a validated scene.")
            if self.temporal_scene.evidence != self.evidence:
                raise ValueError("Temporal scene must use the exact candidate evidence.")
        _version(self.vocabulary_version, DETAIL_VOCABULARY_VERSION)
        if type(self.source_range) is not SourceRange:
            raise ValueError("Candidate details require the original typed source range.")
        source_range_for_evidence(self.evidence)
        references = {item.evidence_id: item for item in self.evidence}
        for item in self.evidence:
            if (
                not item.evidence_id.startswith(f"{self.run_id}:{self.media_id}:image:")
                or item.source_time.duration_us != self.source_range.duration_us
                or not self.source_range.start_us
                <= item.source_time.time_us
                < self.source_range.end_us
            ):
                raise ValueError(
                    "Evidence is foreign or outside the original candidate source clock."
                )
        _items(self.shots, ShotDetail, MAX_DETAIL_SHOTS)
        if len({shot.shot_id for shot in self.shots}) != len(self.shots):
            raise ValueError("Shot identities must be unique within the candidate.")
        shots = tuple(
            sorted(self.shots, key=lambda shot: (shot.source_range.start_us, shot.shot_id))
        )
        used: set[str] = set()
        previous_end = -1
        for shot in shots:
            self._validate_support(shot.evidence_ids, shot.source_range, references)
            if shot.source_range.start_us < previous_end or used.intersection(shot.evidence_ids):
                raise ValueError("Shot ranges/evidence cannot overlap.")
            previous_end = shot.source_range.end_us
            used.update(shot.evidence_ids)
            for attribute in (
                *shot.environment,
                *(item for actor in shot.actors for item in actor.attributes),
            ):
                if not set(attribute.evidence_ids).issubset(shot.evidence_ids):
                    raise ValueError("An attribute cannot cite another shot's evidence.")
                self._validate_support(attribute.evidence_ids, attribute.source_range, references)
                if (
                    attribute.kind == AttributeKind.ACTION
                    and len({references[item].image_sha256 for item in attribute.evidence_ids}) < 2
                ):
                    raise ValueError(
                        "An action needs different image content at different source times."
                    )
        _items(self.notes, str, MAX_ACTOR_ATTRIBUTES)
        if any(not note.strip() or len(note) > 500 for note in self.notes):
            raise ValueError("Invalid bounded pending-detail note.")
        _items(self.unassigned_evidence_ids, str, MAX_DETAIL_FRAMES)
        unassigned = tuple(
            item.evidence_id for item in self.evidence if item.evidence_id not in used
        )
        if self.unassigned_evidence_ids and self.unassigned_evidence_ids != unassigned:
            raise ValueError("Unassigned evidence must come from the frozen request.")
        object.__setattr__(self, "shots", shots)
        object.__setattr__(self, "unassigned_evidence_ids", unassigned)

    @staticmethod
    def _validate_support(
        ids: tuple[str, ...], interval: SourceRange, registered: dict[str, DetailEvidence]
    ) -> None:
        if any(item not in registered for item in ids):
            raise ValueError("A detail references evidence outside the frozen request.")
        expected = source_range_for_evidence(tuple(registered[item] for item in ids))
        if interval != expected:
            raise ValueError("Detail range/duration must equal the actual cited source-clock hull.")


@dataclass(frozen=True, slots=True)
class AttributeConstraint:
    kind: AttributeKind
    value: str
    part_group: str

    def __post_init__(self) -> None:
        _identifier(self.part_group)
        object.__setattr__(self, "value", normalize_attribute_value(self.kind, self.value))


def constraint_sort_key(condition: AttributeConstraint) -> tuple[str, str, str]:
    return condition.part_group, condition.kind.value, condition.value


@dataclass(frozen=True, slots=True)
class QueryConstraint:
    actor_all: tuple[AttributeConstraint, ...]
    environment_all: tuple[AttributeConstraint, ...] = ()
    schema_version: str = QUERY_SCHEMA_VERSION
    version: str = QUERY_VERSION
    vocabulary_version: str = DETAIL_VOCABULARY_VERSION

    def __post_init__(self) -> None:
        _items(self.actor_all, AttributeConstraint, MAX_QUERY_CONDITIONS, nonempty=True)
        _items(self.environment_all, AttributeConstraint, MAX_QUERY_CONDITIONS)
        _version(self.schema_version, QUERY_SCHEMA_VERSION)
        _version(self.version, QUERY_VERSION)
        _version(self.vocabulary_version, DETAIL_VOCABULARY_VERSION)
        if any(item.kind == AttributeKind.ENVIRONMENT for item in self.actor_all) or any(
            item.kind != AttributeKind.ENVIRONMENT for item in self.environment_all
        ):
            raise ValueError("Actor/environment constraint scopes are separate.")
        if len(set(self.actor_all)) != len(self.actor_all) or len(set(self.environment_all)) != len(
            self.environment_all
        ):
            raise ValueError("Repeated normalized query conditions are invalid.")
        object.__setattr__(
            self, "actor_all", tuple(sorted(self.actor_all, key=constraint_sort_key))
        )
        object.__setattr__(
            self, "environment_all", tuple(sorted(self.environment_all, key=constraint_sort_key))
        )


def canonical_constraint_json(constraint: QueryConstraint) -> str:
    if type(constraint) is not QueryConstraint:
        raise ValueError("A typed query constraint is required.")

    def conditions(items: tuple[AttributeConstraint, ...]) -> list[dict[str, str]]:
        return [
            {"kind": item.kind.value, "value": item.value, "partGroup": item.part_group}
            for item in items
        ]

    return json.dumps(
        {
            "schemaVersion": constraint.schema_version,
            "version": constraint.version,
            "vocabularyVersion": constraint.vocabulary_version,
            "actorAll": conditions(constraint.actor_all),
            "environmentAll": conditions(constraint.environment_all),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def constraint_hash(constraint: QueryConstraint) -> str:
    return hashlib.sha256(canonical_constraint_json(constraint).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ConstraintSupport:
    condition: AttributeConstraint
    part_id: str
    evidence_ids: tuple[str, ...]
    source_range: SourceRange

    def __post_init__(self) -> None:
        if type(self.condition) is not AttributeConstraint:
            raise ValueError("A match support requires a typed condition.")
        _identifier(self.part_id)
        _references(self.evidence_ids)
        if type(self.source_range) is not SourceRange:
            raise ValueError("Match support requires its actual source range.")


@dataclass(frozen=True, slots=True)
class AttributeConflict:
    part_id: str
    kind: AttributeKind
    values: tuple[str, str]
    source_range: SourceRange
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.part_id)
        _items(self.values, str, 2, nonempty=True)
        if (
            len(self.values) != 2
            or type(self.kind) is not AttributeKind
            or type(self.source_range) is not SourceRange
            or any(normalize_attribute_value(self.kind, value) != value for value in self.values)
            or not values_are_exclusive(self.kind, *self.values)
        ):
            raise ValueError("A conflict requires explicitly exclusive canonical observed values.")
        _references(self.evidence_ids)


@dataclass(frozen=True, slots=True)
class ActorMatch:
    shot_id: str
    actor_id: str
    satisfied: tuple[ConstraintSupport, ...]
    missing: tuple[AttributeConstraint, ...]
    uncertain: tuple[ConstraintSupport, ...]
    opposed: tuple[ConstraintSupport, ...]
    shared_evidence_ids: tuple[str, ...]
    source_range: SourceRange | None
    conflicts: tuple[AttributeConflict, ...]
    counter_evidence: tuple[ConstraintSupport, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.shot_id)
        _identifier(self.actor_id)
        for values in (self.satisfied, self.uncertain, self.opposed):
            _items(values, ConstraintSupport, 2 * MAX_QUERY_CONDITIONS)
        _items(self.missing, AttributeConstraint, 2 * MAX_QUERY_CONDITIONS)
        conditions = (
            *self.missing,
            *(item.condition for item in self.satisfied),
            *(item.condition for item in self.uncertain),
            *(item.condition for item in self.opposed),
        )
        if len(conditions) > 2 * MAX_QUERY_CONDITIONS or len(set(conditions)) != len(conditions):
            raise ValueError("A match condition must have exactly one reported state.")
        bindings: dict[tuple[bool, str], str] = {}
        for item in self.satisfied:
            group = (item.condition.kind == AttributeKind.ENVIRONMENT, item.condition.part_group)
            if group in bindings and bindings[group] != item.part_id:
                raise ValueError(
                    "Satisfied conditions in one part group cannot pool different parts."
                )
            bindings[group] = item.part_id
        _items(
            self.counter_evidence, ConstraintSupport, 2 * MAX_QUERY_CONDITIONS * MAX_DETAIL_FRAMES
        )
        if any(item.condition not in conditions for item in self.counter_evidence):
            raise ValueError("Counter-evidence must refer to a reported condition.")
        _items(self.conflicts, AttributeConflict, MAX_ACTOR_ATTRIBUTES**2)
        _items(self.shared_evidence_ids, str, MAX_DETAIL_FRAMES)
        if self.shared_evidence_ids:
            _references(self.shared_evidence_ids)
            if type(self.source_range) is not SourceRange or not self.satisfied:
                raise ValueError("Shared match evidence needs a supported source range.")
            if any(
                not set(self.shared_evidence_ids).issubset(item.evidence_ids)
                for item in self.satisfied
            ):
                raise ValueError("Shared match evidence must support every satisfied condition.")
            intervals = tuple(item.source_range for item in self.satisfied)
            if any(item.duration_us != self.source_range.duration_us for item in intervals):
                raise ValueError("Common match support must share the actual media duration.")
            expected = SourceRange(
                max(item.start_us for item in intervals),
                min(item.end_us for item in intervals),
                self.source_range.duration_us,
            )
            if self.source_range != expected:
                raise ValueError("Common match range must equal the actual support intersection.")
        elif self.source_range is not None:
            raise ValueError("A common range alone is not shared match evidence.")


@dataclass(frozen=True, slots=True)
class DetailMatch:
    status: MatchStatus
    constraint_hash: str
    matches: tuple[ActorMatch, ...]
    notes: tuple[str, ...] = ()
    schema_version: str = DETAIL_SCHEMA_VERSION
    query_schema_version: str = QUERY_SCHEMA_VERSION
    query_version: str = QUERY_VERSION
    vocabulary_version: str = DETAIL_VOCABULARY_VERSION
    matcher_version: str = MATCHER_VERSION

    def __post_init__(self) -> None:
        if type(self.status) is not MatchStatus:
            raise ValueError("Invalid typed match status.")
        _hash(self.constraint_hash)
        _items(self.matches, ActorMatch, MAX_DETAIL_SHOTS * MAX_SHOT_ACTORS)
        _items(self.notes, str, MAX_ACTOR_ATTRIBUTES + 2)
        if any(not item.strip() or len(item) > 500 for item in self.notes):
            raise ValueError("Invalid bounded match note.")
        temporal = self.matcher_version == TEMPORAL_MATCHER_VERSION
        _version(
            self.schema_version,
            DETAIL_TEMPORAL_SCHEMA_VERSION if temporal else DETAIL_SCHEMA_VERSION,
        )
        _version(self.matcher_version, TEMPORAL_MATCHER_VERSION if temporal else MATCHER_VERSION)
        for value, expected in (
            (self.query_schema_version, QUERY_SCHEMA_VERSION),
            (self.query_version, QUERY_VERSION),
            (self.vocabulary_version, DETAIL_VOCABULARY_VERSION),
        ):
            _version(value, expected)
        if len({(item.shot_id, item.actor_id) for item in self.matches}) != len(self.matches):
            raise ValueError("Repeated shot/actor matches are invalid.")
        if self.status == MatchStatus.FULL and not any(
            item.satisfied
            and item.shared_evidence_ids
            and not item.missing
            and not item.uncertain
            and not item.opposed
            and not item.conflicts
            for item in self.matches
        ):
            raise ValueError("A full match requires complete shared observed support.")
        if self.status == MatchStatus.NO_MATCH and (
            not self.matches or not all(item.counter_evidence for item in self.matches)
        ):
            raise ValueError("No-match requires explicit opposition for every potential actor.")
        if self.status == MatchStatus.PARTIAL and not any(item.satisfied for item in self.matches):
            raise ValueError("A partial match needs an observed supported subset.")
