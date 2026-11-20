"""Honest candidate counts when there is not enough distinct material for three plans."""

from dataclasses import replace

from test_creation_modes import brief as mode_brief
from test_creation_modes import material
from test_creation_planner import brief, clips

from gamingcreator.application.creative_planner import (
    candidate_count_reason,
    plan_creation,
)

NO_PAD = "不会用重复画面、缩短时长或丢掉观察点来凑满 3 套。"


def test_one_clip_keeps_one_plan_and_explains():
    report = plan_creation(brief(), clips()[:1], 30)
    assert [plan["id"] for plan in report["plans"]] == ["guide-steps"]
    assert report["candidateCountReason"] == (
        f"可用素材只有 1 条不同内容，最多只能给出 1 套方案。{NO_PAD}"
    )
    plan = report["plans"][0]
    assert len(plan["segments"]) == 1
    assert plan["segments"][0]["outputFrames"] == 90


def test_two_clips_keep_at_most_two_plans_and_explain():
    report = plan_creation(brief(), clips()[:2], 30)
    ids = [plan["id"] for plan in report["plans"]]
    assert ids == ["guide-steps", "hook-first"]
    assert len({plan["contentSignature"] for plan in report["plans"]}) == 2
    assert report["candidateCountReason"] == (
        f"可用素材只有 2 条不同内容，最多只能给出 2 套方案。{NO_PAD}"
    )


def test_three_distinct_clips_have_three_plans_and_no_shortage_reason():
    report = plan_creation(brief(), clips(), 30)
    assert len(report["plans"]) == 3
    assert len({plan["contentSignature"] for plan in report["plans"]}) == 3
    assert "candidateCountReason" not in report


def test_same_interval_across_runs_counts_as_one_source():
    clip = clips()[0]
    versions = tuple(
        replace(clip, event=replace(clip.event, run_id=f"run{i}", event_id=f"event{i}"))
        for i in range(3)
    )
    report = plan_creation(brief(), versions, 30)
    assert len(report["plans"]) == 1
    assert report["candidateCountReason"] == (
        f"可用素材只有 1 条不同内容，最多只能给出 1 套方案。{NO_PAD}"
    )


def test_excluded_material_explains_zero_usable_sources():
    report = plan_creation(replace(brief(), exclude=("fact",)), clips(), 30)
    assert len(report["plans"]) == 1
    assert report["plans"][0]["segments"] == []
    assert report["candidateCountReason"] == (
        f"没有可用的不同素材，所以现在只有 1 套方案。{NO_PAD}"
    )


def test_showcase_with_distinct_content_has_no_shortage_reason():
    facts = [
        ["角色奔跑"],
        ["角色跳跃", "空中旋转", "落地特效"],
        ["开门"],
        ["拾取道具"],
        ["结算画面"],
    ]
    report = plan_creation(mode_brief("feature_showcase"), material(facts), 30)
    assert [plan["id"] for plan in report["plans"]] == [
        "showcase",
        "chronological",
        "hook-first",
        "reverse",
    ]
    assert "candidateCountReason" not in report


def test_reason_helper_uses_dedup_wording_when_material_was_enough():
    plans = [{"id": "a"}, {"id": "b"}]
    assert candidate_count_reason(plans, 3) == (
        f"按最终可渲染内容去重后只剩 2 套不同方案。{NO_PAD}"
    )
    assert candidate_count_reason(plans + [{"id": "c"}], 3) is None
