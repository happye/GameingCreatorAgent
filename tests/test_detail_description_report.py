"""Frozen report identity and payload checks cannot borrow another candidate's judgment."""

import builtins
import hashlib
import json
import socket
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from test_detail_description_feedback import detail_fixture, record_fixture

from gamingcreator.application.detail_description_feedback import (
    MAX_FEEDBACK_BYTES,
    decode_description_feedback,
)
from gamingcreator.application.detail_description_report import validate_description_report
from gamingcreator.application.detail_refinement_budget import canonical_detail_json


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def report_fixture():
    return {
        "schemaVersion": "actor-detail-pilot-report-v1",
        "cases": [
            {
                "caseId": case["caseId"],
                "runId": case["runId"],
                "eventId": case["eventId"],
                "requestHash": case["requestHash"],
                "attempt": {
                    "status": "completed",
                    "requestHash": case["requestHash"],
                    "payloadHash": case["refinementPayloadHash"],
                    "payloadJson": canonical_detail_json(detail_fixture(case["runId"])),
                    "metadata": {"unknownCost": True},
                },
                "humanLabels": None,
                "qualityGate": None,
            }
            for case in record_fixture()["cases"]
        ],
        "qualityGate": None,
        "humanLabels": None,
    }


def bound(report=None, record=None, text=None):
    report = report_fixture() if report is None else report
    record = record_fixture() if record is None else record
    text = json.dumps(report, ensure_ascii=False) if text is None else text
    record["pilotReportSha256"] = digest(text)
    return decode_description_feedback(json.dumps(record, ensure_ascii=False)), text


def replace_payload(report, record, payload):
    text = json.dumps(payload, ensure_ascii=False)
    report["cases"][0]["attempt"].update(payloadJson=text, payloadHash=digest(text))
    record["cases"][0]["refinementPayloadHash"] = digest(text)


def test_frozen_report_supports_three_acceptances_and_one_rejection_without_changing_inputs():
    feedback, text = bound()
    before = deepcopy(feedback)
    assert validate_description_report(feedback, text) is None
    assert feedback == before and text == bound()[1]


def test_unknown_report_fields_are_preserved_without_turning_them_into_quality_acceptance():
    report = report_fixture()
    report.update(futureMetadata={"note": "原报告记录保留😀"}, qualityGate=True)
    report["cases"][0].update(unrelatedMatch={"full": True})
    feedback, text = bound(report)
    validate_description_report(feedback, text)
    assert feedback.phase0_quality_gate is None


@pytest.mark.parametrize("schema", ["future", True, None])
def test_wrong_report_schema_is_rejected_even_with_a_correct_report_sha(schema):
    report = report_fixture()
    report["schemaVersion"] = schema
    with pytest.raises(ValueError):
        validate_description_report(*bound(report))


@pytest.mark.parametrize("field", ["schemaVersion", "cases"])
def test_missing_root_fields_are_explicit_errors(field):
    report = report_fixture()
    del report[field]
    with pytest.raises(ValueError):
        validate_description_report(*bound(report))


@pytest.mark.parametrize("field", ["caseId", "runId", "eventId", "requestHash", "attempt"])
def test_report_case_requires_all_identity_and_attempt_fields(field):
    report = report_fixture()
    del report["cases"][0][field]
    with pytest.raises(ValueError):
        validate_description_report(*bound(report))


@pytest.mark.parametrize(
    "field,value",
    [
        ("caseId", False),
        ("caseId", "../candidate"),
        ("runId", True),
        ("runId", "other-run"),
        ("eventId", None),
        ("eventId", "run-1:media-1:event:short"),
        ("requestHash", False),
        ("requestHash", "B" * 64),
        ("requestHash", "9" * 64),
        ("attempt", False),
        ("attempt", []),
    ],
)
def test_case_identity_and_types_cannot_be_borrowed_or_coerced(field, value):
    report = report_fixture()
    report["cases"][0][field] = value
    with pytest.raises(ValueError):
        validate_description_report(*bound(report))


def test_same_case_id_cannot_borrow_another_valid_candidate_even_when_report_sha_is_correct():
    report = report_fixture()
    borrowed = dict(report["cases"][1], caseId=report["cases"][0]["caseId"])
    report["cases"][0] = borrowed
    with pytest.raises(ValueError, match="case identity differs"):
        validate_description_report(*bound(report))


