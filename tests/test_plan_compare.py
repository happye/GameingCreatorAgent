"""Read-only plan comparison: entry pairing plus actual duration, shot count, and gaps."""

from pathlib import Path

import pytest

from gamingcreator.application import plan_compare
from gamingcreator.application.plan_compare import (
    align_source_shots,
    classify_shot_changes,
    format_exact_us,
    open_plan_comparison,
    plan_side_metrics,
)


def test_open_plan_comparison_returns_readonly_copies():
    left = {
        "id": "guide-steps",
        "structure": "按步骤展开",
        "ready": True,
        "segments": [{"eventId": "0"}],
    }
    right = {
        "id": "hook-first",
        "structure": "最后一条先作开场，再回溯",
        "ready": True,
        "segments": [{"eventId": "1"}],
    }
    pair = open_plan_comparison([left, right], "guide-steps", "hook-first")
    assert pair["schemaVersion"] == "plan-comparison-v1" and pair["readonly"] is True
    assert pair["left"]["id"] == "guide-steps" and pair["right"]["id"] == "hook-first"
    pair["left"]["segments"][0]["eventId"] = "changed"
    assert left["segments"][0]["eventId"] == "0"


def test_open_plan_comparison_rejects_same_or_unknown_or_empty():
    plans = [{"id": "guide-steps"}, {"id": "reverse"}]
    with pytest.raises(ValueError, match="不同"):
        open_plan_comparison(plans, "guide-steps", "guide-steps")
    with pytest.raises(ValueError, match="已经生成"):
        open_plan_comparison(plans, "guide-steps", "hook-first")
    with pytest.raises(ValueError, match="两个已生成"):
        open_plan_comparison(plans, "", "reverse")


def test_plan_compare_module_does_not_call_models_or_proposals():
    source = Path(plan_compare.__file__).read_text(encoding="utf-8")
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert all("plan_proposals" not in line and "openai" not in line for line in imports)
    pair = open_plan_comparison(
        [{"id": "a", "segments": []}, {"id": "b", "segments": []}], "a", "b"
    )
    assert pair["readonly"] is True
    assert "score" not in pair and "adopted" not in pair


SAME_SEGMENTS = [
    {"sourceSha256": "aa", "startUs": 0, "endUs": 2_000_000, "outputFrames": 60},
    {"sourceSha256": "bb", "startUs": 0, "endUs": 2_000_000, "outputFrames": 60},
]


def test_metrics_come_from_actual_segments_not_template_names():
    left = {
        "id": "guide-steps",
        "structure": "按步骤展开",
        "ready": True,
        "segments": SAME_SEGMENTS,
        "gaps": [],
    }
    right = {
        "id": "hook-first",
        "structure": "最后一条先作开场，再回溯",
        "ready": True,
        "segments": SAME_SEGMENTS,
        "gaps": [],
    }
    pair = open_plan_comparison([left, right], "guide-steps", "hook-first", fps=30)
    assert pair["leftMetrics"] == pair["rightMetrics"]
    assert pair["leftMetrics"]["totalFrames"] == 120
    assert pair["leftMetrics"]["durationSeconds"] == 4.0
    assert pair["leftMetrics"]["shotCount"] == 2
    assert pair["leftMetrics"]["gaps"] == []


def test_metrics_stay_unknown_when_fields_are_missing():
    left = {"id": "a"}
    right = {
        "id": "b",
        "segments": [{"sourceSha256": "x", "startUs": 0, "endUs": 1_000_000, "outputFrames": 30}],
        "gaps": ["不足三个不同源区间，不能形成完整的三段结构"],
    }
    pair = open_plan_comparison([left, right], "a", "b")
    assert pair["leftMetrics"] == {
        "totalFrames": None,
        "durationSeconds": None,
        "shotCount": None,
        "gaps": None,
    }
    assert pair["rightMetrics"]["totalFrames"] == 30
    assert pair["rightMetrics"]["durationSeconds"] is None
    assert pair["rightMetrics"]["shotCount"] == 1
    assert pair["rightMetrics"]["gaps"] == ["不足三个不同源区间，不能形成完整的三段结构"]
    assert "fps" not in pair


