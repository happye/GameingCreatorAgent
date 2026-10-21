"""Explicit query manifests and evidence reports. No free-text constraint inference or I/O."""

import hashlib
import re
import json
from dataclasses import asdict, replace

from gamingcreator.application.actor_detail_matching import match_actor_details
from gamingcreator.application.detail_refinement import (
    REFINEMENT_TEMPORAL_SCHEMA_VERSION,
    DetailRefinementRequest,
)
from gamingcreator.application.detail_refinement_budget import payload_hash
from gamingcreator.domain.actor_details import (
    DETAIL_SCHEMA_VERSION,
    DETAIL_TEMPORAL_SCHEMA_VERSION,
    DETAIL_VOCABULARY_VERSION,
    DETAIL_TEMPORAL_SCHEMA_VERSION,
    DETAIL_VOCABULARY_VERSION,
    MATCHER_VERSION,
    QUERY_SCHEMA_VERSION,
    QUERY_VERSION,
    TEMPORAL_MATCHER_VERSION,
    AttributeConstraint,
    AttributeKind,
    CandidateDetail,
    MatchStatus,
    QueryConstraint,
    attribute_value_options,
    canonical_constraint_json,
    constraint_hash,
)

MATCH_REPORT_VERSION = "actor-detail-match-report-v1.1"
MAX_MANIFEST_BYTES = 1_048_576
MATCH_REPORT_INERT_VERSION = "match-report-inert-v1"
REQUIRED_MATCH_REPORT_KEYS = frozenset(
    {
        "schemaVersion",
        "runId",
        "eventId",
        "candidateId",
        "sourceRange",
        "eventFingerprint",
        "refinementRequestHash",
        "refinementPayloadHash",
        "constraintJson",
        "constraintHash",
        "result",
        "humanLabels",
        "qualityGate",
        "inertContract",
        "independentStaticClothingIndex",
    }
)


def build_match_report_inert_contract() -> dict[str, object]:
    """Machine-readable rules: match reports never auto-pass or invent static indexes."""
    return {
        "schemaVersion": MATCH_REPORT_INERT_VERSION,
        "humanLabelsMustBeNull": True,
        "qualityGateMustBeNull": True,
        "forbiddenQualityGateValues": [True, "passed", "pass", "已通过", "通过"],
        "independentStaticClothingIndex": False,
        "notes": (
            "humanLabels/qualityGate stay null until explicit human review; "
            "static clothing is candidate-bound only — no independent static event index."
        ),
    }


_HASH64 = re.compile(r"[0-9a-f]{64}\Z")
MATCH_REPORT_FORBIDDEN_CLAIM_KEYS = (
    "formalAcceptancePassed",
    "acceptanceStatus",
    "humanEvalPassed",
    "f006Passed",
    "f009Passed",
    "f010Passed",
)
_MATCH_REPORT_STATUSES = frozenset(status.value for status in MatchStatus)


def _valid_optional_hash64(value: object) -> bool:
    return value is None or (type(value) is str and bool(_HASH64.fullmatch(value)))


def _valid_optional_source_range(value: object) -> bool:
    if value is None:
        return True
    if type(value) is not dict:
        return False
    start_us = value.get("startUs")
    end_us = value.get("endUs")
    duration_us = value.get("durationUs")
    if type(start_us) is not int or type(end_us) is not int or type(duration_us) is not int:
        return False
    return 0 <= start_us < end_us <= duration_us



_MATCH_EVIDENCE_BUCKETS = ("satisfied", "opposed", "counterEvidence", "uncertain")


def _match_evidence_ids_owned(run_id: str, evidence_ids: object) -> bool:
    if type(evidence_ids) is not list:
        return False
    for evidence_id in evidence_ids:
        if type(evidence_id) is not str or not evidence_id:
            return False
        if ":" in evidence_id and not evidence_id.startswith(f"{run_id}:"):
            return False
    return True