def test_missing_feedback_case_and_duplicate_report_case_are_rejected():
    report = report_fixture()
    report["cases"].pop()
    with pytest.raises(ValueError, match="missing"):
        validate_description_report(*bound(report))
    report = report_fixture()
    report["cases"].append(deepcopy(report["cases"][0]))
    with pytest.raises(ValueError, match="Duplicate.*case"):
        validate_description_report(*bound(report))


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "Completed"),
        ("status", "failed"),
        ("status", "planned"),
        ("status", True),
        ("requestHash", "9" * 64),
        ("requestHash", False),
        ("payloadHash", "9" * 64),
        ("payloadHash", True),
        ("payloadJson", None),
        ("payloadJson", {}),
        ("payloadJson", "not json"),
    ],
)
def test_only_exact_completed_attempt_and_actual_payload_text_can_back_feedback(field, value):
    report = report_fixture()
    report["cases"][0]["attempt"][field] = value
    with pytest.raises(ValueError):
        validate_description_report(*bound(report))


@pytest.mark.parametrize("field", ["status", "requestHash", "payloadHash", "payloadJson"])
def test_missing_attempt_fields_are_explicit_errors(field):
    report = report_fixture()
    del report["cases"][0]["attempt"][field]
    with pytest.raises(ValueError):
        validate_description_report(*bound(report))


@pytest.mark.parametrize("change", ["description", "whitespace"])
def test_payload_is_hashed_as_original_utf8_text_without_silent_recanonicalization(change):
    report = report_fixture()
    attempt = report["cases"][0]["attempt"]
    if change == "description":
        attempt["payloadJson"] = attempt["payloadJson"].replace("可见描述1", "改动描述")
    else:
        attempt["payloadJson"] += " "
    with pytest.raises(ValueError, match="payload SHA-256 mismatch"):
        validate_description_report(*bound(report))


@pytest.mark.parametrize("field,value", [("runId", "foreign-run"), ("eventId", "another-event")])
def test_payload_candidate_identity_is_verified_even_when_payload_hash_is_rebound(field, value):
    report, record = report_fixture(), record_fixture()
    payload = json.loads(report["cases"][0]["attempt"]["payloadJson"])
    payload[field] = value
    replace_payload(report, record, payload)
    with pytest.raises(ValueError, match="another candidate"):
        validate_description_report(*bound(report, record))


@pytest.mark.parametrize(
    "change",
    [
        "missing_run",
        "missing_event",
        "missing_shots",
        "wrong_shots_type",
        "missing_actors",
        "wrong_actors_type",
        "missing_shot_id",
        "missing_actor_id",
        "missing_actor_shot",
        "foreign_actor_shot",
        "duplicate_shot",
        "duplicate_actor",
        "unsafe_shot",
        "unsafe_actor",
        "too_many_shots",
        "too_many_actors",
        "target_only_in_metadata",
    ],
)
def test_payload_target_structure_is_bounded_unique_and_bound_to_its_enclosing_shot(change):
    report, record = report_fixture(), record_fixture()
    payload = json.loads(report["cases"][0]["attempt"]["payloadJson"])
    shot = payload["shots"][0]
    actor = shot["actors"][0]
    if change == "missing_run":
        del payload["runId"]
    elif change == "missing_event":
        del payload["eventId"]
    elif change == "missing_shots":
        del payload["shots"]
    elif change == "wrong_shots_type":
        payload["shots"] = False
    elif change == "missing_actors":
        del shot["actors"]
    elif change == "wrong_actors_type":
        shot["actors"] = {}
    elif change == "missing_shot_id":
        del shot["shotId"]
    elif change == "missing_actor_id":
        del actor["actorId"]
    elif change == "missing_actor_shot":
        del actor["shotId"]
    elif change == "foreign_actor_shot":
        actor["shotId"] = "s2"
    elif change == "duplicate_shot":
        payload["shots"].append(deepcopy(shot))
    elif change == "duplicate_actor":
        shot["actors"].append(deepcopy(actor))
    elif change == "unsafe_shot":
        shot["shotId"] = "../shot"
    elif change == "unsafe_actor":
        actor["actorId"] = True
    elif change == "too_many_shots":
        payload["shots"] *= 5
    elif change == "too_many_actors":
        shot["actors"] *= 3
    else:
        payload["onlyMetadataTargets"] = ["s1/a1", "s1/a2", "s1/a3"]
        shot["actors"] = []
    replace_payload(report, record, payload)
    with pytest.raises(ValueError):
        validate_description_report(*bound(report, record))


