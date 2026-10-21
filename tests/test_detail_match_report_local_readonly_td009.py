"""TD009 readonly对照：本机 demo-phase0 旧 match-report-v1 不得通过现行 v1.1 合同.

Verification = pytest + 只读打开 artifacts JSON. No DeepSeek / launcher / paid /
browser. Missing artifacts => skip. Does not claim F006 / F010 / TD009 closeout
or gap clearance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.detail_query import (
    MATCH_REPORT_VERSION,
    assert_match_report_contract,
    assert_match_report_sidecar_binding_contract,
    match_report_contract_gaps,
)
from gamingcreator.domain.actor_details import MATCHER_VERSION, TEMPORAL_MATCHER_VERSION

REPO = Path(__file__).resolve().parents[1]
DEMO_PHASE0 = REPO / "artifacts" / "demo-phase0"
LEGACY_SCHEMA = "actor-detail-match-report-v1"
LEGACY_MATCHER = "actor-detail-matcher-v1"


def _legacy_match_files() -> list[Path]:
    if not DEMO_PHASE0.is_dir():
        return []
    return sorted(DEMO_PHASE0.rglob("*-actor-detail-matcher-*.json"))


def _require_legacy_matches() -> list[Path]:
    files = _legacy_match_files()
    if not files:
        pytest.skip(f"local legacy match reports missing under {DEMO_PHASE0}")
    return files


def test_local_demo_phase0_legacy_match_reports_fail_current_v1_1_contract() -> None:
    files = _require_legacy_matches()
    assert len(files) >= 1
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        assert document.get("schemaVersion") == LEGACY_SCHEMA, path.name
        # Partial inert already: no forged human pass on these disks.
        assert document.get("humanLabels") is None
        assert document.get("qualityGate") is None
        with pytest.raises(ValueError):
            assert_match_report_contract(document)
        gaps = match_report_contract_gaps(document)
        assert "schema_version_mismatch" in gaps, (path.name, gaps)
        assert "missing:constraintHash" in gaps
        assert "missing:inertContract" in gaps
        assert "missing:independentStaticClothingIndex" in gaps
        assert "matcher_version_mismatch" in gaps
        result = document["result"]
        assert result.get("matcherVersion") == LEGACY_MATCHER
        assert result.get("matcherVersion") not in {MATCHER_VERSION, TEMPORAL_MATCHER_VERSION}
        assert MATCH_REPORT_VERSION == "actor-detail-match-report-v1.1"
        assert MATCHER_VERSION == "actor-detail-matcher-v1.2"


def test_match_report_contract_gaps_empty_for_current_fixture_shape() -> None:
    """Fresh v1.1 reports (built via match_report) still report zero gaps."""
    from test_detail_match_report_contract import _weapon_coexist_detail
    from test_actor_detail_matching import EVENT, RUN
    from gamingcreator.application.detail_query import match_report
    from gamingcreator.domain.actor_details import AttributeKind, QueryConstraint
    from test_actor_detail_matching import condition

    query = QueryConstraint((condition(AttributeKind.HELD_CLASS, "weapon", "item"),))
    document = match_report(
        None,
        _weapon_coexist_detail(),
        query,
        run_id=RUN,
        event_id=EVENT,
        request_digest=None,
    )
    assert_match_report_contract(document)
    assert match_report_contract_gaps(document) == ()


def test_match_report_contract_gaps_flags_forged_human_pass_on_legacy_shape() -> None:
    files = _require_legacy_matches()
    document = json.loads(files[0].read_text(encoding="utf-8-sig"))
    forged = dict(document)
    forged["humanLabels"] = {"reviewer": "bot"}
    forged["qualityGate"] = True
    gaps = match_report_contract_gaps(forged)
    assert "human_labels_not_null" in gaps
    assert "quality_gate_not_null" in gaps


def test_local_demo_phase0_legacy_match_reports_bind_refinement_sidecars() -> None:
    """Legacy v1 reports still point at real detail-refinements request/result pairs."""
    files = _require_legacy_matches()
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        request_hash = document.get("refinementRequestHash")
        payload_hash = document.get("refinementPayloadHash")
        assert isinstance(request_hash, str) and len(request_hash) == 64
        assert isinstance(payload_hash, str) and len(payload_hash) == 64
        sidecars = list(DEMO_PHASE0.glob(f"**/detail-refinements/{request_hash}/request.json"))
        assert len(sidecars) == 1, (path.name, request_hash)
        request_doc = json.loads(sidecars[0].read_text(encoding="utf-8-sig"))
        result_path = sidecars[0].with_name("result.json")
        assert result_path.is_file(), path.name
        result_doc = json.loads(result_path.read_text(encoding="utf-8-sig"))
        # Deepened binding: identity + media + evidence ⊆ sidecar + nested ranges.
        assert_match_report_sidecar_binding_contract(document, request_doc, result_doc)
        # Ownership: event id stays under the same run (kept as explicit guard).
        assert str(document["eventId"]).startswith(f'{document["runId"]}:')


def test_assert_match_report_contract_rejects_identity_range_matcher_and_claims() -> None:
    from test_detail_match_report_contract import _weapon_coexist_detail
    from test_actor_detail_matching import EVENT, RUN, condition
    from gamingcreator.application.detail_query import match_report
    from gamingcreator.domain.actor_details import AttributeKind, QueryConstraint

    query = QueryConstraint((condition(AttributeKind.HELD_CLASS, "weapon", "item"),))
    document = match_report(
        None,
        _weapon_coexist_detail(),
        query,
        run_id=RUN,
        event_id=EVENT,
        request_digest=None,
    )
    assert_match_report_contract(document)

    bad_event = dict(document)
    bad_event["eventId"] = "other-run:media:event:x"
    with pytest.raises(ValueError, match="eventId"):
        assert_match_report_contract(bad_event)

    bad_range = dict(document)
    bad_range["sourceRange"] = {"startUs": 10, "endUs": 10, "durationUs": 100}
    with pytest.raises(ValueError, match="sourceRange"):
        assert_match_report_contract(bad_range)

    bad_matcher = json.loads(json.dumps(document))
    bad_matcher["result"]["matcherVersion"] = "actor-detail-matcher-v1"
    with pytest.raises(ValueError, match="matcherVersion"):
        assert_match_report_contract(bad_matcher)

    bad_status = json.loads(json.dumps(document))
    bad_status["result"]["status"] = "passed"
    with pytest.raises(ValueError, match="status"):
        assert_match_report_contract(bad_status)

    claim = dict(document)
    claim["formalAcceptancePassed"] = True
    with pytest.raises(ValueError, match="formalAcceptancePassed"):
        assert_match_report_contract(claim)

    hash_drift = json.loads(json.dumps(document))
    hash_drift["result"]["constraintHash"] = "0" * 64
    with pytest.raises(ValueError, match="constraintHash"):
        assert_match_report_contract(hash_drift)


def test_match_report_contract_gaps_flags_identity_and_forbidden_claims() -> None:
    files = _require_legacy_matches()
    document = json.loads(files[0].read_text(encoding="utf-8-sig"))
    forged = dict(document)
    forged["eventId"] = "someone-else:media:event:x"
    forged["formalAcceptancePassed"] = True
    forged["sourceRange"] = {"startUs": 5, "endUs": 1, "durationUs": 10}
    gaps = match_report_contract_gaps(forged)
    assert "event_run_mismatch" in gaps
    assert "forbidden_claim:formalAcceptancePassed" in gaps
    assert "source_range_invalid" in gaps


def test_assert_match_report_contract_rejects_match_row_evidence_and_result_versions() -> None:
    """Deeper v1.1 gates: match actor/shot, owned evidenceIds, result/constraint versions."""
    from test_detail_match_report_contract import _weapon_coexist_detail
    from test_actor_detail_matching import EVENT, RUN, condition
    from gamingcreator.application.detail_query import match_report
    from gamingcreator.domain.actor_details import AttributeKind, QueryConstraint

    query = QueryConstraint((condition(AttributeKind.HELD_CLASS, "weapon", "item"),))
    document = match_report(
        None,
        _weapon_coexist_detail(),
        query,
        run_id=RUN,
        event_id=EVENT,
        request_digest=None,
    )
    assert_match_report_contract(document)
    assert match_report_contract_gaps(document) == ()

    bad_actor = json.loads(json.dumps(document, default=str))
    # default=str may stringify enums in constraint — rebuild from fresh copy via match_report fields we mutate on result only
    bad_actor = dict(document)
    bad_actor["result"] = json.loads(json.dumps(document["result"], default=str))
    # Fix enum strings back? result matches uncertain condition may be strings now — re-assert path only mutates actorId
    bad_actor["result"]["matches"][0]["actorId"] = ""
    with pytest.raises(ValueError, match="actorId"):
        assert_match_report_contract(bad_actor)

    bad_shot = dict(document)
    bad_shot["result"] = json.loads(json.dumps(document["result"], default=str))
    bad_shot["result"]["matches"][0]["shotId"] = ""
    with pytest.raises(ValueError, match="shotId"):
        assert_match_report_contract(bad_shot)

    foreign = dict(document)
    foreign["result"] = json.loads(json.dumps(document["result"], default=str))
    # Put a foreign evidence id into sharedEvidenceIds
    foreign["result"]["matches"][0]["sharedEvidenceIds"] = ["other-run:media:image:000001"]
    with pytest.raises(ValueError, match="sharedEvidenceIds"):
        assert_match_report_contract(foreign)

    bad_query_ver = dict(document)
    bad_query_ver["result"] = json.loads(json.dumps(document["result"], default=str))
    bad_query_ver["result"]["queryVersion"] = "actor-detail-query-v0"
    with pytest.raises(ValueError, match="queryVersion"):
        assert_match_report_contract(bad_query_ver)

    bad_constraint = dict(document)
    payload = json.loads(document["constraintJson"])
    del payload["vocabularyVersion"]
    bad_constraint["constraintJson"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    bad_constraint["constraintHash"] = __import__("hashlib").sha256(
        bad_constraint["constraintJson"].encode("utf-8")
    ).hexdigest()
    bad_constraint["result"] = json.loads(json.dumps(document["result"], default=str))
    bad_constraint["result"]["constraintHash"] = bad_constraint["constraintHash"]
    with pytest.raises(ValueError, match="vocabularyVersion"):
        assert_match_report_contract(bad_constraint)


def test_match_report_contract_gaps_flags_match_evidence_and_versions_on_legacy() -> None:
    files = _require_legacy_matches()
    document = json.loads(files[0].read_text(encoding="utf-8-sig"))
    forged = json.loads(json.dumps(document))
    forged["result"]["matches"][0]["sharedEvidenceIds"] = ["foreign-run:media:image:1"]
    forged["result"]["queryVersion"] = "not-current"
    forged["result"]["matches"][0]["actorId"] = ""
    gaps = match_report_contract_gaps(forged)
    assert "match_shared_evidence_invalid" in gaps
    assert "query_version_mismatch" in gaps
    assert "match_actor_id_invalid" in gaps


def _load_first_legacy_binding() -> tuple[dict, dict, dict]:
    path = _require_legacy_matches()[0]
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    request_hash = document["refinementRequestHash"]
    sidecar = list(DEMO_PHASE0.glob(f"**/detail-refinements/{request_hash}/request.json"))[0]
    request_doc = json.loads(sidecar.read_text(encoding="utf-8-sig"))
    result_doc = json.loads(sidecar.with_name("result.json").read_text(encoding="utf-8-sig"))
    return document, request_doc, result_doc


def test_assert_match_report_sidecar_binding_rejects_foreign_evidence_and_range() -> None:
    document, request_doc, result_doc = _load_first_legacy_binding()
    assert_match_report_sidecar_binding_contract(document, request_doc, result_doc)

    forged = json.loads(json.dumps(document))
    matches = forged["result"]["matches"]
    assert matches, "legacy report should have matches"
    # Inject foreign evidence id not present on the sidecar request.
    bucket = None
    for name in ("satisfied", "opposed", "counterEvidence", "uncertain"):
        if matches[0].get(name):
            bucket = name
            break
    assert bucket is not None
    matches[0][bucket][0]["evidenceIds"] = [
        f'{forged["runId"]}:{"a"*64}:evidence:forged-not-on-sidecar'
    ]
    with pytest.raises(ValueError, match="not in sidecar evidence"):
        assert_match_report_sidecar_binding_contract(forged, request_doc, result_doc)

    forged2 = json.loads(json.dumps(document))
    outer = forged2["sourceRange"]
    assert isinstance(outer, dict)
    # Escape the report/sidecar interval.
    forged2["result"]["matches"][0]["sourceRange"] = {
        "startUs": int(outer["startUs"]) - 1_000_000,
        "endUs": int(outer["endUs"]) + 1_000_000,
        "durationUs": int(outer["durationUs"]),
    }
    with pytest.raises(ValueError, match="escapes report"):
        assert_match_report_sidecar_binding_contract(forged2, request_doc, result_doc)


def test_assert_match_report_sidecar_binding_rejects_media_and_payload_drift() -> None:
    document, request_doc, result_doc = _load_first_legacy_binding()
    forged = json.loads(json.dumps(document))
    # Keep run prefix but swap media segment so eventId no longer matches sidecar media.
    run_id = forged["runId"]
    forged["eventId"] = f"{run_id}:{'b'*64}:event:forged"
    with pytest.raises(ValueError, match="mediaSha256"):
        assert_match_report_sidecar_binding_contract(forged, request_doc, result_doc)

    forged_payload = json.loads(json.dumps(document))
    forged_payload["refinementPayloadHash"] = "c" * 64
    with pytest.raises(ValueError, match="payloadHash"):
        assert_match_report_sidecar_binding_contract(forged_payload, request_doc, result_doc)


def test_assert_match_report_contract_rejects_match_source_range_escape() -> None:
    """When report sourceRange is bound, nested match ranges must stay inside."""
    from test_detail_match_report_contract import _weapon_coexist_detail
    from test_actor_detail_matching import EVENT, RUN, condition
    from gamingcreator.application.detail_query import match_report
    from gamingcreator.domain.actor_details import AttributeKind, QueryConstraint

    query = QueryConstraint((condition(AttributeKind.HELD_CLASS, "weapon", "item"),))
    document = match_report(
        None,
        _weapon_coexist_detail(),
        query,
        run_id=RUN,
        event_id=EVENT,
        request_digest=None,
    )
    document["sourceRange"] = {"startUs": 0, "endUs": 1_000_000, "durationUs": 5_000_000}
    # Force an escape on the first match that has / can take a sourceRange.
    row = document["result"]["matches"][0]
    row["sourceRange"] = {"startUs": 0, "endUs": 2_000_000, "durationUs": 5_000_000}
    with pytest.raises(ValueError, match="escapes report range"):
        assert_match_report_contract(document)
