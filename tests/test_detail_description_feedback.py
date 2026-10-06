"""Description judgments stay bounded, immutable and attached to their exact result."""

import builtins
import json
import socket
import sqlite3
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path

import pytest

from gamingcreator.application.detail_description_feedback import (
    MAX_FEEDBACK_BYTES,
    DescriptionFeedback,
    decode_description_feedback,
    project_description_feedback,
)
from gamingcreator.application.detail_refinement import registered_candidate_id
from gamingcreator.application.detail_refinement_budget import canonical_detail_json, payload_hash
from gamingcreator.domain.actor_details import (
    ActorDetail,
    CandidateDetail,
    DetailEvidence,
    ShotDetail,
)
from gamingcreator.domain.time import SourceInstant, SourceRange

REPORT_HASH = "a" * 64
REQUEST_HASH = "b" * 64
SECOND_REQUEST_HASH = "c" * 64


def detail_fixture(run_id="run-1"):
    event_id = f"{run_id}:media-1:event:" + "1" * 24
    evidence = tuple(
        DetailEvidence(
            f"{run_id}:media-1:image:{index:06d}",
            str(index + 1) * 64,
            SourceInstant((index + 1) * 100, 1000),
        )
        for index in range(3)
    )
    first = ShotDetail(
        "s1",
        SourceRange(100, 201, 1000),
        tuple(item.evidence_id for item in evidence[:2]),
        (),
        tuple(ActorDetail("s1", f"a{index}", f"可见描述{index}", ()) for index in range(1, 5)),
    )
    second = ShotDetail(
        "s2",
        SourceRange(300, 301, 1000),
        (evidence[2].evidence_id,),
        (),
        (ActorDetail("s2", "a1", "另一镜头的描述", ()),),
    )
    return CandidateDetail(
        run_id,
        "media-1",
        event_id,
        registered_candidate_id(run_id, event_id),
        "2" * 64,
        "3" * 64,
        "4" * 64,
        "pipeline-v1",
        "base-v1",
        "5" * 64,
        "6" * 64,
        SourceRange(0, 500, 1000),
        evidence,
        (first, second),
    )


def case_fixture(detail, *, case_id="actor-separation", request_hash=REQUEST_HASH):
    return {
        "caseId": case_id,
        "runId": detail.run_id,
        "eventId": detail.event_id,
        "requestHash": request_hash,
        "refinementPayloadHash": payload_hash(detail),
        "scope": "actor-description",
        "targetActorIds": ["s1/a1", "s1/a2", "s1/a3"],
        "verdict": "accepted",
        "source": "direct-project-user-feedback",
        "statement": "用户确认三个描述；不扩大为全部属性或检索质量通过。",
    }


def record_fixture():
    second = case_fixture(
        detail_fixture("run-2"), case_id="held-item-shape", request_hash=SECOND_REQUEST_HASH
    )
    second.update(
        targetActorIds=["s1/a2"],
        verdict="rejected",
        statement="用户指出s1/a2错误：大面积前景是靠近镜头的物品，不是新人物；其他描述未判定。",
    )
    return {
        "schemaVersion": "detail-pilot-human-feedback-v1",
        "recordedOn": "2026-10-06",
        "pilotReportSha256": REPORT_HASH,
        "cases": [case_fixture(detail_fixture()), second],
        "unmentionedEntries": "unreviewed",
        "phase0QualityGate": None,
        "newProviderCalls": 0,
    }


def decode(record=None):
    return decode_description_feedback(
        json.dumps(record_fixture() if record is None else record, ensure_ascii=False)
    )


def project(feedback=None, detail=None, **changes):
    detail = detail_fixture() if detail is None else detail
    arguments = {
        "pilot_report_sha256": REPORT_HASH,
        "run_id": detail.run_id,
        "event_id": detail.event_id,
        "request_hash": REQUEST_HASH,
        "detail": detail,
    }
    arguments.update(changes)
    return project_description_feedback(decode() if feedback is None else feedback, **arguments)


def test_three_accepted_and_one_rejected_descriptions_do_not_label_unmentioned_entries():
    feedback = decode()
    accepted = project(feedback)
    rejected = project(feedback, detail_fixture("run-2"), request_hash=SECOND_REQUEST_HASH)
    assert [(item.shot_id, item.actor_id, item.verdict) for item in accepted] == [
        ("s1", "a1", "accepted"),
        ("s1", "a2", "accepted"),
        ("s1", "a3", "accepted"),
    ]
    assert [(item.shot_id, item.actor_id, item.verdict) for item in rejected] == [
        ("s1", "a2", "rejected")
    ]
    assert all(item.scope == "actor-description" for item in (*accepted, *rejected))
    assert feedback.unmentioned_entries == "unreviewed"
    assert feedback.phase0_quality_gate is None and feedback.new_provider_calls == 0
    assert ("s1", "a4") not in {(item.shot_id, item.actor_id) for item in accepted}
    assert ("s2", "a1") not in {(item.shot_id, item.actor_id) for item in accepted}
    assert rejected[0].source == "direct-project-user-feedback"
    assert rejected[0].recorded_on == "2026-10-06"
    assert rejected[0].statement == record_fixture()["cases"][1]["statement"]
    assert rejected[0].pilot_report_sha256 == REPORT_HASH