def test_nonexistent_requested_target_and_later_invalid_target_are_errors():
    for targets in (["s2/a2"], ["s1/a1", "missing/a2"]):
        record = record_fixture()
        record["cases"][0]["targetActorIds"] = targets
        with pytest.raises(ValueError, match="target is missing"):
            validate_description_report(*bound(record=record))


def test_safe_generic_target_ids_and_cross_shot_actor_ids_are_supported():
    report, record = report_fixture(), record_fixture()
    payload = json.loads(report["cases"][0]["attempt"]["payloadJson"])
    shot = payload["shots"][0]
    shot["shotId"] = "shot-1"
    shot["actors"] = [{"shotId": "shot-1", "actorId": "left"}]
    record["cases"][0]["targetActorIds"] = ["shot-1/left", "s2/a1"]
    replace_payload(report, record, payload)
    validate_description_report(*bound(report, record))


@pytest.mark.parametrize("where", ["report", "payload"])
def test_duplicate_json_fields_are_rejected_at_every_decoded_layer(where):
    report, record = report_fixture(), record_fixture()
    if where == "report":
        text = json.dumps(report).replace(
            '"schemaVersion": "actor-detail-pilot-report-v1"',
            '"schemaVersion": "actor-detail-pilot-report-v1", "\\u0073chemaVersion": "actor-detail-pilot-report-v1"',
            1,
        )
        feedback, text = bound(report, record, text)
    else:
        attempt = report["cases"][0]["attempt"]
        text = attempt["payloadJson"].replace('"actorId":"a1"', '"actorId":"a1","actorId":"a1"', 1)
        attempt.update(payloadJson=text, payloadHash=digest(text))
        record["cases"][0]["refinementPayloadHash"] = digest(text)
        feedback, text = bound(report, record)
    with pytest.raises(ValueError, match="Duplicate.*JSON"):
        validate_description_report(feedback, text)


def test_report_case_limit_is_inclusive_and_overlimit_is_rejected():
    report = report_fixture()
    extra = report["cases"][0]
    report["cases"].extend(dict(extra, caseId=f"extra-{index}") for index in range(126))
    validate_description_report(*bound(report))
    report["cases"].append(dict(extra, caseId="extra-final"))
    with pytest.raises(ValueError, match="bounded"):
        validate_description_report(*bound(report))


def test_utf8_byte_limit_and_report_sha_are_checked_without_truncation():
    feedback, text = bound()
    with pytest.raises(ValueError, match="report SHA-256 mismatch"):
        validate_description_report(feedback, text + " ")
    padded = text + " " * (MAX_FEEDBACK_BYTES - len(text.encode("utf-8")))
    validate_description_report(*bound(text=padded))
    with pytest.raises(ValueError, match="byte limit"):
        validate_description_report(*bound(text=padded + " "))


@pytest.mark.parametrize("text", [None, True, b"{}", "[]", "null", "{", "\ud800"])
def test_invalid_report_json_is_a_value_error(text):
    feedback, _ = bound()
    with pytest.raises(ValueError):
        validate_description_report(feedback, text)


def test_deep_nesting_nonfinite_numbers_and_untyped_feedback_are_rejected():
    feedback, text = bound()
    for invalid in ("[" * 2000 + "0" + "]" * 2000, '{"ignored": NaN}'):
        with pytest.raises(ValueError):
            validate_description_report(feedback, invalid)
    with pytest.raises(ValueError):
        validate_description_report({}, text)


def test_pure_report_validation_performs_no_file_database_or_network_io(monkeypatch):
    feedback, text = bound()

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure report validator attempted I/O.")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        validate_description_report(feedback, text)
