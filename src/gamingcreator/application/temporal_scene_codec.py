"""Strict pure model/persistence codec for registered temporal scenes."""

import json

from gamingcreator.domain.actor_details import (
    AttributeKind,
    AttributeStatus,
    DetailAttribute,
    DetailEvidence,
    source_range_for_evidence,
)
from gamingcreator.domain.temporal_entities import (
    MAX_SCENE_ENTITIES,
    MAX_SCENE_OWNERS,
    TEMPORAL_SCENE_VERSION,
    ClassificationBasis,
    EntityClassification,
    EntityKind,
    EntityObservation,
    EntityPart,
    EntityPartGroup,
    FrameTransition,
    OwnerRelation,
    TemporalEntity,
    TemporalScene,
    TransitionBasis,
    TransitionState,
    Visibility,
)
from gamingcreator.domain.time import SourceInstant

MAX_SCENE_BYTES = 1_048_576
_MODEL_FIELDS = {"transitions", "entities", "owners", "environment", "notes"}


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Unexpected temporal scene fields.")
    return value


def _list(value: object, maximum: int) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        raise ValueError("Invalid bounded temporal scene collection.")
    return value


def _string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("Temporal scene strings must have the correct type.")
    return value


def _refs(value: object) -> tuple[str, ...]:
    return tuple(_string(item) for item in _list(value, 9))


def _bounded(value: object) -> None:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Invalid temporal JSON value.") from None
    if len(encoded) > MAX_SCENE_BYTES:
        raise ValueError("Temporal scene exceeds its byte limit.")


def scene_from_model(payload: object, evidence: tuple[DetailEvidence, ...]) -> TemporalScene:
    _bounded(payload)
    value = _object(payload, _MODEL_FIELDS)
    source_range_for_evidence(evidence)
    registered = {item.evidence_id: item for item in evidence}

    def attribute(raw: object, part_id: str | None = None) -> DetailAttribute:
        fields = {"kind", "value", "status", "evidenceIds"}
        item = _object(raw, fields | ({"partId"} if part_id is None else set()))
        refs = _refs(item["evidenceIds"])
        if any(ref not in registered for ref in refs):
            raise ValueError("Unknown temporal attribute reference.")
        return DetailAttribute(
            _string(item["partId"]) if part_id is None else part_id,
            AttributeKind(_string(item["kind"])),
            _string(item["value"]),
            AttributeStatus(_string(item["status"])),
            refs,
            source_range_for_evidence(tuple(registered[ref] for ref in refs)),
        )

    transitions = []
    for raw in _list(value["transitions"], 8):
        item = _object(raw, {"beforeId", "afterId", "state", "basis", "reason"})
        transitions.append(
            FrameTransition(
                _string(item["beforeId"]),
                _string(item["afterId"]),
                TransitionState(_string(item["state"])),
                TransitionBasis(_string(item["basis"])),
                _string(item["reason"]),
            )
        )
    entities = []
    for raw in _list(value["entities"], MAX_SCENE_ENTITIES):
        item = _object(raw, {"entityId", "description", "classification", "observations", "parts"})
        classification = _object(
            item["classification"], {"kind", "status", "basis", "evidenceIds", "reason"}
        )
        observations = []
        for raw_observation in _list(item["observations"], 9):
            observation = _object(raw_observation, {"evidenceId", "visibility", "location"})
            observations.append(
                EntityObservation(
                    _string(observation["evidenceId"]),
                    Visibility(_string(observation["visibility"])),
                    _string(observation["location"]),
                )
            )
        parts = []
        for raw_part in _list(item["parts"], 16):
            part = _object(raw_part, {"partId", "partGroup", "attributes"})
            part_id = _string(part["partId"])
            parts.append(
                EntityPart(
                    part_id,
                    EntityPartGroup(_string(part["partGroup"])),
                    tuple(
                        attribute(raw_attribute, part_id)
                        for raw_attribute in _list(part["attributes"], 16)
                    ),
                )
            )
        entities.append(
            TemporalEntity(
                _string(item["entityId"]),
                _string(item["description"]),
                EntityClassification(
                    EntityKind(_string(classification["kind"])),
                    AttributeStatus(_string(classification["status"])),
                    ClassificationBasis(_string(classification["basis"])),
                    _refs(classification["evidenceIds"]),
                    _string(classification["reason"]),
                ),
                tuple(observations),
                tuple(parts),
            )
        )
    owners = []
    for raw in _list(value["owners"], MAX_SCENE_OWNERS):
        owner = _object(raw, {"objectId", "actorId", "status", "evidenceIds", "reason"})
        owners.append(
            OwnerRelation(
                _string(owner["objectId"]),
                _string(owner["actorId"]),
                AttributeStatus(_string(owner["status"])),
                _refs(owner["evidenceIds"]),
                _string(owner["reason"]),
            )
        )
    return TemporalScene(
        evidence,
        tuple(transitions),
        tuple(entities),
        tuple(owners),
        tuple(attribute(item) for item in _list(value["environment"], 16)),
        tuple(_string(item) for item in _list(value["notes"], 16)),
    )