@pytest.mark.parametrize("field", ["runId", "eventId", "requestHash", "refinementPayloadHash"])
def test_each_exact_identity_dimension_is_required_without_reusing_old_labels(field):
    record = record_fixture()
    case = record["cases"][0]
    if field == "runId":
        case.update(runId="old-run", eventId="old-run:media-1:event:" + "1" * 24)
    elif field == "eventId":
        case[field] = "run-1:media-1:event:" + "9" * 24
    else:
        case[field] = "9" * 64
    assert project(decode(record)) == ()


@pytest.mark.parametrize("change", ["profile", "description", "unassigned"])
def test_current_payload_is_computed_from_actual_detail_and_old_feedback_is_isolated(change):
    detail = detail_fixture()
    if change == "profile":
        detail = replace(detail, detail_identity_hash="9" * 64)
    elif change == "description":
        actor = replace(detail.shots[0].actors[0], description="新结果中的人物描述")
        shot = replace(detail.shots[0], actors=(actor, *detail.shots[0].actors[1:]))
        detail = replace(detail, shots=(shot, detail.shots[1]))
    else:
        detail = replace(detail, notes=("保留新的不确定说明",))
    assert payload_hash(detail) != record_fixture()["cases"][0]["refinementPayloadHash"]
    assert project(detail=detail) == ()


def test_report_hash_mismatch_is_an_error_even_when_no_case_matches_current_result():
    with pytest.raises(ValueError, match="report SHA-256 mismatch"):
        project(detail=detail_fixture("unreviewed-run"), pilot_report_sha256="9" * 64)


@pytest.mark.parametrize("target", ["missing/a1", "s1/missing", "s2/a2"])
def test_nonexistent_exact_shot_actor_target_is_rejected(target):
    record = record_fixture()
    record["cases"][0]["targetActorIds"] = [target]
    with pytest.raises(ValueError, match="nonexistent"):
        project(decode(record))


def test_nonexistent_target_in_an_old_payload_does_not_become_a_current_label_or_error():
    record = record_fixture()
    record["cases"][0].update(refinementPayloadHash="9" * 64, targetActorIds=["missing/a1"])
    assert project(decode(record)) == ()


def test_same_actor_id_in_another_shot_is_a_distinct_review_target():
    record = record_fixture()
    record["cases"][0]["targetActorIds"] = ["s2/a1"]
    reviews = project(decode(record))
    assert [(item.shot_id, item.actor_id) for item in reviews] == [("s2", "a1")]


def test_domain_safe_target_names_are_supported_without_assuming_s_number_a_number():
    detail = detail_fixture()
    shot = replace(
        detail.shots[0],
        shot_id="shot-1",
        actors=(replace(detail.shots[0].actors[0], shot_id="shot-1", actor_id="left"),),
    )
    detail = replace(detail, shots=(shot, detail.shots[1]))
    record = record_fixture()
    record["cases"][0] = case_fixture(detail)
    record["cases"][0]["targetActorIds"] = ["shot-1/left"]
    assert [(item.shot_id, item.actor_id) for item in project(decode(record), detail)] == [
        ("shot-1", "left")
    ]


def test_same_shot_mixed_verdicts_and_broad_statement_do_not_label_unmentioned_actors():
    record = record_fixture()
    original = record["cases"][0]
    original.update(targetActorIds=["s1/a1"], statement="全部正确")
    record["cases"].append(
        dict(original, caseId="reject-second", targetActorIds=["s1/a2"], verdict="rejected")
    )
    reviews = project(decode(record))
    assert [(item.actor_id, item.verdict) for item in reviews] == [
        ("a1", "accepted"),
        ("a2", "rejected"),
    ]


def test_later_invalid_target_prevents_returning_a_partial_review():
    record = record_fixture()
    record["cases"][0]["targetActorIds"] = ["s1/a1", "missing/a2"]
    with pytest.raises(ValueError, match="nonexistent"):
        project(decode(record))


