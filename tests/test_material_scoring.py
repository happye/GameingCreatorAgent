"""Material scores follow the master-plan weights and never invent unmeasured dimensions."""

from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.creative_planner import CreationClip, plan_creation
from gamingcreator.application.material_scoring import WEIGHTS, advisories, score_materials
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.time import SourceRange


def asset(sha="a"):
    return MediaAsset(
        "media" + sha,
        Path(f"{sha}.mp4"),
        sha * 64,
        (MediaStream(0, "video", Fraction(1, 1), 0, 120),),
        Fraction(0),
        120_000_000,
        "probe",
    )


def clip(index, facts, seconds=4, tags=(), uncertainty=None, source=None):
    source = source or asset()
    start = index * 4_000_000
    return CreationClip(
        source,
        SemanticEvent(
            f"e{index}",
            source.media_id,
            "run",
            SourceRange(start, start + int(seconds * 1_000_000), 120_000_000),
            tuple(facts),
            tuple(tags),
            (f"evidence{index}",),
            "visual",
            uncertainty,
        ),
    )


def brief(topics=(), duration=12):
    return CreativeBrief(
        "游戏", "feature_showcase", ("bilibili",), duration, "目标", "新玩家", "简洁", topics, ()
    )


def test_weights_match_master_plan_and_sum_to_one():
    assert sum(WEIGHTS.values()) == 1
    assert WEIGHTS["briefMatch"] == Fraction(1, 4) and WEIGHTS["technicalQuality"] == Fraction(
        1, 20
    )


def test_unmeasured_dimensions_stay_unknown_and_total_uses_measured_weight_only():
    clips = [
        clip(0, ["角色奔跑", "跳跃", "旋转"], tags=("跑酷",)),
        clip(1, ["角色奔跑"], seconds=0.75, uncertainty="画面遮挡"),
        clip(2, ["角色奔跑"]),
    ]
    scores = score_materials(brief(), clips)
    first, second = scores[("run", "e0")], scores[("run", "e1")]
    for name in ("visualQuality", "emotionalIntensity", "narrativeValue", "briefMatch"):
        assert first["parts"][name] is None
    assert first["coverage"] == 0.4  # clarity .15 + novelty .10 + platform .10 + technical .05
    assert first["total"] == 1.0
    # Shared description halves novelty; 0.75 s halves platform fit; uncertainty halves quality.
    assert second["parts"]["novelty"] == 0.5
    assert second["parts"]["platformFit"] == 0.5
    assert second["parts"]["technicalQuality"] == 0.5
    assert second["total"] < first["total"]


def test_brief_match_counts_mandatory_topics():
    clips = [clip(0, ["新英雄登场"]), clip(1, ["新英雄登场", "限时活动"])]
    scores = score_materials(brief(("新英雄", "限时活动")), clips)
    assert scores[("run", "e0")]["parts"]["briefMatch"] == 0.5
    assert scores[("run", "e1")]["parts"]["briefMatch"] == 1.0
    assert scores[("run", "e0")]["coverage"] == 0.65


def test_plan_carries_scores_legend_and_advisories():
    clips = tuple(clip(i, [f"片段{i}"], seconds=2) for i in range(3))
    report = plan_creation(brief(("片段1",), duration=12), clips, 30)
    assert report["scoring"]["weights"]["briefMatch"] == 0.25
    assert "未知" in report["scoring"]["basis"]["visualQuality"]
    for plan in report["plans"]:
        assert all("score" in segment for segment in plan["segments"])
        notes = " ".join(plan["advisories"])
        assert "素材偏少" in notes and "时长不足" in notes and "主题“片段1”只有1个片段" in notes
        assert "单一来源" in notes


@pytest.mark.parametrize("sources", [1, 2])
def test_single_source_advisory_only_when_true(sources):
    clips = [clip(i, [f"片段{i}"], source=asset("ab"[i % sources])) for i in range(4)]
    notes = advisories(brief(duration=6), clips, [], 30)
    assert any("单一来源" in note for note in notes) == (sources == 1)


def test_sampling_prefers_better_scored_clip_near_each_slot():
    facts = [[f"片段{i}"] for i in range(30)]
    facts[6] = ["角色跳跃", "空中旋转", "落地特效"]
    clips = tuple(clip(i, fact) for i, fact in enumerate(facts))
    guide = CreativeBrief("游戏", "guide", ("bilibili",), 6, "目标", "新玩家", "简洁", (), ())
    steps = plan_creation(guide, clips, 30)["plans"][0]["segments"]
    # Slots fall at 0, 10, 19, 29; the detailed clip 6 is within reach of slot 10.
    assert [s["eventId"] for s in steps] == ["e0", "e6", "e19", "e29"]


def test_guide_ends_stay_at_recording_ends_even_with_better_neighbours():
    facts = [[f"片段{i}"] for i in range(30)]
    facts[1] = facts[28] = ["角色跳跃", "空中旋转", "落地特效"]
    facts[28] = ["角色冲刺", "空中翻滚", "落地特效"]
    clips = tuple(clip(i, fact) for i, fact in enumerate(facts))
    guide = CreativeBrief("游戏", "guide", ("bilibili",), 6, "目标", "新玩家", "简洁", (), ())
    steps = plan_creation(guide, clips, 30)["plans"][0]["segments"]
    assert steps[0]["eventId"] == "e0" and steps[-1]["eventId"] == "e29"