def _source_range_contains(outer: object, inner: object) -> bool:
    """True when inner is null, outer is unbound, or inner sits inside outer (same durationUs)."""
    if inner is None or outer is None:
        return True
    if not _valid_optional_source_range(outer):
        return False
    if not _valid_optional_source_range(inner):
        return False
    assert type(outer) is dict and type(inner) is dict
    return (
        int(outer["startUs"]) <= int(inner["startUs"]) < int(inner["endUs"]) <= int(outer["endUs"])
        and int(inner["durationUs"]) == int(outer["durationUs"])
    )


def assert_match_report_contract(document: dict[str, object]) -> None:
    """Refuse match reports that claim human pass or open a static clothing index."""
    missing = REQUIRED_MATCH_REPORT_KEYS - set(document)
    if missing:
        raise ValueError(f"Match report missing fields: {sorted(missing)}")
    if document.get("schemaVersion") != MATCH_REPORT_VERSION:
        raise ValueError("Match report schemaVersion mismatch.")
    if document.get("humanLabels") is not None:
        raise ValueError("humanLabels must stay null on offline match reports.")
    gate = document.get("qualityGate")
    if gate is not None:
        raise ValueError("qualityGate must stay null on offline match reports.")
    if document.get("independentStaticClothingIndex") is not False:
        raise ValueError("independentStaticClothingIndex must stay False.")
    contract = document.get("inertContract")
    expected = build_match_report_inert_contract()
    if contract != expected:
        raise ValueError("Match report inertContract mismatch.")
    for key in MATCH_REPORT_FORBIDDEN_CLAIM_KEYS:
        if key in document and document.get(key) is not None:
            raise ValueError(f"{key} must stay absent/null on offline match reports.")
    run_id = document.get("runId")
    if type(run_id) is not str or not run_id:
        raise ValueError("Match report runId must be a non-empty string.")
    event_id = document.get("eventId")
    if type(event_id) is not str or not event_id:
        raise ValueError("Match report eventId must be a non-empty string.")
    if ":" in event_id and not event_id.startswith(f"{run_id}:"):
        raise ValueError("Match report eventId does not belong to runId.")
    candidate_id = document.get("candidateId")
    if candidate_id is not None and (type(candidate_id) is not str or not candidate_id):
        raise ValueError("Match report candidateId must be null or a non-empty string.")
    fingerprint = document.get("eventFingerprint")
    if not _valid_optional_hash64(fingerprint):
        raise ValueError("Match report eventFingerprint must be null or sha256 hex.")
    if not _valid_optional_source_range(document.get("sourceRange")):
        raise ValueError("Match report sourceRange is invalid.")
    if not _valid_optional_hash64(document.get("refinementRequestHash")):
        raise ValueError("Match report refinementRequestHash must be null or sha256 hex.")
    if not _valid_optional_hash64(document.get("refinementPayloadHash")):
        raise ValueError("Match report refinementPayloadHash must be null or sha256 hex.")
    result = document.get("result")
    if not isinstance(result, dict) or "status" not in result or "matcherVersion" not in result:
        raise ValueError("Match report result must expose status and matcherVersion.")
    status = result.get("status")
    if status not in _MATCH_REPORT_STATUSES:
        raise ValueError("Match report result.status is invalid.")
    matcher = result.get("matcherVersion")
    if matcher not in {MATCHER_VERSION, TEMPORAL_MATCHER_VERSION}:
        raise ValueError("Match report result.matcherVersion is invalid.")
    if result.get("constraintHash") != document.get("constraintHash"):
        raise ValueError("Match report result.constraintHash must match constraintHash.")
    constraint_json = document.get("constraintJson")
    constraint_digest = document.get("constraintHash")
    if type(constraint_json) is not str or type(constraint_digest) is not str:
        raise ValueError("constraintJson/constraintHash must be strings.")
    if constraint_digest != hashlib.sha256(constraint_json.encode("utf-8")).hexdigest():
        raise ValueError("constraintHash must digest constraintJson.")
    try:
        constraint_payload = json.loads(constraint_json)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("constraintJson must be JSON object.") from exc
    if type(constraint_payload) is not dict:
        raise ValueError("constraintJson must be JSON object.")
    for key in ("schemaVersion", "version", "vocabularyVersion"):
        value = constraint_payload.get(key)
        if type(value) is not str or not value:
            raise ValueError(f"constraintJson.{key} is invalid.")
    result_schema = result.get("schemaVersion")
    if result_schema not in {DETAIL_SCHEMA_VERSION, DETAIL_TEMPORAL_SCHEMA_VERSION}:
        raise ValueError("Match report result.schemaVersion is invalid.")
    if result.get("querySchemaVersion") != QUERY_SCHEMA_VERSION:
        raise ValueError("Match report result.querySchemaVersion is invalid.")
    if result.get("queryVersion") != QUERY_VERSION:
        raise ValueError("Match report result.queryVersion is invalid.")
    if result.get("vocabularyVersion") != DETAIL_VOCABULARY_VERSION:
        raise ValueError("Match report result.vocabularyVersion is invalid.")
    notes = result.get("notes")
    if notes is not None:
        if type(notes) is not list or any(type(item) is not str for item in notes):
            raise ValueError("Match report result.notes must be a string list.")
    matches = result.get("matches")
    if type(matches) is not list:
        raise ValueError("Match report result.matches must be a list.")
    assert type(run_id) is str
    for row in matches:
        if type(row) is not dict:
            raise ValueError("Match report match row must be an object.")
        actor_id = row.get("actorId")
        if type(actor_id) is not str or not actor_id:
            raise ValueError("Match report match actorId is invalid.")
        shot_id = row.get("shotId")
        if type(shot_id) is not str or not shot_id:
            raise ValueError("Match report match shotId is invalid.")
        if not _valid_optional_source_range(row.get("sourceRange")):
            raise ValueError("Match report match sourceRange is invalid.")
        shared = row.get("sharedEvidenceIds")
        if shared is None:
            shared = []
        if not _match_evidence_ids_owned(run_id, shared):
            raise ValueError("Match report sharedEvidenceIds are invalid.")
        for bucket in _MATCH_EVIDENCE_BUCKETS:
            entries = row.get(bucket)
            if entries is None:
                continue
            if type(entries) is not list:
                raise ValueError(f"Match report match.{bucket} must be a list.")
            for entry in entries:
                if type(entry) is not dict:
                    raise ValueError(f"Match report match.{bucket} entry must be an object.")
                evidence_ids = entry.get("evidenceIds")
                if evidence_ids is None:
                    evidence_ids = []
                if not _match_evidence_ids_owned(run_id, evidence_ids):
                    raise ValueError(f"Match report match.{bucket} evidenceIds are invalid.")
                if "sourceRange" in entry and not _valid_optional_source_range(entry.get("sourceRange")):
                    raise ValueError(f"Match report match.{bucket} sourceRange is invalid.")
                if not _source_range_contains(document.get("sourceRange"), entry.get("sourceRange")):
                    raise ValueError(f"Match report match.{bucket} sourceRange escapes report range.")
        if not _source_range_contains(document.get("sourceRange"), row.get("sourceRange")):
            raise ValueError("Match report match sourceRange escapes report range.")


