"""Strict versioned JSON codec for local static declarations; no execution or I/O."""

import json
from typing import cast

from gamingcreator.domain.actor_details import (
    DETAIL_VOCABULARY_VERSION,
    MAX_QUERY_CONDITIONS,
    QUERY_SCHEMA_VERSION,
    QUERY_VERSION,
    AttributeConstraint,
    AttributeKind,
    AttributeStatus,
    QueryConstraint,
)
from gamingcreator.domain.static_observations import (
    MAX_STATIC_ACTOR_ATTRIBUTES,
    MAX_STATIC_OBSERVATION_ACTORS,
    MAX_STATIC_OBSERVATIONS,
    MAX_STATIC_PACKAGE_BYTES,
    STATIC_ATTRIBUTE_KINDS,
    STATIC_OBSERVATION_SCHEMA_VERSION,
    STATIC_QUERY_SCHEMA_VERSION,
    StaticActor,
    StaticAttribute,
    StaticObservation,
    StaticObservationError,
    StaticObservationPackage,
    StaticObservationProvenance,
    StaticQuery,
    UnsupportedStaticSchema,
)

_PACKAGE_FIELDS = frozenset(
    {
        "schemaVersion",
        "runId",
        "collectionId",
        "mediaId",
        "sourceSha256",
        "configHash",
        "pipelineVersion",
        "provenance",
        "observations",
    }
)
_PROVENANCE_FIELDS = frozenset({"sourceNote", "sourcePayloadSha256", "sourcePayloadVersion"})
_OBSERVATION_FIELDS = frozenset({"localObservationId", "evidenceId", "actors"})
_ACTOR_FIELDS = frozenset({"actorId", "attributes"})
_ATTRIBUTE_FIELDS = frozenset({"partGroup", "partId", "kind", "value", "status"})
_QUERY_FIELDS = frozenset({"schemaVersion", "actorAll"})
_QUERY_OPTIONAL_FIELDS = frozenset({"runId", "collectionId"})
_CONDITION_FIELDS = frozenset({"kind", "value", "partGroup"})


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise StaticObservationError("Duplicate JSON field in static declaration.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise StaticObservationError("Non-finite JSON numbers are not valid static declarations.")


def _decode_json(data: object, limit: int) -> dict[str, object]:
    if type(data) is not bytes or len(data) > limit:
        raise StaticObservationError("Static declaration exceeds its bounded JSON size.")
    if data.startswith(b"\xef\xbb\xbf"):
        raise StaticObservationError("Static declarations must be UTF-8 JSON without a BOM.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise StaticObservationError("Static declaration is not valid UTF-8.") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_invalid_constant,
        )
    except (json.JSONDecodeError, RecursionError) as error:
        raise StaticObservationError("Static declaration is not valid bounded JSON.") from error
    if type(value) is not dict:
        raise StaticObservationError("Static declaration must be a JSON object.")
    return cast(dict[str, object], value)


def _object(
    value: object,
    fields: frozenset[str],
    label: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> dict[str, object]:
    if type(value) is not dict:
        raise StaticObservationError(f"Static {label} must be an object.")
    result = cast(dict[str, object], value)
    keys = set(result)
    if not fields <= keys or keys - fields - optional:
        raise StaticObservationError(f"Static {label} has unexpected or missing fields.")
    return result


def _list(value: object, label: str, maximum: int, *, minimum: int = 0) -> list[object]:
    if type(value) is not list:
        raise StaticObservationError(f"Static {label} must be a JSON array.")
    result = cast(list[object], value)
    if not minimum <= len(result) <= maximum:
        raise StaticObservationError(f"Static {label} exceeds its bounded size.")
    return result


def _string(value: object, label: str) -> str:
    if type(value) is not str:
        raise StaticObservationError(f"Static {label} must be a string.")
    return value


def _schema(value: object, supported: str) -> str:
    schema = _string(value, "schemaVersion")
    if schema != supported:
        raise UnsupportedStaticSchema("Unsupported static declaration schema version.")
    return schema


def _kind(value: object) -> AttributeKind:
    kind_value = _string(value, "attribute kind")
    try:
        kind = AttributeKind(kind_value)
    except ValueError as error:
        raise StaticObservationError("Unknown static attribute kind.") from error
    if kind not in STATIC_ATTRIBUTE_KINDS:
        raise StaticObservationError("Only the five static attribute kinds are importable.")
    return kind


def _status(value: object) -> AttributeStatus:
    status_value = _string(value, "attribute status")
    try:
        return AttributeStatus(status_value)
    except ValueError as error:
        raise StaticObservationError("Unknown static attribute status.") from error


def _attribute(value: object) -> StaticAttribute:
    item = _object(value, _ATTRIBUTE_FIELDS, "attribute")
    return StaticAttribute(
        _string(item["partGroup"], "partGroup"),
        _string(item["partId"], "partId"),
        _kind(item["kind"]),
        _string(item["value"], "attribute value"),
        _status(item["status"]),
    )


def _actor(value: object) -> StaticActor:
    item = _object(value, _ACTOR_FIELDS, "actor")
    return StaticActor(
        _string(item["actorId"], "actorId"),
        tuple(
            _attribute(attribute)
            for attribute in _list(
                item["attributes"],
                "actor attributes",
                MAX_STATIC_ACTOR_ATTRIBUTES,
            )
        ),
    )


def _observation(value: object) -> StaticObservation:
    item = _object(value, _OBSERVATION_FIELDS, "observation")
    return StaticObservation(
        _string(item["localObservationId"], "localObservationId"),
        _string(item["evidenceId"], "evidenceId"),
        tuple(
            _actor(actor)
            for actor in _list(
                item["actors"],
                "observation actors",
                MAX_STATIC_OBSERVATION_ACTORS,
            )
        ),
    )


def _provenance(value: object) -> StaticObservationProvenance:
    item = _object(value, _PROVENANCE_FIELDS, "provenance")
    return StaticObservationProvenance(
        _string(item["sourceNote"], "sourceNote"),
        _string(item["sourcePayloadSha256"], "sourcePayloadSha256"),
        _string(item["sourcePayloadVersion"], "sourcePayloadVersion"),
    )


def loads_static_package(data: bytes) -> StaticObservationPackage:
    """Parse one explicit immutable collection package; reject anything not in v1."""
    document = _decode_json(data, MAX_STATIC_PACKAGE_BYTES)
    item = _object(document, _PACKAGE_FIELDS, "package", optional=frozenset({"pipelineHash"}))
    schema = _schema(item["schemaVersion"], STATIC_OBSERVATION_SCHEMA_VERSION)
    observations = tuple(
        _observation(observation)
        for observation in _list(
            item["observations"],
            "observations",
            MAX_STATIC_OBSERVATIONS,
            minimum=1,
        )
    )
    pipeline_hash = (
        _string(item["pipelineHash"], "pipelineHash") if "pipelineHash" in item else None
    )
    return StaticObservationPackage(
        run_id=_string(item["runId"], "runId"),
        collection_id=_string(item["collectionId"], "collectionId"),
        media_id=_string(item["mediaId"], "mediaId"),
        source_sha256=_string(item["sourceSha256"], "sourceSha256"),
        config_hash=_string(item["configHash"], "configHash"),
        pipeline_version=_string(item["pipelineVersion"], "pipelineVersion"),
        provenance=_provenance(item["provenance"]),
        observations=observations,
        pipeline_hash=pipeline_hash,
        schema_version=schema,
    )


def query_schema_version(data: bytes) -> str:
    """Read only the declared schema version so the CLI can select one supported query form."""
    document = _decode_json(data, MAX_STATIC_PACKAGE_BYTES)
    value = document.get("schemaVersion")
    if type(value) is not str:
        raise StaticObservationError("Static query schemaVersion must be a string.")
    return value


def loads_static_query(
    data: bytes,
    *,
    run_id: str | None = None,
    collection_id: str | None = None,
) -> StaticQuery:
    """Parse one explicit typed AND query; action, effect, and environment are refused."""
    document = _decode_json(data, MAX_STATIC_PACKAGE_BYTES)
    item = _object(
        document,
        _QUERY_FIELDS,
        "query",
        optional=_QUERY_OPTIONAL_FIELDS,
    )
    schema = _schema(item["schemaVersion"], STATIC_QUERY_SCHEMA_VERSION)
    scoped_run = _string(item["runId"], "runId") if "runId" in item else run_id
    scoped_collection = (
        _string(item["collectionId"], "collectionId") if "collectionId" in item else collection_id
    )
    if scoped_run is None or scoped_collection is None:
        raise StaticObservationError("Static query needs explicit run and collection scope.")
    conditions = []
    for value in _list(
        item["actorAll"],
        "query conditions",
        MAX_QUERY_CONDITIONS,
        minimum=1,
    ):
        condition = _object(value, _CONDITION_FIELDS, "query condition")
        kind = _kind(condition["kind"])
        conditions.append(
            AttributeConstraint(
                kind,
                _string(condition["value"], "query value"),
                _string(condition["partGroup"], "query partGroup"),
            )
        )
    constraint = QueryConstraint(
        tuple(conditions),
        (),
        QUERY_SCHEMA_VERSION,
        QUERY_VERSION,
        DETAIL_VOCABULARY_VERSION,
    )
    return StaticQuery(
        scoped_run,
        scoped_collection,
        constraint,
        schema,
    )