@pytest.mark.parametrize(
    "field,value",
    [
        ("schemaVersion", "future"),
        ("schemaVersion", True),
        ("recordedOn", "2026-2-06"),
        ("recordedOn", "2026-02-30"),
        ("recordedOn", "0000-01-01"),
        ("recordedOn", "2026-10-06T00:00:00"),
        ("recordedOn", False),
        ("pilotReportSha256", "A" * 64),
        ("pilotReportSha256", "a" * 63),
        ("pilotReportSha256", True),
        ("unmentionedEntries", "accepted"),
        ("unmentionedEntries", None),
        ("phase0QualityGate", True),
        ("phase0QualityGate", 0),
        ("newProviderCalls", False),
        ("newProviderCalls", True),
        ("newProviderCalls", 0.0),
        ("newProviderCalls", 1),
        ("newProviderCalls", -1),
        ("cases", None),
        ("cases", {}),
        ("cases", [True]),
    ],
)
def test_root_fields_cannot_forge_policy_identity_or_acceptance(field, value):
    record = record_fixture()
    record[field] = value
    with pytest.raises(ValueError):
        decode(record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("caseId", "../escape"),
        ("caseId", "x" * 129),
        ("caseId", False),
        ("runId", "../run"),
        ("runId", False),
        ("eventId", "other-run:media-1:event:" + "1" * 24),
        ("eventId", "run-1:media-1:event:" + "1" * 23),
        ("eventId", True),
        ("requestHash", "B" * 64),
        ("requestHash", "b" * 65),
        ("requestHash", False),
        ("refinementPayloadHash", "c" * 63),
        ("refinementPayloadHash", False),
        ("scope", "actor-attributes"),
        ("scope", "U10"),
        ("scope", False),
        ("source", "model-self-review"),
        ("source", True),
        ("verdict", "unreviewed"),
        ("verdict", True),
        ("statement", ""),
        ("statement", " \n\t"),
        ("statement", "x" * 2049),
        ("statement", False),
        ("statement", "\ud800"),
        ("targetActorIds", []),
        ("targetActorIds", {}),
        ("targetActorIds", False),
        ("targetActorIds", [True]),
        ("targetActorIds", ["s1/a1", "s1/a1"]),
        ("targetActorIds", ["a1"]),
        ("targetActorIds", ["s1/a1/extra"]),
        ("targetActorIds", ["../a1"]),
        ("targetActorIds", ["s1/" + "x" * 129]),
        ("targetActorIds", [f"s1/a{index}" for index in range(9)]),
    ],
)
def test_case_fields_are_strict_bounded_and_description_only(field, value):
    record = record_fixture()
    record["cases"][0][field] = value
    with pytest.raises(ValueError):
        decode(record)


@pytest.mark.parametrize("scope", ["root", "case"])
@pytest.mark.parametrize("change", ["extra", "missing", "duplicate"])
def test_unknown_missing_and_duplicate_fields_never_silently_override(scope, change):
    record = record_fixture()
    item = record if scope == "root" else record["cases"][0]
    field = "schemaVersion" if scope == "root" else "verdict"
    if change == "extra":
        item["forgedAcceptance"] = True
    elif change == "missing":
        del item[field]
    text = json.dumps(record)
    if change == "duplicate":
        token = json.dumps(field) + ": " + json.dumps(item[field])
        text = text.replace(token, token + ", " + token, 1)
    with pytest.raises(ValueError):
        decode_description_feedback(text)


def test_json_escaped_field_name_is_still_a_duplicate_field():
    text = json.dumps(record_fixture())
    text = text.replace(
        '"scope": "actor-description"',
        '"scope": "actor-description", "\\u0073cope": "actor-description"',
        1,
    )
    with pytest.raises(ValueError, match="Duplicate.*JSON"):
        decode_description_feedback(text)


@pytest.mark.parametrize("verdict", ["accepted", "rejected"])
def test_repeated_or_contradictory_judgment_for_one_exact_target_is_rejected(verdict):
    record = record_fixture()
    extra = dict(
        record["cases"][0], caseId="another-review", targetActorIds=["s1/a2"], verdict=verdict
    )
    record["cases"].append(extra)
    with pytest.raises(ValueError, match="Duplicate or conflicting"):
        decode(record)


def test_duplicate_case_identity_is_rejected_even_for_different_results():
    record = record_fixture()
    record["cases"][1]["caseId"] = record["cases"][0]["caseId"]
    with pytest.raises(ValueError, match="Duplicate.*case"):
        decode(record)


def test_nonoverlapping_targets_and_different_payloads_are_distinct_historical_judgments():
    record = record_fixture()
    original = record["cases"][0]
    extra = dict(original, caseId="fourth-review", targetActorIds=["s1/a4"], verdict="rejected")
    stale = dict(original, caseId="old-review", refinementPayloadHash="9" * 64, verdict="rejected")
    record["cases"].extend([extra, stale])
    reviews = project(decode(record))
    assert [item.verdict for item in reviews] == ["accepted"] * 3 + ["rejected"]
    assert all(item.case_id != "old-review" for item in reviews)


