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