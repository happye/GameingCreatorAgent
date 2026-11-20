"""D02: drop rule plans that share a final content signature, keep preference order."""

from __future__ import annotations

from test_creation_modes import brief, material
from test_creation_planner import brief as guide_brief
from test_creation_planner import clips
from test_plan_content_signature import _row

from gamingcreator.application.creative_planner import (
    plan_content_signature,
    plan_creation,
    unique_rule_plans,
)


def test_unique_rule_plans_keeps_first_and_leaves_distinct_content():
    first = {"id": "preferred", "contentSignature": "aaa"}
    duplicate = {"id": "later", "contentSignature": "aaa"}
    other = {"id": "other", "contentSignature": "bbb"}
    assert [plan["id"] for plan in unique_rule_plans([first, duplicate, other])] == [
        "preferred",
        "other",
    ]


def test_generated_guide_plans_drop_duplicate_chronological_and_keep_order():
    report = plan_creation(guide_brief(), clips(), 30)
    ids = [plan["id"] for plan in report["plans"]]
    signatures = [plan["contentSignature"] for plan in report["plans"]]
    assert len(set(signatures)) == len(signatures)
    assert ids[0] == "guide-steps"
    assert "hook-first" in ids and "reverse" in ids
    # The mode plan already occupies the chronological source order; do not keep a twin.
    assert "chronological" not in ids
    assert signatures[0] == plan_content_signature(report["plans"][0]["segments"])


def test_distinct_mode_and_generic_plans_all_remain():
    facts = [
        ["角色奔跑"],
        ["角色跳跃", "空中旋转", "落地特效"],
        ["开门"],
        ["拾取道具"],
        ["结算画面"],
    ]
    report = plan_creation(brief("feature_showcase"), material(facts), 30)
    ids = [plan["id"] for plan in report["plans"]]
    assert ids == ["showcase", "chronological", "hook-first", "reverse"]
    assert len({plan["contentSignature"] for plan in report["plans"]}) == 4


def test_preference_order_is_kept_when_dropping_a_duplicate():
    preferred = {
        "id": "hook-first",
        "contentSignature": plan_content_signature(
            [_row(), _row(start=1_000_000, end=2_000_000, frames=15)]
        ),
    }
    later = {
        "id": "chronological",
        "contentSignature": preferred["contentSignature"],
    }
    distinct = {
        "id": "reverse",
        "contentSignature": plan_content_signature(
            [_row(start=1_000_000, end=2_000_000, frames=15), _row()]
        ),
    }
    assert [plan["id"] for plan in unique_rule_plans([preferred, later, distinct])] == [
        "hook-first",
        "reverse",
    ]
