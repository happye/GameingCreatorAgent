"""Strict description-only human feedback decoding and exact-result projection; no I/O."""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal, cast

from gamingcreator.application.detail_refinement_budget import payload_hash
from gamingcreator.domain.actor_details import CandidateDetail

FEEDBACK_SCHEMA_VERSION = "detail-pilot-human-feedback-v1"
FEEDBACK_SCOPE = "actor-description"
FEEDBACK_SOURCE = "direct-project-user-feedback"
MAX_FEEDBACK_BYTES = 1_048_576
MAX_FEEDBACK_CASES = 128
MAX_CASE_TARGETS = 8
MAX_FEEDBACK_STATEMENT_CHARACTERS = 2048

_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TARGET = re.compile(r"([A-Za-z0-9_-]{1,128})/([A-Za-z0-9_-]{1,128})\Z")
_ROOT_FIELDS = {
    "schemaVersion",
    "recordedOn",
    "pilotReportSha256",
    "cases",
    "unmentionedEntries",
    "phase0QualityGate",
    "newProviderCalls",
}
_CASE_FIELDS = {
    "caseId",
    "runId",
    "eventId",
    "requestHash",
    "refinementPayloadHash",
    "scope",
    "targetActorIds",
    "verdict",
    "source",
    "statement",
}
DescriptionVerdict = Literal["accepted", "rejected"]


def _string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("Description feedback requires correctly typed strings.")
    return value


def _identifier(value: object) -> None:
    if not _IDENTIFIER.fullmatch(_string(value)):
        raise ValueError("Invalid description feedback identity.")


def _hash(value: object) -> None:
    if not _HASH.fullmatch(_string(value)):
        raise ValueError("Description feedback requires lowercase SHA-256 identities.")


def _event(run_id: str, event_id: str) -> None:
    _identifier(run_id)
    if not re.fullmatch(
        re.escape(run_id) + r":[A-Za-z0-9_-]{1,128}:event:[0-9a-f]{24}", _string(event_id)
    ):
        raise ValueError("Description feedback event must belong to its stated run.")


def _constant(value: object, expected: str) -> None:
    if _string(value) != expected:
        raise ValueError("Unsupported description feedback schema, scope, source or policy.")


@dataclass(frozen=True, slots=True)
class DescriptionFeedbackCase:
    case_id: str
    run_id: str
    event_id: str
    request_hash: str
    refinement_payload_hash: str
    scope: str
    target_actor_ids: tuple[str, ...]
    verdict: DescriptionVerdict
    source: str
    statement: str

    def __post_init__(self) -> None:
        _identifier(self.case_id)
        _event(self.run_id, self.event_id)
        _hash(self.request_hash)
        _hash(self.refinement_payload_hash)
        _constant(self.scope, FEEDBACK_SCOPE)
        _constant(self.source, FEEDBACK_SOURCE)
        if type(self.verdict) is not str or self.verdict not in ("accepted", "rejected"):
            raise ValueError("Description feedback verdict must be accepted or rejected.")
        if (
            type(self.target_actor_ids) is not tuple
            or not 1 <= len(self.target_actor_ids) <= MAX_CASE_TARGETS
            or any(not _TARGET.fullmatch(_string(target)) for target in self.target_actor_ids)
            or len(set(self.target_actor_ids)) != len(self.target_actor_ids)
        ):
            raise ValueError("Description feedback needs unique bounded shot/actor targets.")
        statement = _string(self.statement)
        if not statement.strip() or len(statement) > MAX_FEEDBACK_STATEMENT_CHARACTERS:
            raise ValueError("Description feedback statement must be nonempty and bounded.")
        try:
            statement.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Description feedback statement requires valid Unicode.") from None


@dataclass(frozen=True, slots=True)
class DescriptionFeedback:
    schema_version: str
    recorded_on: str
    pilot_report_sha256: str
    cases: tuple[DescriptionFeedbackCase, ...]
    unmentioned_entries: str
    phase0_quality_gate: None
    new_provider_calls: int

    def __post_init__(self) -> None:
        _constant(self.schema_version, FEEDBACK_SCHEMA_VERSION)
        _hash(self.pilot_report_sha256)
        _constant(self.unmentioned_entries, "unreviewed")
        recorded_on = _string(self.recorded_on)
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", recorded_on):
            raise ValueError("Description feedback recordedOn must be an ISO calendar date.")
        try:
            date.fromisoformat(recorded_on)
        except ValueError:
            raise ValueError("Description feedback recordedOn is not a calendar date.") from None
        if (
            self.phase0_quality_gate is not None
            or type(self.new_provider_calls) is not int
            or self.new_provider_calls != 0
        ):
            raise ValueError("Description feedback cannot pass a quality gate or call a provider.")
        if (
            type(self.cases) is not tuple
            or len(self.cases) > MAX_FEEDBACK_CASES
            or any(type(case) is not DescriptionFeedbackCase for case in self.cases)
        ):
            raise ValueError("Invalid bounded description feedback cases.")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate description feedback case identity.")
        seen: set[tuple[str, str, str, str, str]] = set()
        for case in self.cases:
            for target in case.target_actor_ids:
                key = (
                    case.run_id,
                    case.event_id,
                    case.request_hash,
                    case.refinement_payload_hash,
                    target,
                )
                if key in seen:
                    raise ValueError(
                        "Duplicate or conflicting description feedback for one target."
                    )
                seen.add(key)


