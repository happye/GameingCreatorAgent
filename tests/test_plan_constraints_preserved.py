"""D04: mode templates, observation ranges, dedup, frame budgets, and old saved bytes stay put."""

import pytest
from test_creation_modes import brief, material
from test_creation_planner import brief as guide_brief
from test_creation_planner import clips
from test_selected_clip_ranges import candidates, ranges, timeline

from gamingcreator.application.creative_planner import (
    overlaps_observation,
    plan_creation,
)
from gamingcreator.cli.creation_render import read_creation
from gamingcreator.infrastructure.creation_files import write_creation

MODE_TEMPLATES = {
    "feature_showcase": ("showcase", "玩法展示"),
    "guide": ("guide-steps", "攻略"),
    "campaign": ("campaign-topics", "活动投稿"),
    "commentary": ("commentary-segments", "游戏解说"),
    "live_cut": ("live-cut", "实况精剪"),
    "highlight": ("highlight-climax", "高光"),
    "ad": ("ad-hook", "广告/买量"),
}


def _mode_clips():
    facts = [[f"片段{i}"] for i in range(20)]
    facts[3] = ["角色跳跃", "空中旋转", "落地特效"]
    facts[12] = ["新英雄登场", "技能展示"]
    facts[15] = ["限时活动入口"]
    return material(facts)


def _mode_report(kind):
    duration = 6 if kind == "highlight" else 15 if kind in {"commentary", "live_cut", "ad"} else 12
    topics = ("新英雄",) if kind == "ad" else ("限时活动",) if kind == "campaign" else ()
    return plan_creation(brief(kind, duration=duration, topics=topics), _mode_clips(), 30), duration


def test_all_seven_modes_keep_their_own_template_first():
    assert set(MODE_TEMPLATES) == {
        "feature_showcase",
        "guide",
        "campaign",
        "commentary",
        "live_cut",
        "highlight",
        "ad",
    }
    for kind, (identity, label) in MODE_TEMPLATES.items():
        report, duration = _mode_report(kind)
        plan = report["plans"][0]
        assert plan["id"] == identity
        assert plan["mode"] == kind and plan["modeLabel"] == label
        assert any(p["id"] == identity for p in report["plans"])
        budget = duration * 30
        for row in report["plans"]:
            assert sum(segment["outputFrames"] for segment in row["segments"]) <= budget


def test_source_observation_stays_inside_selected_ranges():
    saved = timeline(clips()[0].asset, False)
    selected = [
        {**row, "startUs": 0, "endUs": (i + 3) * 5_000_000} for i, row in enumerate(ranges())
    ]
    report = plan_creation(guide_brief(), candidates((saved,), ("0", "1", "2"), selected), 30)
    for plan in report["plans"]:
        for segment in plan["segments"]:
            proven = segment["rangeProvenance"]
            event = saved.events[int(segment["eventId"])]
            assert proven["analysisStartUs"] == event.source_range.start_us
            assert proven["analysisEndUs"] == event.source_range.end_us
            assert overlaps_observation(
                segment["startUs"],
                segment["endUs"],
                proven["analysisStartUs"],
                proven["analysisEndUs"],
                event.source_range.duration_us,
            )


def test_dedup_and_budgets_do_not_pad_or_shrink_the_target():
    short = plan_creation(guide_brief(), clips()[:1], 30)
    assert len(short["plans"]) == 1
    assert short["plans"][0]["segments"][0]["outputFrames"] == 90
    full = plan_creation(guide_brief(), clips(), 30)
    signatures = [plan["contentSignature"] for plan in full["plans"]]
    assert len(signatures) == len(set(signatures)) == 3
    assert "chronological" not in [plan["id"] for plan in full["plans"]]
    assert all(
        sum(segment["outputFrames"] for segment in plan["segments"]) <= 180
        for plan in full["plans"]
    )


def test_old_saved_version_bytes_stay_unchanged(tmp_path):
    old_report = {
        "schemaVersion": "creation-plan-v1",
        "planner": "offline-template-v1",
        "plans": [
            {
                "id": "chronological",
                "structure": "按来源顺序展开",
                "segments": [],
                "ready": False,
                "gaps": ["旧缺口"],
                "advisories": [],
            }
        ],
    }
    old_edl = {"schemaVersion": "edit-decision-v1", "planId": "chronological", "segments": []}
    directory = tmp_path / "old-version"
    write_creation(directory, {"plans.json": old_report, "edit-decision.json": old_edl}, ())
    before = {
        name: (directory / name).read_bytes()
        for name in ("plans.json", "edit-decision.json", "receipt.json")
    }
    assert b"contentSignature" not in before["plans.json"]
    assert b"candidateCountReason" not in before["plans.json"]
    loaded, plans, _receipt = read_creation(directory)
    assert loaded == old_edl and plans == old_report
    plan_creation(guide_brief(), clips(), 30)
    with pytest.raises(FileExistsError):
        write_creation(
            directory,
            {"plans.json": {"schemaVersion": "changed"}, "edit-decision.json": old_edl},
            (),
        )
    after = {
        name: (directory / name).read_bytes()
        for name in ("plans.json", "edit-decision.json", "receipt.json")
    }
    assert after == before