def test_contiguous_same_source_counts_as_one_shot():
    segments = [
        {"sourceSha256": "aa", "startUs": 0, "endUs": 1_000_000, "outputFrames": 30},
        {"sourceSha256": "aa", "startUs": 1_000_000, "endUs": 2_000_000, "outputFrames": 30},
    ]
    metrics = plan_side_metrics({"segments": segments, "gaps": []}, fps=30)
    assert metrics["shotCount"] == 1
    assert metrics["totalFrames"] == 60
    assert metrics["durationSeconds"] == 2.0


def test_missing_output_frames_stay_unknown_instead_of_zero():
    metrics = plan_side_metrics(
        {"segments": [{"outputFrames": 30}, {"sourceSha256": "x"}], "gaps": []}
    )
    assert metrics["totalFrames"] is None
    assert metrics["durationSeconds"] is None
    assert metrics["shotCount"] == 2


def _seg(sha, start, end, frames, run="run-1", role=None, script=None):
    row = {
        "runId": run,
        "sourceSha256": sha,
        "startUs": start,
        "endUs": end,
        "outputFrames": frames,
    }
    if role is not None:
        row["role"] = role
    if script is not None:
        row["scriptDraft"] = script
    return row


def test_aligns_same_source_by_identity_and_shows_output_positions():
    left = [
        _seg("aa", 0, 2_000_000, 60),
        _seg("bb", 0, 2_000_000, 60),
        _seg("cc", 0, 2_000_000, 60),
    ]
    right = [
        _seg("cc", 0, 2_000_000, 60),
        _seg("aa", 0, 2_000_000, 60),
        _seg("bb", 0, 2_000_000, 60),
    ]
    rows = align_source_shots(left, right, fps=30)
    assert [row["sourceSha256"] for row in rows] == ["aa", "bb", "cc"]
    assert rows[0]["left"] == {
        "shotIndex": 1,
        "startFrame": 0,
        "endFrame": 60,
        "startSeconds": 0.0,
        "endSeconds": 2.0,
    }
    assert rows[0]["right"]["shotIndex"] == 2
    assert rows[0]["right"]["startSeconds"] == 2.0
    assert rows[0]["right"]["endSeconds"] == 4.0
    assert rows[2]["left"]["shotIndex"] == 3
    assert rows[2]["right"]["shotIndex"] == 1
    assert rows[2]["right"]["startSeconds"] == 0.0


def test_alignment_ignores_role_and_script_wording():
    left = [_seg("aa", 0, 2_000_000, 60, role="开场", script="先讲玩法")]
    right = [_seg("aa", 0, 2_000_000, 60, role="收尾", script="完全不同的说明")]
    rows = align_source_shots(left, right, fps=30)
    assert len(rows) == 1 and rows[0]["left"] and rows[0]["right"]


def test_alignment_does_not_pair_by_role_when_sources_differ():
    left = [_seg("aa", 0, 2_000_000, 60, role="开场")]
    right = [_seg("bb", 0, 2_000_000, 60, role="开场")]
    rows = align_source_shots(left, right, fps=30)
    assert rows[0]["sourceSha256"] == "aa" and rows[0]["right"] is None
    assert rows[1]["sourceSha256"] == "bb" and rows[1]["left"] is None


def test_alignment_does_not_pair_unknown_identities_together():
    left = [{"outputFrames": 60, "role": "开场"}]
    right = [{"outputFrames": 60, "role": "开场"}]
    rows = align_source_shots(left, right, fps=30)
    assert rows[0]["sourceSha256"] is None and rows[0]["right"] is None
    assert rows[1]["sourceSha256"] is None and rows[1]["left"] is None


