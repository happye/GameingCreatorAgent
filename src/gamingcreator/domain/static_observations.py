"""Immutable static-appearance declarations; local imports only, no inference or I/O."""

import hashlib
import json
import re
from dataclasses import dataclass

from gamingcreator.domain.actor_details import (
    DETAIL_VOCABULARY_VERSION,
    MAX_QUERY_CONDITIONS,
    AttributeConstraint,
    AttributeKind,
    AttributeStatus,
    QueryConstraint,
    constraint_sort_key,
    normalize_attribute_value,
)
from gamingcreator.domain.time import SourceInstant, SourceRange

STATIC_OBSERVATION_SCHEMA_VERSION = "static-observation-import-v1"
STATIC_QUERY_SCHEMA_VERSION = "static-observation-query-v1"
STATIC_SEARCH_RESULT_SCHEMA_VERSION = "static-observation-search-result-v1"
STATIC_IMPORT_RESULT_SCHEMA_VERSION = "static-observation-import-result-v1"
STATIC_STORE_SCHEMA_VERSION = "static-observation-store-v1"
STATIC_KIND = "static_appearance"
STATIC_CLAIM = "imported_local_declaration_only"
STATIC_VOCABULARY_VERSION = DETAIL_VOCABULARY_VERSION
MAX_STATIC_PACKAGE_BYTES = 1_048_576
MAX_STATIC_OBSERVATIONS = 128
MAX_STATIC_OBSERVATION_ACTORS = 8
MAX_STATIC_ACTOR_ATTRIBUTES = 16
MAX_STATIC_PROVENANCE_NOTE = 500
STATIC_ATTRIBUTE_KINDS = frozenset(
    {
        AttributeKind.HAIR_COLOR,
        AttributeKind.CLOTHING_COLOR,
        AttributeKind.CLOTHING_SHAPE,
        AttributeKind.HELD_SHAPE,
        AttributeKind.HELD_CLASS,
    }
)

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_LOCAL_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_EVIDENCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,511}\Z")
_OBSERVATION_ID = re.compile(r"static-[0-9a-f]{64}\Z")


class StaticObservationError(ValueError):
    """A local static declaration is malformed; messages never echo imported values."""


class UnsupportedStaticSchema(StaticObservationError):
    """A package, query, or store schema version outside this release."""


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise StaticObservationError(f"Invalid static {label} identity.")
    return value


def _hash(value: object, label: str) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise StaticObservationError(f"Invalid static {label} SHA-256.")
    return value


def _local_identifier(value: object, label: str) -> str:
    if type(value) is not str or not _LOCAL_IDENTIFIER.fullmatch(value):
        raise StaticObservationError(f"Invalid static {label} identity.")
    return value


def _text(value: object, label: str, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise StaticObservationError(f"Invalid static {label} text.")
    return value.strip()


def _items(value: object, item_type: type[object], maximum: int, *, minimum: int = 0) -> None:
    if (
        type(value) is not tuple
        or not minimum <= len(value) <= maximum
        or any(type(item) is not item_type for item in value)
    ):
        raise StaticObservationError("Invalid bounded static collection.")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _attribute_sort_key(attribute: "StaticAttribute") -> tuple[str, str, str, str, str]:
    return (
        attribute.part_group,
        attribute.part_id,
        attribute.kind.value,
        attribute.value,
        attribute.status.value,
    )


@dataclass(frozen=True, slots=True)
class StaticAttribute:
    part_group: str
    part_id: str
    kind: AttributeKind
    value: str
    status: AttributeStatus

    def __post_init__(self) -> None:
        _local_identifier(self.part_group, "part group")
        _local_identifier(self.part_id, "part")
        if type(self.kind) is not AttributeKind or self.kind not in STATIC_ATTRIBUTE_KINDS:
            raise StaticObservationError("Unsupported static attribute kind.")
        if type(self.status) is not AttributeStatus:
            raise StaticObservationError("Unsupported static attribute status.")
        try:
            value = normalize_attribute_value(self.kind, self.value)
        except ValueError as error:
            raise StaticObservationError("Unsupported static attribute value.") from error
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class StaticActor:
    actor_id: str
    attributes: tuple[StaticAttribute, ...]

    def __post_init__(self) -> None:
        _local_identifier(self.actor_id, "actor")
        _items(self.attributes, StaticAttribute, MAX_STATIC_ACTOR_ATTRIBUTES)
        if len(set(self.attributes)) != len(self.attributes):
            raise StaticObservationError("Repeated static attributes are invalid.")
        object.__setattr__(
            self, "attributes", tuple(sorted(self.attributes, key=_attribute_sort_key))
        )


@dataclass(frozen=True, slots=True)
class StaticObservation:
    local_observation_id: str
    evidence_id: str
    actors: tuple[StaticActor, ...]

    def __post_init__(self) -> None:
        _local_identifier(self.local_observation_id, "observation")
        if type(self.evidence_id) is not str or not _EVIDENCE_ID.fullmatch(self.evidence_id):
            raise StaticObservationError("Invalid registered static frame identity.")
        _items(self.actors, StaticActor, MAX_STATIC_OBSERVATION_ACTORS)
        if len({actor.actor_id for actor in self.actors}) != len(self.actors):
            raise StaticObservationError("Actor identities must be unique in one static frame.")
        object.__setattr__(
            self, "actors", tuple(sorted(self.actors, key=lambda actor: actor.actor_id))
        )


@dataclass(frozen=True, slots=True)
class StaticObservationProvenance:
    source_note: str
    source_payload_sha256: str
    source_payload_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_note",
            _text(self.source_note, "provenance note", MAX_STATIC_PROVENANCE_NOTE),
        )
        _hash(self.source_payload_sha256, "source payload")
        _identifier(self.source_payload_version, "source payload version")