def scene_payload(scene: TemporalScene) -> dict[str, object]:
    if type(scene) is not TemporalScene:
        raise ValueError("A validated temporal scene is required.")

    def attribute(item: DetailAttribute, *, include_part: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "kind": item.kind.value,
            "value": item.value,
            "status": item.status.value,
            "evidenceIds": list(item.evidence_ids),
        }
        if include_part:
            result["partId"] = item.part_id
        return result

    result: dict[str, object] = {
        "schemaVersion": scene.schema_version,
        "evidence": [
            {
                "evidenceId": item.evidence_id,
                "imageSha256": item.image_sha256,
                "sourceUs": item.source_time.time_us,
                "durationUs": item.source_time.duration_us,
            }
            for item in scene.evidence
        ],
        "transitions": [
            {
                "beforeId": item.before_id,
                "afterId": item.after_id,
                "state": item.state.value,
                "basis": item.basis.value,
                "reason": item.reason,
            }
            for item in scene.transitions
        ],
        "entities": [
            {
                "entityId": item.entity_id,
                "description": item.description,
                "classification": {
                    "kind": item.classification.kind.value,
                    "status": item.classification.status.value,
                    "basis": item.classification.basis.value,
                    "evidenceIds": list(item.classification.evidence_ids),
                    "reason": item.classification.reason,
                },
                "observations": [
                    {
                        "evidenceId": observation.evidence_id,
                        "visibility": observation.visibility.value,
                        "location": observation.location,
                    }
                    for observation in item.observations
                ],
                "parts": [
                    {
                        "partId": part.part_id,
                        "partGroup": part.part_group.value,
                        "attributes": [attribute(value) for value in part.attributes],
                    }
                    for part in item.parts
                ],
            }
            for item in scene.entities
        ],
        "owners": [
            {
                "objectId": item.object_id,
                "actorId": item.actor_id,
                "status": item.status.value,
                "evidenceIds": list(item.evidence_ids),
                "reason": item.reason,
            }
            for item in scene.owners
        ],
        "environment": [attribute(item, include_part=True) for item in scene.environment],
        "notes": list(scene.notes),
    }
    _bounded(result)
    return result


def scene_from_payload(value: object) -> TemporalScene:
    _bounded(value)
    document = _object(value, _MODEL_FIELDS | {"schemaVersion", "evidence"})
    if (
        type(document["schemaVersion"]) is not str
        or document["schemaVersion"] != TEMPORAL_SCENE_VERSION
    ):
        raise ValueError("Unsupported temporal scene payload version.")
    evidence = []
    for raw in _list(document["evidence"], 9):
        item = _object(raw, {"evidenceId", "imageSha256", "sourceUs", "durationUs"})
        if type(item["sourceUs"]) is not int or type(item["durationUs"]) is not int:
            raise ValueError("Registered temporal clocks must be integer microseconds.")
        evidence.append(
            DetailEvidence(
                _string(item["evidenceId"]),
                _string(item["imageSha256"]),
                SourceInstant(item["sourceUs"], item["durationUs"]),
            )
        )
    return scene_from_model({key: document[key] for key in _MODEL_FIELDS}, tuple(evidence))