def assert_match_report_sidecar_binding_contract(
    report: dict[str, object],
    request_document: dict[str, object],
    result_document: dict[str, object] | None = None,
) -> None:
    """Readonly对照：match-report 身份／区间／证据必须挂回精分析 request／result 侧车.

    Does not claim human-eval / F010 / TD009 closeout. Legacy v1 reports may bind.
    """
    if type(report) is not dict or type(request_document) is not dict:
        raise ValueError("Match report sidecar binding requires objects.")
    request_hash = report.get("refinementRequestHash")
    if type(request_hash) is not str or not _HASH64.fullmatch(request_hash):
        raise ValueError("Match report refinementRequestHash is invalid.")
    if request_document.get("requestHash") != request_hash:
        raise ValueError("Match report requestHash does not match sidecar request.")
    if request_document.get("runId") != report.get("runId"):
        raise ValueError("Match report runId does not match sidecar request.")
    if request_document.get("eventFingerprint") != report.get("eventFingerprint"):
        raise ValueError("Match report eventFingerprint does not match sidecar request.")
    canonical = request_document.get("canonicalJson")
    if type(canonical) is not str or not canonical:
        raise ValueError("Sidecar request canonicalJson is invalid.")
    try:
        payload = json.loads(canonical)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Sidecar request canonicalJson must be JSON object.") from exc
    if type(payload) is not dict:
        raise ValueError("Sidecar request canonicalJson must be JSON object.")
    if payload.get("candidateId") != report.get("candidateId"):
        raise ValueError("Match report candidateId does not match sidecar request.")
    if payload.get("interval") != report.get("sourceRange"):
        raise ValueError("Match report sourceRange does not match sidecar interval.")
    media_sha = payload.get("mediaSha256")
    run_id = report.get("runId")
    event_id = report.get("eventId")
    if type(media_sha) is not str or not _HASH64.fullmatch(media_sha):
        raise ValueError("Sidecar request mediaSha256 is invalid.")
    if type(run_id) is not str or not run_id or type(event_id) is not str or not event_id:
        raise ValueError("Match report runId/eventId invalid for sidecar binding.")
    if not event_id.startswith(f"{run_id}:{media_sha}:"):
        raise ValueError("Match report eventId does not match sidecar mediaSha256.")
    evidence_rows = payload.get("evidence")
    if type(evidence_rows) is not list or not evidence_rows:
        raise ValueError("Sidecar request evidence is invalid.")
    allowed_evidence = {
        row.get("evidenceId")
        for row in evidence_rows
        if type(row) is dict and type(row.get("evidenceId")) is str
    }
    result = report.get("result")
    if not isinstance(result, dict):
        raise ValueError("Match report result must be an object for sidecar binding.")
    matches = result.get("matches")
    if type(matches) is not list:
        raise ValueError("Match report matches must be a list for sidecar binding.")
    outer_range = report.get("sourceRange")
    for row in matches:
        if type(row) is not dict:
            raise ValueError("Match report match row invalid for sidecar binding.")
        if not _source_range_contains(outer_range, row.get("sourceRange")):
            raise ValueError("Match report match sourceRange escapes report/sidecar range.")
        shared = row.get("sharedEvidenceIds") or []
        if not _match_evidence_ids_owned(run_id, shared):
            raise ValueError("Match report sharedEvidenceIds invalid for sidecar binding.")
        if not set(shared) <= allowed_evidence:
            raise ValueError("Match report sharedEvidenceIds not in sidecar evidence.")
        for bucket in _MATCH_EVIDENCE_BUCKETS:
            entries = row.get(bucket) or []
            if type(entries) is not list:
                raise ValueError(f"Match report match.{bucket} invalid for sidecar binding.")
            for entry in entries:
                if type(entry) is not dict:
                    raise ValueError(f"Match report match.{bucket} entry invalid for sidecar binding.")
                evidence_ids = entry.get("evidenceIds") or []
                if not _match_evidence_ids_owned(run_id, evidence_ids):
                    raise ValueError(
                        f"Match report match.{bucket} evidenceIds invalid for sidecar binding."
                    )
                if not set(evidence_ids) <= allowed_evidence:
                    raise ValueError(
                        f"Match report match.{bucket} evidenceIds not in sidecar evidence."
                    )
                if not _source_range_contains(outer_range, entry.get("sourceRange")):
                    raise ValueError(
                        f"Match report match.{bucket} sourceRange escapes report range."
                    )
    if result_document is not None:
        if type(result_document) is not dict:
            raise ValueError("Sidecar result must be an object.")
        payload_hash = report.get("refinementPayloadHash")
        if type(payload_hash) is not str or not _HASH64.fullmatch(payload_hash):
            raise ValueError("Match report refinementPayloadHash is invalid.")
        if result_document.get("payloadHash") != payload_hash:
            raise ValueError("Match report payloadHash does not match sidecar result.")
        if result_document.get("requestHash") != request_hash:
            raise ValueError("Sidecar result requestHash does not match match report.")


