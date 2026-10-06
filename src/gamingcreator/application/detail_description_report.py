"""Pure validation of the frozen report behind description-only human feedback."""

import hashlib
import json
import re

from gamingcreator.application.detail_description_feedback import (
    MAX_FEEDBACK_BYTES,
    MAX_FEEDBACK_CASES,
    DescriptionFeedback,
)
from gamingcreator.domain.actor_details import MAX_DETAIL_SHOTS, MAX_SHOT_ACTORS

DESCRIPTION_REPORT_SCHEMA_VERSION = "actor-detail-pilot-report-v1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate description report JSON field.")
        value[key] = item
    return value


def _nonfinite(value: str) -> None:
    raise ValueError("Non-finite description report JSON numbers are invalid.")


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("Description report requires correctly typed JSON objects.")
    return value


def _string_field(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if type(item) is not str:
        raise ValueError("Missing or incorrectly typed description report field.")
    return item


def _identifier(value: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid description report local identity.")


def _hash(value: str) -> None:
    if not _HASH.fullmatch(value):
        raise ValueError("Description report requires lowercase SHA-256 identities.")


def _list(value: object, maximum: int) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        raise ValueError("Invalid bounded description report list.")
    return value


def _document(text: object) -> tuple[dict[str, object], bytes]:
    if type(text) is not str:
        raise ValueError("Description report requires JSON text.")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Description report requires valid Unicode.") from None
    if len(encoded) > MAX_FEEDBACK_BYTES:
        raise ValueError("Description report exceeds its byte limit.")
    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (RecursionError, json.JSONDecodeError):
        raise ValueError("Invalid description report JSON.") from None
    return _object(document), encoded


def _targets(payload: dict[str, object]) -> set[str]:
    targets: set[str] = set()
    shot_ids: set[str] = set()
    for raw in _list(payload.get("shots"), MAX_DETAIL_SHOTS):
        shot = _object(raw)
        shot_id = _string_field(shot, "shotId")
        _identifier(shot_id)
        if shot_id in shot_ids:
            raise ValueError("Duplicate description report shot identity.")
        shot_ids.add(shot_id)
        for raw_actor in _list(shot.get("actors"), MAX_SHOT_ACTORS):
            actor = _object(raw_actor)
            actor_id = _string_field(actor, "actorId")
            _identifier(actor_id)
            if _string_field(actor, "shotId") != shot_id:
                raise ValueError("Description report actor belongs to another shot.")
            target = f"{shot_id}/{actor_id}"
            if target in targets:
                raise ValueError("Duplicate description report actor target.")
            targets.add(target)
    return targets


def validate_description_report(feedback: DescriptionFeedback, report_text: str) -> None:
    """Confirm each judgment belongs to a completed exact case in its frozen report."""
    if type(feedback) is not DescriptionFeedback:
        raise ValueError("Description report validation requires typed feedback.")
    report, encoded = _document(report_text)
    if hashlib.sha256(encoded).hexdigest() != feedback.pilot_report_sha256:
        raise ValueError("Description feedback pilot report SHA-256 mismatch.")
    if _string_field(report, "schemaVersion") != DESCRIPTION_REPORT_SCHEMA_VERSION:
        raise ValueError("Unsupported description report schema.")
    cases: dict[str, dict[str, object]] = {}
    for raw in _list(report.get("cases"), MAX_FEEDBACK_CASES):
        case = _object(raw)
        case_id = _string_field(case, "caseId")
        run_id = _string_field(case, "runId")
        event_id = _string_field(case, "eventId")
        _identifier(case_id)
        _identifier(run_id)
        _hash(_string_field(case, "requestHash"))
        if not re.fullmatch(
            re.escape(run_id) + r":[A-Za-z0-9_-]{1,128}:event:[0-9a-f]{24}", event_id
        ):
            raise ValueError("Description report event belongs to another run.")
        _object(case.get("attempt"))
        if case_id in cases:
            raise ValueError("Duplicate description report case identity.")
        cases[case_id] = case
    for judgment in feedback.cases:
        matched_case = cases.get(judgment.case_id)
        if matched_case is None:
            raise ValueError("Description feedback case is missing from its report.")
        if (matched_case["runId"], matched_case["eventId"], matched_case["requestHash"]) != (
            judgment.run_id,
            judgment.event_id,
            judgment.request_hash,
        ):
            raise ValueError("Description feedback case identity differs from its report.")
        attempt = _object(matched_case["attempt"])
        if (
            _string_field(attempt, "status") != "completed"
            or _string_field(attempt, "requestHash") != judgment.request_hash
            or _string_field(attempt, "payloadHash") != judgment.refinement_payload_hash
        ):
            raise ValueError("Description feedback requires the exact completed report attempt.")
        payload, payload_bytes = _document(_string_field(attempt, "payloadJson"))
        if hashlib.sha256(payload_bytes).hexdigest() != judgment.refinement_payload_hash:
            raise ValueError("Description report payload SHA-256 mismatch.")
        if (_string_field(payload, "runId"), _string_field(payload, "eventId")) != (
            judgment.run_id,
            judgment.event_id,
        ):
            raise ValueError("Description report payload belongs to another candidate.")
        if not set(judgment.target_actor_ids).issubset(_targets(payload)):
            raise ValueError("Description feedback target is missing from its report payload.")