def test_limits_are_inclusive_and_empty_records_stay_unreviewed():
    record = record_fixture()
    original = record["cases"][0]
    original["statement"] = "字" * 2048
    original["targetActorIds"] = [f"s1/a{index}" for index in range(1, 9)]
    record["cases"] = [
        dict(original, caseId=f"case-{index}", requestHash=f"{index:064x}") for index in range(128)
    ]
    assert len(decode(record).cases) == 128
    record["cases"].append(dict(original, caseId="case-129", requestHash="f" * 64))
    with pytest.raises(ValueError):
        decode(record)
    record["cases"] = []
    assert project(decode(record)) == ()


def test_byte_limit_counts_utf8_and_never_truncates_json_or_statement():
    text = json.dumps(record_fixture(), ensure_ascii=False)
    remaining = MAX_FEEDBACK_BYTES - len(text.encode("utf-8"))
    padded = text + " " * remaining
    assert decode_description_feedback(padded) == decode()
    with pytest.raises(ValueError, match="byte limit"):
        decode_description_feedback(padded + " ")
    with pytest.raises(ValueError, match="byte limit"):
        decode_description_feedback("字" * (MAX_FEEDBACK_BYTES // 3 + 1))


@pytest.mark.parametrize("text", [None, True, b"{}", "{", "[]", "null", "\ud800"])
def test_invalid_json_input_is_an_explicit_value_error(text):
    with pytest.raises(ValueError):
        decode_description_feedback(text)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_is_rejected(value):
    text = json.dumps(record_fixture()).replace(
        '"newProviderCalls": 0', '"newProviderCalls": ' + value
    )
    with pytest.raises(ValueError):
        decode_description_feedback(text)


def test_deeply_nested_invalid_json_does_not_leak_recursion_error():
    with pytest.raises(ValueError):
        decode_description_feedback("[" * 2000 + "0" + "]" * 2000)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pilot_report_sha256", True),
        ("pilot_report_sha256", "A" * 64),
        ("request_hash", False),
        ("request_hash", "b" * 63),
        ("run_id", False),
        ("event_id", "run-1:media-1:event:short"),
        ("detail", None),
        ("detail", {}),
    ],
)
def test_projection_rejects_invalid_inputs_before_a_review_can_be_returned(field, value):
    detail = detail_fixture()
    arguments = {
        "pilot_report_sha256": REPORT_HASH,
        "run_id": detail.run_id,
        "event_id": detail.event_id,
        "request_hash": REQUEST_HASH,
        "detail": detail,
    }
    arguments[field] = value
    with pytest.raises(ValueError):
        project_description_feedback(decode(), **arguments)


def test_projection_rejects_a_foreign_detail_instead_of_trusting_caller_identity():
    with pytest.raises(ValueError, match="foreign candidate"):
        project(detail=detail_fixture("run-2"), run_id="run-1", event_id=detail_fixture().event_id)
    with pytest.raises(ValueError):
        project_description_feedback(
            {},
            pilot_report_sha256=REPORT_HASH,
            run_id="run-1",
            event_id=detail_fixture().event_id,
            request_hash=REQUEST_HASH,
            detail=detail_fixture(),
        )


def test_unicode_html_statement_and_original_feedback_are_preserved_without_interpretation():
    record = record_fixture()
    statement = '  用户说😀<img src=x onerror="alert(1)">描述正确\n只是描述，不是全部属性。  '
    record["cases"][0]["statement"] = statement
    feedback = decode(record)
    record["cases"][0]["statement"] = "later mutation"
    assert all(item.statement == statement for item in project(feedback))
    assert feedback.cases[0].statement == statement


def test_decoded_dtos_are_immutable_and_repeated_projection_does_not_mutate_detail():
    detail = detail_fixture()
    before = canonical_detail_json(detail)
    feedback = decode()
    first = project(feedback, detail)
    assert isinstance(first, tuple)
    for item, field, value in [
        (feedback, "recorded_on", "2026-10-07"),
        (feedback.cases[0], "statement", "changed"),
        (first[0], "verdict", "rejected"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(item, field, value)
    assert project(feedback, detail) == first
    assert canonical_detail_json(detail) == before
    assert asdict(first[0])["refinement_payload_hash"] == payload_hash(detail)


def test_direct_dto_construction_cannot_bypass_record_validation():
    feedback = decode()
    with pytest.raises(ValueError):
        replace(feedback, new_provider_calls=False)
    with pytest.raises(ValueError):
        replace(feedback.cases[0], statement="\ud800")
    with pytest.raises(ValueError):
        replace(feedback, cases=[feedback.cases[0]])
    assert isinstance(feedback, DescriptionFeedback)


def test_codec_and_projection_perform_no_file_database_or_network_io(monkeypatch):
    text = json.dumps(record_fixture())
    detail = detail_fixture()

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure feedback code attempted I/O.")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        assert len(project(decode_description_feedback(text), detail)) == 3
