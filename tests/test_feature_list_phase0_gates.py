"""Phase-0 feature_list gates stay false; readiness claims must match."""

from __future__ import annotations

import json
from pathlib import Path

from gamingcreator.application.acceptance_readiness import build_acceptance_readiness
from gamingcreator.application.tasks import TASKS_VERSION

ROOT = Path(__file__).resolve().parents[1]
FEATURE_LIST = ROOT / "feature_list.json"
_GATE_IDS = ("F006", "F009", "F010")


def _tasks() -> dict:
    return {
        "schemaVersion": TASKS_VERSION,
        "tasks": [],
        "total": 0,
        "offset": 0,
        "limit": 100,
        "hasMore": False,
        "ordering": "created-time-descending-then-run-id",
        "snapshotOnly": True,
    }


def test_feature_list_phase0_acceptance_gates_remain_false() -> None:
    payload = json.loads(FEATURE_LIST.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in payload["features"]}
    for feature_id in _GATE_IDS:
        assert feature_id in by_id, feature_id
        assert by_id[feature_id].get("passes") is False, feature_id


def test_acceptance_readiness_feature_claims_match_feature_list_gates() -> None:
    payload = json.loads(FEATURE_LIST.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in payload["features"]}
    doc = build_acceptance_readiness(_tasks())
    claims = doc["featureClaims"]
    for feature_id in _GATE_IDS:
        assert claims[feature_id] is False
        assert by_id[feature_id].get("passes") is False
        assert claims[feature_id] is by_id[feature_id].get("passes")