def test_alignment_requires_run_and_hash():
    left = [_seg("aa", 0, 2_000_000, 60, run="run-1")]
    right = [_seg("aa", 0, 2_000_000, 60, run="run-2")]
    rows = align_source_shots(left, right, fps=30)
    assert rows[0]["runId"] == "run-1" and rows[0]["right"] is None
    assert rows[1]["runId"] == "run-2" and rows[1]["left"] is None


def test_alignment_merges_contiguous_same_source_as_one_shot():
    left = [_seg("aa", 0, 1_000_000, 30), _seg("aa", 1_000_000, 2_000_000, 30)]
    right = [_seg("aa", 0, 2_000_000, 60)]
    rows = align_source_shots(left, right, fps=30)
    assert len(rows) == 1
    assert rows[0]["left"]["shotIndex"] == 1
    assert rows[0]["left"]["endFrame"] == 60
    assert rows[0]["left"]["endSeconds"] == 2.0
    assert rows[0]["right"]["shotIndex"] == 1


def test_shot_changes_mark_added_missing_and_reordered():
    left = [
        _seg("aa", 0, 2_000_000, 60),
        _seg("bb", 0, 2_000_000, 60),
        _seg("cc", 0, 2_000_000, 60),
    ]
    right = [_seg("cc", 0, 2_000_000, 60), _seg("aa", 0, 2_000_000, 60)]
    rows = classify_shot_changes(left, right, fps=30)
    by_sha = {row["sourceSha256"]: row for row in rows}
    assert by_sha["aa"]["status"] == "reordered"
    assert by_sha["bb"]["status"] == "missing" and by_sha["bb"]["right"] is None
    assert by_sha["cc"]["status"] == "reordered"
    assert by_sha["aa"]["left"]["shotIndex"] == 1
    assert by_sha["aa"]["right"]["shotIndex"] == 2


def test_same_footage_different_intervals_are_compared_separately():
    left = [_seg("aa", 0, 2_000_000, 60)]
    right = [_seg("aa", 1_000_000, 3_000_000, 60)]
    rows = classify_shot_changes(left, right, fps=30)
    assert len(rows) == 2
    assert rows[0]["status"] == "missing"
    assert rows[0]["startUs"] == 0 and rows[0]["endUs"] == 2_000_000
    assert rows[1]["status"] == "added"
    assert rows[1]["startUs"] == 1_000_000 and rows[1]["endUs"] == 3_000_000


def test_duplicate_event_ids_are_not_treated_as_the_same_shot():
    left = [_seg("aa", 0, 2_000_000, 60)]
    right = [_seg("bb", 0, 2_000_000, 60)]
    left[0]["eventId"] = "clip-1"
    right[0]["eventId"] = "clip-1"
    left[0]["id"] = "same"
    right[0]["id"] = "same"
    rows = classify_shot_changes(left, right, fps=30)
    assert rows[0]["status"] == "missing" and rows[0]["sourceSha256"] == "aa"
    assert rows[1]["status"] == "added" and rows[1]["sourceSha256"] == "bb"


def test_same_interval_stays_same_even_with_different_ids():
    left = [_seg("aa", 0, 2_000_000, 60)]
    right = [_seg("aa", 0, 2_000_000, 60)]
    left[0]["eventId"] = "left-id"
    right[0]["eventId"] = "right-id"
    rows = classify_shot_changes(left, right, fps=30)
    assert len(rows) == 1 and rows[0]["status"] == "same"


def test_shot_changes_unknown_when_interval_is_missing():
    rows = classify_shot_changes(
        [{"outputFrames": 60, "eventId": "1"}], [{"outputFrames": 60, "eventId": "1"}], fps=30
    )
    assert rows[0]["status"] == "unknown" and rows[0]["right"] is None
    assert rows[1]["status"] == "unknown" and rows[1]["left"] is None