@dataclass(frozen=True, slots=True)
class StaticObservationPackage:
    run_id: str
    collection_id: str
    media_id: str
    source_sha256: str
    config_hash: str
    pipeline_version: str
    provenance: StaticObservationProvenance
    observations: tuple[StaticObservation, ...]
    pipeline_hash: str | None = None
    schema_version: str = STATIC_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not str
            or self.schema_version != STATIC_OBSERVATION_SCHEMA_VERSION
        ):
            raise UnsupportedStaticSchema("Unsupported static observation package version.")
        _identifier(self.run_id, "run")
        _identifier(self.collection_id, "collection")
        _identifier(self.media_id, "media")
        _hash(self.source_sha256, "source")
        _hash(self.config_hash, "configuration")
        _identifier(self.pipeline_version, "pipeline version")
        if self.pipeline_hash is not None:
            _hash(self.pipeline_hash, "pipeline")
        if type(self.provenance) is not StaticObservationProvenance:
            raise StaticObservationError("Static provenance is required.")
        _items(
            self.observations,
            StaticObservation,
            MAX_STATIC_OBSERVATIONS,
            minimum=1,
        )
        if len({item.local_observation_id for item in self.observations}) != len(self.observations):
            raise StaticObservationError("Repeated static observation identities are invalid.")
        if len({item.evidence_id for item in self.observations}) != len(self.observations):
            raise StaticObservationError(
                "A static frame cannot be declared twice in one collection."
            )
        object.__setattr__(
            self,
            "observations",
            tuple(sorted(self.observations, key=lambda item: item.local_observation_id)),
        )


@dataclass(frozen=True, slots=True)
class StaticQuery:
    run_id: str
    collection_id: str
    constraint: QueryConstraint
    schema_version: str = STATIC_QUERY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not str
            or self.schema_version != STATIC_QUERY_SCHEMA_VERSION
        ):
            raise UnsupportedStaticSchema("Unsupported static observation query version.")
        _identifier(self.run_id, "run")
        _identifier(self.collection_id, "collection")
        if type(self.constraint) is not QueryConstraint:
            raise StaticObservationError("A typed static query constraint is required.")
        if self.constraint.environment_all:
            raise StaticObservationError("Environment conditions are not part of this slice.")
        if any(
            condition.kind not in STATIC_ATTRIBUTE_KINDS for condition in self.constraint.actor_all
        ):
            raise StaticObservationError(
                "Only the five typed static attribute kinds are queryable."
            )


@dataclass(frozen=True, slots=True)
class StaticAttributeSupport:
    condition: AttributeConstraint
    part_id: str
    evidence_id: str
    source_range: SourceRange

    def __post_init__(self) -> None:
        if type(self.condition) is not AttributeConstraint:
            raise StaticObservationError("A static support needs a typed condition.")
        _local_identifier(self.part_id, "part")
        if type(self.evidence_id) is not str or not _EVIDENCE_ID.fullmatch(self.evidence_id):
            raise StaticObservationError("Invalid static support evidence identity.")
        if type(self.source_range) is not SourceRange:
            raise StaticObservationError("A static support needs its registered source range.")


@dataclass(frozen=True, slots=True)
class StaticObservationMatch:
    observation_id: str
    local_observation_id: str
    actor_id: str
    evidence_id: str
    image_sha256: str
    artifact_path: str
    source_path: str
    source_range: SourceRange
    supported: tuple[StaticAttributeSupport, ...]

    def __post_init__(self) -> None:
        if type(self.observation_id) is not str or not _OBSERVATION_ID.fullmatch(
            self.observation_id
        ):
            raise StaticObservationError("Invalid static observation identity.")
        _local_identifier(self.local_observation_id, "observation")
        _local_identifier(self.actor_id, "actor")
        if type(self.evidence_id) is not str or not _EVIDENCE_ID.fullmatch(self.evidence_id):
            raise StaticObservationError("Invalid static match evidence identity.")
        _hash(self.image_sha256, "registered image")
        for value, label in (
            (self.artifact_path, "artifact path"),
            (self.source_path, "source path"),
        ):
            if type(value) is not str or not value.strip() or "\x00" in value:
                raise StaticObservationError(f"Invalid static {label}.")
        if type(self.source_range) is not SourceRange:
            raise StaticObservationError("A static match needs a registered source range.")
        _items(
            self.supported,
            StaticAttributeSupport,
            MAX_QUERY_CONDITIONS,
            minimum=1,
        )
        if any(
            item.evidence_id != self.evidence_id or item.source_range != self.source_range
            for item in self.supported
        ):
            raise StaticObservationError("Static support must stay in one registered frame.")


