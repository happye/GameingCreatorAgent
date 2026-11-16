"""Check real plan EDLs against comparison diffs, including concatenable ranges."""

from dataclasses import replace

import pytest
from test_creation_planner import brief, clips

from gamingcreator.application.creative_planner import plan_creation
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.plan_compare import (
    align_source_shots,
    list_source_shots,
    open_plan_comparison,
    plan_side_metrics,
)


def _interval(segment):
    return (segment["runId"], segment["sourceSha256"], segment["startUs"], segment["endUs"])


def _index_map(segments):
    return {_interval(segment): index for index, segment in enumerate(segments, 1)}


def _assert_changes_match_edl(left_segments, right_segments, changes):
    left_map = _index_map(left_segments)
    right_map = _index_map(right_segments)
    assert changes is not None
    seen = {(row["runId"], row["sourceSha256"], row["startUs"], row["endUs"]) for row in changes}
    assert seen == set(left_map) | set(right_map)
    for row in changes:
        key = (row["runId"], row["sourceSha256"], row["startUs"], row["endUs"])
        left_index = left_map.get(key)
        right_index = right_map.get(key)
        if left_index and right_index:
            assert row["left"]["shotIndex"] == left_index
            assert row["right"]["shotIndex"] == right_index
            assert row["status"] == ("same" if left_index == right_index else "reordered")
        elif left_index:
            assert row["right"] is None
            assert row["status"] == "missing"
        else:
            assert row["left"] is None
            assert row["status"] == "added"


def test_one_clip_keeps_draft_edl_and_cannot_open_compare():
    report = plan_creation(brief(), clips()[:1], 30)
    assert [plan["id"] for plan in report["plans"]] == ["guide-steps"]
    plan = report["plans"][0]
    assert [(_interval(segment), segment["outputFrames"]) for segment in plan["segments"]] == [
        (("run", "a" * 64, 0, 3_000_000), 90)
    ]
    with pytest.raises(ValueError, match="gaps"):
        select_edit_decision(report, plan["id"])
    assert len(report["plans"]) == 1


def test_two_adjacent_clips_keep_separate_edl_intervals_and_do_not_claim_source_missing():
    report = plan_creation(brief(), clips()[:2], 30)
    assert [plan["id"] for plan in report["plans"]] == ["guide-steps", "hook-first"]
    left, right = report["plans"]
    assert [(_interval(segment), segment["outputFrames"]) for segment in left["segments"]] == [
        (("run", "a" * 64, 0, 3_000_000), 90),
        (("run", "a" * 64, 3_000_000, 6_000_000), 90),
    ]
    assert [(_interval(segment), segment["outputFrames"]) for segment in right["segments"]] == [
        (("run", "a" * 64, 3_000_000, 6_000_000), 90),
        (("run", "a" * 64, 0, 3_000_000), 90),
    ]
    for plan in report["plans"]:
        with pytest.raises(ValueError, match="gaps"):
            select_edit_decision(report, plan["id"])
    # Adjacent ranges stay two EDL cuts; only source-shot metrics may merge them.
    assert len(list_source_shots(left["segments"])) == 1
    assert len(list_source_shots(right["segments"])) == 2
    pair = open_plan_comparison(report["plans"], left["id"], right["id"], fps=30)
    _assert_changes_match_edl(left["segments"], right["segments"], pair["shotChanges"])
    assert all(row["status"] == "reordered" for row in pair["shotChanges"])
    assert pair["leftMetrics"]["shotCount"] == 1
    assert pair["rightMetrics"]["shotCount"] == 2
    assert {row.get("reason") for row in pair["sourceAlignment"]} == {"split"}
    assert all(row["left"] is None or row["right"] is None for row in pair["sourceAlignment"])
    assert all(row["sourceSha256"] == "a" * 64 for row in pair["sourceAlignment"])