def test_trim_and_speed_keep_exact_fractions_without_rounding():
    assert format_exact_us(2_000_000) == "2000000 微秒（2 秒）"
    assert format_exact_us(2_000_001) == "2000001 微秒（2000001/1000000 秒）"
    assert "2.0" not in format_exact_us(2_000_001)
    left = [_seg("aa", 0, 2_000_000, 60)]
    right = [_seg("aa", 0, 2_000_000, 61)]
    rows = classify_shot_changes(left, right, fps=30)
    assert len(rows) == 1
    assert rows[0]["leftTrim"]["speed"] == "1"
    assert rows[0]["rightTrim"]["speed"] == "60/61"
    assert rows[0]["leftTrim"]["sourceUs"] == 2_000_000
    assert rows[0]["rightTrim"]["outputFrames"] == 61
    # A 1-microsecond crop change must stay visible as itself, not as 2.0 seconds.
    split = classify_shot_changes(
        [_seg("aa", 0, 2_000_000, 60)],
        [_seg("aa", 0, 2_000_001, 60)],
        fps=30,
    )
    assert split[0]["endUs"] == 2_000_000 and split[1]["endUs"] == 2_000_001
    assert split[0]["leftTrim"]["speed"] == "1"
    assert split[1]["rightTrim"]["speed"] == "2000001/2000000"


def test_theme_reasons_show_recorded_values_and_say_missing_without_inventing():
    left = {
        "id": "guide-steps",
        "structure": "按步骤展开",
        "ready": True,
        "segments": [
            {
                "sourceSha256": "aa",
                "startUs": 0,
                "endUs": 2_000_000,
                "outputFrames": 60,
                "scriptDraft": "角色在草地上奔跑",
                "topicUses": [
                    {
                        "topic": "玩法展示",
                        "rationale": "用开场操作说明核心玩法",
                        "observationQuote": "角色在草地上奔跑",
                    }
                ],
            }
        ],
        "gaps": [],
    }
    right = {
        "id": "reverse",
        "structure": "倒序逐条回顾",
        "ready": True,
        "segments": [
            {
                "sourceSha256": "aa",
                "startUs": 0,
                "endUs": 2_000_000,
                "outputFrames": 60,
                "scriptDraft": "角色在草地上奔跑",
            }
        ],
        "gaps": [],
    }
    pair = open_plan_comparison([left, right], "guide-steps", "reverse")
    assert pair["leftThemeReasons"] == {
        "provided": True,
        "uses": [
            {
                "shotIndex": 1,
                "topic": "玩法展示",
                "rationale": "用开场操作说明核心玩法",
                "observationQuote": "角色在草地上奔跑",
            }
        ],
    }
    assert pair["rightThemeReasons"] == {"provided": False, "uses": []}
    # Missing fields stay missing; scriptDraft and the template name must not be filled in as a reason.
    partial = {
        "id": "hook-first",
        "structure": "最后一条先作开场，再回溯",
        "segments": [
            {
                "sourceSha256": "aa",
                "startUs": 0,
                "endUs": 2_000_000,
                "outputFrames": 60,
                "scriptDraft": "角色在草地上奔跑",
                "topicUses": [
                    {"topic": "玩法展示", "rationale": "只有理由", "observationQuote": ""}
                ],
            }
        ],
    }
    partial_pair = open_plan_comparison([left, partial], "guide-steps", "hook-first")
    assert partial_pair["rightThemeReasons"]["uses"] == [
        {
            "shotIndex": 1,
            "topic": "玩法展示",
            "rationale": "只有理由",
            "observationQuote": None,
        }
    ]


def _export_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _export_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _export_keys(item)