def static_source_range(instant: SourceInstant) -> SourceRange:
    """The registered frame supports exactly [t, t+1), never a model-supplied time."""
    if type(instant) is not SourceInstant:
        raise StaticObservationError("A static frame needs a typed source instant.")
    return SourceRange(instant.time_us, instant.time_us + 1, instant.duration_us)


def _attribute_document(attribute: StaticAttribute) -> dict[str, object]:
    return {
        "partGroup": attribute.part_group,
        "partId": attribute.part_id,
        "kind": attribute.kind.value,
        "value": attribute.value,
        "status": attribute.status.value,
    }


def _observation_document(observation: StaticObservation) -> dict[str, object]:
    return {
        "localObservationId": observation.local_observation_id,
        "evidenceId": observation.evidence_id,
        "actors": [
            {
                "actorId": actor.actor_id,
                "attributes": [_attribute_document(attribute) for attribute in actor.attributes],
            }
            for actor in observation.actors
        ],
    }


def canonical_provenance_json(provenance: StaticObservationProvenance) -> str:
    if type(provenance) is not StaticObservationProvenance:
        raise StaticObservationError("Typed static provenance is required.")
    return _canonical_json(
        {
            "sourceNote": provenance.source_note,
            "sourcePayloadSha256": provenance.source_payload_sha256,
            "sourcePayloadVersion": provenance.source_payload_version,
        }
    )


def canonical_observation_json(observation: StaticObservation) -> str:
    if type(observation) is not StaticObservation:
        raise StaticObservationError("Typed static observation is required.")
    return _canonical_json(_observation_document(observation))


def canonical_package_json(package: StaticObservationPackage) -> str:
    if type(package) is not StaticObservationPackage:
        raise StaticObservationError("Typed static observation package is required.")
    document: dict[str, object] = {
        "schemaVersion": package.schema_version,
        "runId": package.run_id,
        "collectionId": package.collection_id,
        "mediaId": package.media_id,
        "sourceSha256": package.source_sha256,
        "configHash": package.config_hash,
        "pipelineVersion": package.pipeline_version,
        "provenance": {
            "sourceNote": package.provenance.source_note,
            "sourcePayloadSha256": package.provenance.source_payload_sha256,
            "sourcePayloadVersion": package.provenance.source_payload_version,
        },
        "observations": [
            _observation_document(observation) for observation in package.observations
        ],
    }
    if package.pipeline_hash is not None:
        document["pipelineHash"] = package.pipeline_hash
    return _canonical_json(document)


def package_sha256(package: StaticObservationPackage) -> str:
    return hashlib.sha256(canonical_package_json(package).encode("utf-8")).hexdigest()


def observation_id(package: StaticObservationPackage, observation: StaticObservation) -> str:
    if type(package) is not StaticObservationPackage:
        raise StaticObservationError("Typed static observation package is required.")
    if type(observation) is not StaticObservation or observation not in package.observations:
        raise StaticObservationError("Observation identity must belong to its package.")
    material = "\x1f".join(
        (
            STATIC_OBSERVATION_SCHEMA_VERSION,
            package.run_id,
            package.collection_id,
            package.media_id,
            observation.evidence_id,
            observation.local_observation_id,
        )
    )
    return "static-" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def canonical_query_json(query: StaticQuery) -> str:
    if type(query) is not StaticQuery:
        raise StaticObservationError("Typed static query is required.")
    return _canonical_json(
        {
            "schemaVersion": query.schema_version,
            "runId": query.run_id,
            "collectionId": query.collection_id,
            "actorAll": [
                {
                    "kind": condition.kind.value,
                    "value": condition.value,
                    "partGroup": condition.part_group,
                }
                for condition in query.constraint.actor_all
            ],
        }
    )


def query_sha256(query: StaticQuery) -> str:
    return hashlib.sha256(canonical_query_json(query).encode("utf-8")).hexdigest()


def sorted_supports(
    supports: tuple[StaticAttributeSupport, ...],
) -> tuple[StaticAttributeSupport, ...]:
    return tuple(
        sorted(
            supports,
            key=lambda item: (*constraint_sort_key(item.condition), item.part_id),
        )
    )
