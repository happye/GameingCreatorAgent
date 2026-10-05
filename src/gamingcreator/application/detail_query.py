"""Explicit query manifests and evidence reports. No free-text constraint inference or I/O."""

import json
from dataclasses import asdict

from gamingcreator.application.actor_detail_matching import match_actor_details
from gamingcreator.application.detail_refinement import DetailRefinementRequest
from gamingcreator.application.detail_refinement_budget import payload_hash
from gamingcreator.domain.actor_details import (
    DETAIL_VOCABULARY_VERSION,
    QUERY_SCHEMA_VERSION,
    QUERY_VERSION,
    AttributeConstraint,
    AttributeKind,
    CandidateDetail,
    QueryConstraint,
    attribute_value_options,
    canonical_constraint_json,
)

MATCH_REPORT_VERSION = "actor-detail-match-report-v1"
MAX_MANIFEST_BYTES = 1_048_576


def query_options() -> dict[str, object]:
    labels = {
        AttributeKind.HAIR_COLOR: "发色",
        AttributeKind.CLOTHING_COLOR: "衣物颜色",
        AttributeKind.CLOTHING_SHAPE: "衣物形状",
        AttributeKind.HELD_SHAPE: "持有物形状",
        AttributeKind.HELD_CLASS: "持有物类别",
        AttributeKind.ACTION: "动作",
        AttributeKind.EFFECT: "效果",
        AttributeKind.ENVIRONMENT: "环境",
    }
    return {
        "schemaVersion": QUERY_SCHEMA_VERSION,
        "version": QUERY_VERSION,
        "vocabularyVersion": DETAIL_VOCABULARY_VERSION,
        "maxConditions": 16,
        "kinds": [
            {
                "kind": kind.value,
                "label": labels[kind],
                "values": [
                    {"value": value, "label": label}
                    for value, label in attribute_value_options(kind)
                ],
            }
            for kind in AttributeKind
        ],
    }


def loads_constraint(text: str) -> QueryConstraint:
    if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ValueError("Query manifest exceeds 1MiB.")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate query field.")
            value[key] = item
        return value

    def conditions(value: object) -> tuple[AttributeConstraint, ...]:
        if type(value) is not list or len(value) > 16:
            raise ValueError("Invalid bounded query conditions.")
        entries = []
        for item in value:
            if (
                type(item) is not dict
                or set(item) != {"kind", "value", "partGroup"}
                or any(type(part) is not str for part in item.values())
            ):
                raise ValueError("Invalid query condition fields.")
            entries.append(
                AttributeConstraint(AttributeKind(item["kind"]), item["value"], item["partGroup"])
            )
        return tuple(entries)

    try:
        value = json.loads(text, object_pairs_hook=unique)
        if type(value) is not dict or set(value) != {
            "schemaVersion",
            "version",
            "vocabularyVersion",
            "actorAll",
            "environmentAll",
        }:
            raise ValueError("Unexpected query manifest fields.")
        return QueryConstraint(
            conditions(value["actorAll"]),
            conditions(value["environmentAll"]),
            value["schemaVersion"],
            value["version"],
            value["vocabularyVersion"],
        )
    except (KeyError, TypeError, RecursionError) as error:
        raise ValueError("Invalid query manifest.") from error


def _camel_payload(value: object) -> object:
    if isinstance(value, dict):

        def camel(key: str) -> str:
            first, *rest = key.split("_")
            return first + "".join(item.title() for item in rest)

        return {camel(key): _camel_payload(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_camel_payload(item) for item in value]
    return value


def match_report(
    request: DetailRefinementRequest | None,
    detail: CandidateDetail | None,
    constraint: QueryConstraint,
    *,
    run_id: str,
    event_id: str,
    request_digest: str | None,
) -> dict[str, object]:
    return {
        "schemaVersion": MATCH_REPORT_VERSION,
        "runId": run_id,
        "eventId": event_id,
        "candidateId": None if request is None else request.candidate_id,
        "sourceRange": None if request is None else _camel_payload(asdict(request.source_range)),
        "eventFingerprint": None if request is None else request.event_fingerprint,
        "refinementRequestHash": request_digest,
        "refinementPayloadHash": None if detail is None else payload_hash(detail),
        "constraintJson": canonical_constraint_json(constraint),
        "result": _camel_payload(asdict(match_actor_details(detail, constraint))),
        "humanLabels": None,
        "qualityGate": None,
    }