@dataclass(frozen=True, slots=True)
class DescriptionReview:
    case_id: str
    recorded_on: str
    pilot_report_sha256: str
    run_id: str
    event_id: str
    request_hash: str
    refinement_payload_hash: str
    shot_id: str
    actor_id: str
    verdict: DescriptionVerdict
    scope: str
    source: str
    statement: str


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate description feedback JSON field.")
        value[key] = item
    return value


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Unexpected description feedback fields.")
    return value


def _list(value: object, maximum: int) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        raise ValueError("Invalid bounded description feedback list.")
    return value


def _nonfinite(value: str) -> None:
    raise ValueError("Non-finite description feedback JSON numbers are invalid.")


def decode_description_feedback(text: str) -> DescriptionFeedback:
    """Decode the existing immutable feedback record without interpreting its prose."""
    if type(text) is not str:
        raise ValueError("Description feedback requires JSON text.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("Description feedback requires valid Unicode.") from None
    if size > MAX_FEEDBACK_BYTES:
        raise ValueError("Description feedback exceeds its byte limit.")
    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (RecursionError, json.JSONDecodeError):
        raise ValueError("Invalid description feedback JSON.") from None
    value = _object(document, _ROOT_FIELDS)
    if value["phase0QualityGate"] is not None or type(value["newProviderCalls"]) is not int:
        raise ValueError("Invalid description feedback gate or provider-call policy.")
    cases = []
    for raw in _list(value["cases"], MAX_FEEDBACK_CASES):
        item = _object(raw, _CASE_FIELDS)
        cases.append(
            DescriptionFeedbackCase(
                _string(item["caseId"]),
                _string(item["runId"]),
                _string(item["eventId"]),
                _string(item["requestHash"]),
                _string(item["refinementPayloadHash"]),
                _string(item["scope"]),
                tuple(
                    _string(target) for target in _list(item["targetActorIds"], MAX_CASE_TARGETS)
                ),
                cast(DescriptionVerdict, _string(item["verdict"])),
                _string(item["source"]),
                _string(item["statement"]),
            )
        )
    return DescriptionFeedback(
        _string(value["schemaVersion"]),
        _string(value["recordedOn"]),
        _string(value["pilotReportSha256"]),
        tuple(cases),
        _string(value["unmentionedEntries"]),
        None,
        value["newProviderCalls"],
    )


def project_description_feedback(
    feedback: DescriptionFeedback,
    *,
    pilot_report_sha256: str,
    run_id: str,
    event_id: str,
    request_hash: str,
    detail: CandidateDetail,
) -> tuple[DescriptionReview, ...]:
    """Return only reviewed descriptions belonging to the exact supplied saved result."""
    if type(feedback) is not DescriptionFeedback or type(detail) is not CandidateDetail:
        raise ValueError("Projection requires typed description feedback and candidate detail.")
    _hash(pilot_report_sha256)
    _hash(request_hash)
    _event(run_id, event_id)
    if feedback.pilot_report_sha256 != pilot_report_sha256:
        raise ValueError("Description feedback pilot report SHA-256 mismatch.")
    if detail.run_id != run_id or detail.event_id != event_id:
        raise ValueError("Description feedback projection received a foreign candidate detail.")
    current_key = (run_id, event_id, request_hash, payload_hash(detail))
    targets = {(shot.shot_id, actor.actor_id) for shot in detail.shots for actor in shot.actors}
    reviews = []
    for case in feedback.cases:
        if (
            case.run_id,
            case.event_id,
            case.request_hash,
            case.refinement_payload_hash,
        ) != current_key:
            continue
        for target in case.target_actor_ids:
            shot_id, actor_id = target.split("/")
            if (shot_id, actor_id) not in targets:
                raise ValueError("Description feedback references a nonexistent shot/actor target.")
            reviews.append(
                DescriptionReview(
                    case.case_id,
                    feedback.recorded_on,
                    feedback.pilot_report_sha256,
                    run_id,
                    event_id,
                    request_hash,
                    current_key[3],
                    shot_id,
                    actor_id,
                    case.verdict,
                    case.scope,
                    case.source,
                    case.statement,
                )
            )
    return tuple(reviews)
