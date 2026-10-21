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
        assert request_doc["requestHash"] == request_hash
        assert request_doc["runId"] == document["runId"]
        assert request_doc["eventFingerprint"] == document["eventFingerprint"]
        canonical = json.loads(request_doc["canonicalJson"])
        assert canonical.get("candidateId") == document.get("candidateId")
        assert canonical.get("interval") == document.get("sourceRange")
        result_path = sidecars[0].with_name("result.json")
        assert result_path.is_file(), path.name
        result_doc = json.loads(result_path.read_text(encoding="utf-8-sig"))
        assert result_doc.get("payloadHash") == payload_hash
        # Ownership: event id stays under the same run.
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