def match_report_contract_gaps(document: dict[str, object]) -> tuple[str, ...]:
    """Stable offline gap codes when a saved match report is not current v1.1 contract.

    Does not claim human-eval / F010 / TD009 closeout. Used for readonly对照 against
    legacy on-disk reports (e.g. actor-detail-match-report-v1 + matcher-v1).
    """
    if not isinstance(document, dict):
        return ("not_object",)
    gaps: list[str] = []
    schema = document.get("schemaVersion")
    if schema != MATCH_REPORT_VERSION:
        gaps.append("schema_version_mismatch")
    missing = REQUIRED_MATCH_REPORT_KEYS - set(document)
    for key in sorted(missing):
        gaps.append(f"missing:{key}")
    if document.get("humanLabels") is not None:
        gaps.append("human_labels_not_null")
    if document.get("qualityGate") is not None:
        gaps.append("quality_gate_not_null")
    for key in MATCH_REPORT_FORBIDDEN_CLAIM_KEYS:
        if key in document and document.get(key) is not None:
            gaps.append(f"forbidden_claim:{key}")
    if (
        "independentStaticClothingIndex" in document
        and document.get("independentStaticClothingIndex") is not False
    ):
        gaps.append("static_clothing_index_enabled")
    if "inertContract" in document and document.get("inertContract") != build_match_report_inert_contract():
        gaps.append("inert_contract_mismatch")
    run_id = document.get("runId")
    event_id = document.get("eventId")
    if type(run_id) is not str or not run_id:
        gaps.append("run_id_invalid")
    if type(event_id) is not str or not event_id:
        gaps.append("event_id_invalid")
    elif type(run_id) is str and ":" in event_id and not event_id.startswith(f"{run_id}:"):
        gaps.append("event_run_mismatch")
    candidate_id = document.get("candidateId")
    if candidate_id is not None and (type(candidate_id) is not str or not candidate_id):
        gaps.append("candidate_id_invalid")
    if "eventFingerprint" in document and not _valid_optional_hash64(document.get("eventFingerprint")):
        gaps.append("event_fingerprint_invalid")
    if "sourceRange" in document and not _valid_optional_source_range(document.get("sourceRange")):
        gaps.append("source_range_invalid")
    if "refinementRequestHash" in document and not _valid_optional_hash64(
        document.get("refinementRequestHash")
    ):
        gaps.append("refinement_request_hash_invalid")
    if "refinementPayloadHash" in document and not _valid_optional_hash64(
        document.get("refinementPayloadHash")
    ):
        gaps.append("refinement_payload_hash_invalid")
    result = document.get("result")
    if not isinstance(result, dict):
        gaps.append("result_not_object")
    else:
        if "status" not in result:
            gaps.append("result_missing_status")
        elif result.get("status") not in _MATCH_REPORT_STATUSES:
            gaps.append("result_status_invalid")
        if "matcherVersion" not in result:
            gaps.append("result_missing_matcher_version")
        else:
            matcher = result.get("matcherVersion")
            if matcher not in {MATCHER_VERSION, TEMPORAL_MATCHER_VERSION}:
                gaps.append("matcher_version_mismatch")
        if (
            "constraintHash" in result
            and "constraintHash" in document
            and result.get("constraintHash") != document.get("constraintHash")
        ):
            gaps.append("result_constraint_hash_mismatch")
    constraint_json = document.get("constraintJson")
    constraint_digest = document.get("constraintHash")
    if "constraintHash" in document or "constraintJson" in document:
        if type(constraint_json) is not str or type(constraint_digest) is not str:
            gaps.append("constraint_hash_type")
        elif constraint_digest != hashlib.sha256(constraint_json.encode("utf-8")).hexdigest():
            gaps.append("constraint_hash_mismatch")
        elif type(constraint_json) is str:
            try:
                constraint_payload = json.loads(constraint_json)
            except (TypeError, ValueError, RecursionError):
                gaps.append("constraint_json_invalid")
                constraint_payload = None
            if type(constraint_payload) is dict:
                for key in ("schemaVersion", "version", "vocabularyVersion"):
                    value = constraint_payload.get(key)
                    if type(value) is not str or not value:
                        gaps.append(f"constraint_missing:{key}")
            elif constraint_payload is not None:
                gaps.append("constraint_json_invalid")
    if isinstance(result, dict):
        result_schema = result.get("schemaVersion")
        if (
            "schemaVersion" in result
            and result_schema not in {DETAIL_SCHEMA_VERSION, DETAIL_TEMPORAL_SCHEMA_VERSION}
        ):
            gaps.append("result_schema_version_invalid")
        if (
            "querySchemaVersion" in result
            and result.get("querySchemaVersion") != QUERY_SCHEMA_VERSION
        ):
            gaps.append("query_schema_version_mismatch")
        if "queryVersion" in result and result.get("queryVersion") != QUERY_VERSION:
            gaps.append("query_version_mismatch")
        if (
            "vocabularyVersion" in result
            and result.get("vocabularyVersion") != DETAIL_VOCABULARY_VERSION
        ):
            gaps.append("vocabulary_version_mismatch")
        notes = result.get("notes")
        if notes is not None and (
            type(notes) is not list or any(type(item) is not str for item in notes)
        ):
            gaps.append("notes_invalid")
        matches = result.get("matches")
        if "matches" in result and type(matches) is not list:
            gaps.append("matches_not_list")
        elif type(matches) is list and type(run_id) is str and run_id:
            for row in matches:
                if type(row) is not dict:
                    gaps.append("match_row_invalid")
                    continue
                if type(row.get("actorId")) is not str or not row.get("actorId"):
                    gaps.append("match_actor_id_invalid")
                if type(row.get("shotId")) is not str or not row.get("shotId"):
                    gaps.append("match_shot_id_invalid")
                if "sourceRange" in row and not _valid_optional_source_range(row.get("sourceRange")):
                    gaps.append("match_source_range_invalid")
                shared = row.get("sharedEvidenceIds")
                if shared is not None and not _match_evidence_ids_owned(run_id, shared):
                    gaps.append("match_shared_evidence_invalid")
                for bucket in _MATCH_EVIDENCE_BUCKETS:
                    entries = row.get(bucket)
                    if entries is None:
                        continue
                    if type(entries) is not list:
                        gaps.append(f"match_{bucket}_invalid")
                        continue
                    for entry in entries:
                        if type(entry) is not dict:
                            gaps.append(f"match_{bucket}_entry_invalid")
                            continue
                        evidence_ids = entry.get("evidenceIds")
                        if evidence_ids is not None and not _match_evidence_ids_owned(
                            run_id, evidence_ids
                        ):
                            gaps.append(f"match_{bucket}_evidence_invalid")
                        if "sourceRange" in entry and not _valid_optional_source_range(
                            entry.get("sourceRange")
                        ):
                            gaps.append(f"match_{bucket}_range_invalid")
    return tuple(gaps)




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
    result = match_actor_details(detail, constraint)
    if (
        request is not None
        and request.identity.schema_version == REFINEMENT_TEMPORAL_SCHEMA_VERSION
    ):
        result = replace(
            result,
            schema_version=DETAIL_TEMPORAL_SCHEMA_VERSION,
            matcher_version=TEMPORAL_MATCHER_VERSION,
        )
    document: dict[str, object] = {
        "schemaVersion": MATCH_REPORT_VERSION,
        "runId": run_id,
        "eventId": event_id,
        "candidateId": None if request is None else request.candidate_id,
        "sourceRange": None if request is None else _camel_payload(asdict(request.source_range)),
        "eventFingerprint": None if request is None else request.event_fingerprint,
        "refinementRequestHash": request_digest,
        "refinementPayloadHash": None if detail is None else payload_hash(detail),
        "constraintJson": canonical_constraint_json(constraint),
        "constraintHash": constraint_hash(constraint),
        "result": _camel_payload(asdict(result)),
        "humanLabels": None,
        "qualityGate": None,
        "independentStaticClothingIndex": False,
        "inertContract": build_match_report_inert_contract(),
    }
    assert_match_report_contract(document)
    return document