def test_three_distinct_clips_official_edl_matches_shot_changes():
    report = plan_creation(brief(), clips(), 30)
    assert [plan["id"] for plan in report["plans"]] == ["guide-steps", "hook-first", "reverse"]
    decisions = {plan["id"]: select_edit_decision(report, plan["id"]) for plan in report["plans"]}
    for plan in report["plans"]:
        assert decisions[plan["id"]]["segments"] == plan["segments"]
        assert decisions[plan["id"]]["schemaVersion"] == "edit-decision-v1"
        assert plan["ready"] is True
    pair = open_plan_comparison(report["plans"], "guide-steps", "hook-first", fps=30)
    _assert_changes_match_edl(
        decisions["guide-steps"]["segments"],
        decisions["hook-first"]["segments"],
        pair["shotChanges"],
    )
    reverse_pair = open_plan_comparison(report["plans"], "guide-steps", "reverse", fps=30)
    _assert_changes_match_edl(
        decisions["guide-steps"]["segments"],
        decisions["reverse"]["segments"],
        reverse_pair["shotChanges"],
    )


def test_concatenable_three_clips_keep_interval_edl_and_mark_split_alignment():
    report = plan_creation(replace(brief(), target_duration=9), clips(), 30)
    left = next(plan for plan in report["plans"] if plan["id"] == "guide-steps")
    right = next(plan for plan in report["plans"] if plan["id"] == "hook-first")
    left_edl = select_edit_decision(report, left["id"])["segments"]
    right_edl = select_edit_decision(report, right["id"])["segments"]
    assert [(_interval(segment), segment["outputFrames"]) for segment in left_edl] == [
        (("run", "a" * 64, 0, 3_000_000), 90),
        (("run", "a" * 64, 3_000_000, 6_000_000), 90),
        (("run", "a" * 64, 6_000_000, 9_000_000), 90),
    ]
    assert [(_interval(segment), segment["outputFrames"]) for segment in right_edl] == [
        (("run", "a" * 64, 6_000_000, 9_000_000), 90),
        (("run", "a" * 64, 0, 3_000_000), 90),
        (("run", "a" * 64, 3_000_000, 6_000_000), 90),
    ]
    assert len(list_source_shots(left_edl)) == 1
    assert len(list_source_shots(right_edl)) == 2
    pair = open_plan_comparison(report["plans"], "guide-steps", "hook-first", fps=30)
    _assert_changes_match_edl(left_edl, right_edl, pair["shotChanges"])
    assert plan_side_metrics(left, 30)["shotCount"] == 1
    assert plan_side_metrics(right, 30)["shotCount"] == 2
    assert {row.get("reason") for row in pair["sourceAlignment"]} == {"split"}


def test_alignment_split_does_not_pair_merged_shot_with_only_the_first_piece():
    left = [
        {
            "runId": "run-1",
            "sourceSha256": "aa",
            "startUs": 0,
            "endUs": 1_000_000,
            "outputFrames": 30,
        },
        {
            "runId": "run-1",
            "sourceSha256": "aa",
            "startUs": 1_000_000,
            "endUs": 2_000_000,
            "outputFrames": 30,
        },
    ]
    right = list(reversed(left))
    rows = align_source_shots(left, right, fps=30)
    assert len(list_source_shots(left)) == 1
    assert len(list_source_shots(right)) == 2
    assert all(row.get("reason") == "split" for row in rows)
    assert rows[0]["left"]["endFrame"] == 60 and rows[0]["right"] is None
    assert [row["right"]["shotIndex"] for row in rows if row["right"]] == [1, 2]
    missing = align_source_shots(
        left,
        [
            {
                "runId": "run-1",
                "sourceSha256": "bb",
                "startUs": 0,
                "endUs": 2_000_000,
                "outputFrames": 60,
            }
        ],
        fps=30,
    )
    assert missing[0]["right"] is None and "reason" not in missing[0]
    assert missing[1]["left"] is None and "reason" not in missing[1]