def test_comparison_export_contains_only_diffs_and_sources_without_writing_back(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    left = {
        "id": "guide-steps",
        "structure": "按步骤展开",
        "contentSignature": "sig-left",
        "ready": True,
        "score": 9.9,
        "segments": [
            {
                "runId": "run-1",
                "sourceSha256": "aa",
                "startUs": 0,
                "endUs": 2_000_000,
                "outputFrames": 60,
                "eventId": "clip-1",
                "scriptDraft": "角色在草地上奔跑",
                "topicUses": [
                    {
                        "topic": "玩法展示",
                        "rationale": "用开场操作说明核心玩法",
                        "observationQuote": "角色在草地上奔跑",
                    }
                ],
            },
            {
                "runId": "run-1",
                "sourceSha256": "bb",
                "startUs": 0,
                "endUs": 2_000_000,
                "outputFrames": 60,
            },
        ],
        "gaps": [],
    }
    right = {
        "id": "hook-first",
        "structure": "最后一条先作开场，再回溯",
        "contentSignature": "sig-right",
        "ready": True,
        "segments": [
            {
                "runId": "run-1",
                "sourceSha256": "bb",
                "startUs": 0,
                "endUs": 2_000_000,
                "outputFrames": 60,
            },
            {
                "runId": "run-1",
                "sourceSha256": "aa",
                "startUs": 0,
                "endUs": 2_000_000,
                "outputFrames": 60,
            },
        ],
        "gaps": [],
    }
    pair = open_plan_comparison([left, right], "guide-steps", "hook-first", fps=30)
    exported = plan_compare.comparison_export_document(pair)
    assert exported["schemaVersion"] == "plan-comparison-export-v1"
    assert exported["readonly"] is True
    assert exported["note"] == "只包含这次对照的差异和来源，不会写回报告、证据或偏好。"
    assert exported["fps"] == 30
    assert exported["left"]["planId"] == "guide-steps"
    assert exported["right"]["planId"] == "hook-first"
    assert exported["left"]["contentSignature"] == "sig-left"
    assert exported["right"]["contentSignature"] == "sig-right"
    assert exported["left"]["metrics"]["totalFrames"] == 120
    assert exported["left"]["themeReasons"]["provided"] is True
    assert exported["right"]["themeReasons"] == {"provided": False, "uses": []}
    assert {row["sourceSha256"] for row in exported["sources"]} == {"aa", "bb"}
    assert all(
        "startUs" in row and "endUs" in row and "runId" in row for row in exported["sources"]
    )
    assert exported["shotChanges"]
    assert any(row["status"] == "reordered" for row in exported["shotChanges"])
    allowed = {
        "schemaVersion",
        "readonly",
        "note",
        "fps",
        "left",
        "right",
        "planId",
        "contentSignature",
        "metrics",
        "themeReasons",
        "provided",
        "uses",
        "shotIndex",
        "topic",
        "rationale",
        "observationQuote",
        "totalFrames",
        "durationSeconds",
        "shotCount",
        "gaps",
        "sources",
        "sourceAlignment",
        "shotChanges",
        "runId",
        "sourceSha256",
        "startUs",
        "endUs",
        "status",
        "leftTrim",
        "rightTrim",
        "sourceUs",
        "outputFrames",
        "outputUs",
        "speed",
        "startFrame",
        "endFrame",
        "startSeconds",
        "endSeconds",
    }
    keys = set(_export_keys(exported))
    assert keys <= allowed
    blocked = {
        "score",
        "scriptDraft",
        "structure",
        "eventId",
        "mediaId",
        "sourcePath",
        "segments",
        "preference",
        "preferences",
        "evidence",
        "evidenceId",
        "report",
        "reports",
        "cost",
        "apiKey",
        "adopted",
        "secret",
    }
    assert keys.isdisjoint(blocked)
    exported["left"]["planId"] = "changed"
    exported["shotChanges"][0]["status"] = "changed"
    assert pair["left"]["id"] == "guide-steps"
    assert pair["shotChanges"][0]["status"] != "changed"
    assert (
        plan_compare.comparison_export_filename(pair)
        == "plan-comparison-guide-steps-hook-first.json"
    )
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError, match="已经打开的只读对照"):
        plan_compare.comparison_export_document({"left": left, "right": right})
