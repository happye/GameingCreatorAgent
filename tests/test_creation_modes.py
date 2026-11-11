"""Content-mode templates: recommended first, honest roles, render-valid frame layout."""

from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

from gamingcreator.application.creative_planner import CreationClip, plan_creation
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.narration_script import build_narration_script
from gamingcreator.application.rendering import validate_render_plan
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.time import SourceRange

ASSET = MediaAsset(
    "media",
    Path("source.mp4"),
    "a" * 64,
    (MediaStream(0, "video", Fraction(1, 1), 0, 120),),
    Fraction(0),
    120_000_000,
    "probe",
)


def brief(kind, duration=12, topics=()):
    return CreativeBrief(
        "代号Atom", kind, ("bilibili",), duration, "目标", "新玩家", "简洁", topics, ()
    )


def material(facts):
    return tuple(
        CreationClip(
            ASSET,
            SemanticEvent(
                f"e{i}",
                "media",
                "run",
                SourceRange(i * 4_000_000, (i + 1) * 4_000_000, 120_000_000),
                tuple(fact),
                (),
                (f"evidence{i}",),
                "visual",
                None,
            ),
        )
        for i, fact in enumerate(facts)
    )


def plan(report, identity):
    return next(p for p in report["plans"] if p["id"] == identity)


def test_showcase_hook_first_with_more_time_and_generic_plans_kept():
    facts = [
        ["角色奔跑"],
        ["角色跳跃", "空中旋转", "落地特效"],
        ["开门"],
        ["拾取道具"],
        ["结算画面"],
    ]
    report = plan_creation(brief("feature_showcase"), material(facts), 30)
    assert [p["id"] for p in report["plans"]] == [
        "showcase",
        "chronological",
        "hook-first",
        "reverse",
    ]
    showcase = report["plans"][0]
    assert showcase["mode"] == "feature_showcase" and showcase["modeLabel"] == "玩法展示"
    segments = showcase["segments"]
    assert [s["eventId"] for s in segments] == ["e1", "e0", "e2", "e3", "e4"]
    assert [s["role"] for s in segments] == ["开场高光", "玩法展示", "玩法展示", "玩法展示", "收尾"]
    assert segments[0]["outputFrames"] > segments[1]["outputFrames"]
    assert sum(s["outputFrames"] for s in segments) <= 12 * 30
    # Generic plans keep their previous even layout and carry no roles.
    chronological = plan(report, "chronological")["segments"]
    assert all("role" not in s for s in chronological)
    assert [s["outputFrames"] for s in chronological] == [72] * 5


def test_guide_steps_sample_the_whole_recording_with_contiguous_numbers():
    report = plan_creation(
        brief("guide", duration=6), material([[f"步骤{i}"] for i in range(20)]), 30
    )
    steps = report["plans"][0]
    assert steps["id"] == "guide-steps" and steps["modeLabel"] == "攻略"
    segments = steps["segments"]
    assert [s["role"] for s in segments] == ["第1步", "第2步", "第3步", "第4步"]
    assert [s["eventId"] for s in segments] == ["e0", "e6", "e13", "e19"]
    assert all(s["outputFrames"] >= 45 for s in segments)


def test_campaign_topics_follow_opening_and_missing_topic_is_advised():
    facts = [["角色奔跑"], ["新英雄登场", "技能展示"], ["限时活动入口"], ["结算"]]
    report = plan_creation(brief("campaign", topics=("限时活动",)), material(facts), 30)
    campaign = report["plans"][0]
    assert campaign["id"] == "campaign-topics" and campaign["ready"]
    assert [(s["eventId"], s["role"]) for s in campaign["segments"]] == [
        ("e1", "开场"),
        ("e2", "活动主题：限时活动"),
        ("e0", "活动亮点"),
        ("e3", "收尾"),
    ]
    missing = plan_creation(brief("campaign", topics=("周年庆",)), material(facts), 30)
    # Since 2026-11-11 a topic not seen in the facts only advises; it never greys the plan out.
    assert missing["plans"][0]["ready"]
    assert any("周年庆" in note for note in missing["plans"][0]["advisories"])


def test_mode_plan_is_a_valid_render_decision():
    report = plan_creation(brief("guide"), material([[f"步骤{i}"] for i in range(5)]), 30)
    report["brief"] = {"targetDuration": 12}
    edl = select_edit_decision(report, "guide-steps")
    timeline = SimpleNamespace(
        run=SimpleNamespace(run_id="run", asset=ASSET),
        events=tuple(clip.event for clip in material([[f"步骤{i}"] for i in range(5)])),
    )
    render = validate_render_plan(edl, report, (timeline,))
    assert render.frames == sum(s["outputFrames"] for s in edl["segments"])


def test_script_wording_follows_mode_roles():
    report = plan_creation(
        brief("guide", duration=30), material([[f"打开第{i}扇门"] for i in range(3)]), 30
    )
    rows = [{**s, "clipId": s["eventId"]} for s in report["plans"][0]["segments"]]
    script = build_narration_script(brief("guide", duration=30), rows, 900, 30)
    assert "第1步，打开第0扇门" in script["text"] and "第3步，打开第2扇门" in script["text"]
    campaign = build_narration_script(brief("campaign", duration=30), rows, 900, 30)
    assert campaign["text"].endswith("快来一起参与活动。")


def test_showcase_and_campaign_cap_clip_count_for_watchable_shots():
    facts = [[f"片段{i}"] for i in range(30)]
    facts[10] = ["角色跳跃", "空中旋转"]
    report = plan_creation(brief("feature_showcase", duration=15), material(facts), 30)
    showcase = report["plans"][0]["segments"]
    # 15 seconds at about 1.5 seconds per shot -> 10 shots, opening first, evenly sampled rest.
    assert len(showcase) == 10 and showcase[0]["eventId"] == "e10"
    assert showcase[1]["eventId"] == "e0" and showcase[-1]["eventId"] == "e29"
    assert all(s["outputFrames"] >= 30 for s in showcase)
    facts[20] = ["限时活动入口"]
    campaign = plan_creation(
        brief("campaign", duration=15, topics=("限时活动",)), material(facts), 30
    )["plans"][0]["segments"]
    assert len(campaign) == 10 and campaign[1]["role"] == "活动主题：限时活动"


def test_topic_label_is_not_overwritten_by_closing():
    facts = [["开场奔跑", "特效"], ["事件甲"], ["事件乙"]]
    report = plan_creation(brief("campaign", topics=("事件甲", "事件乙")), material(facts), 30)
    assert [s["role"] for s in report["plans"][0]["segments"]] == [
        "开场",
        "活动主题：事件甲",
        "活动主题：事件乙",
    ]


def test_spoken_steps_stay_contiguous_after_edits():
    report = plan_creation(
        brief("guide", duration=30), material([[f"打开第{i}扇门"] for i in range(4)]), 30
    )
    rows = [{**s, "clipId": s["eventId"]} for s in report["plans"][0]["segments"]]
    edited = [rows[3], rows[0], rows[2]]  # second step deleted, last moved first
    text = build_narration_script(brief("guide", duration=30), edited, 900, 30)["text"]
    assert "第1步，打开第3扇门" in text and "第2步，打开第0扇门" in text
    assert "第3步，打开第2扇门" in text and "第4步" not in text


def test_remaining_modes_are_recommended_with_their_own_structures():
    facts = [[f"片段{i}"] for i in range(20)]
    facts[3] = ["角色跳跃", "空中旋转", "落地特效"]
    facts[12] = ["新英雄登场", "技能展示"]
    clips = material(facts)
    commentary = plan_creation(brief("commentary", duration=15), clips, 30)["plans"][0]
    assert commentary["id"] == "commentary-segments" and commentary["modeLabel"] == "游戏解说"
    roles = [s["role"] for s in commentary["segments"]]
    assert roles[0] == "开场" and roles[-1] == "结尾" and len(roles) == 5
    live = plan_creation(brief("live_cut", duration=15), clips, 30)["plans"][0]
    assert live["id"] == "live-cut" and len(live["segments"]) == 10
    events = [s["eventId"] for s in live["segments"]]
    assert events == sorted(events, key=lambda e: int(e[1:]))
    highlight = plan_creation(brief("highlight", duration=6), clips, 30)["plans"][0]
    assert highlight["id"] == "highlight-climax"
    assert (
        highlight["segments"][-1]["eventId"] == "e3" and highlight["segments"][-1]["role"] == "高潮"
    )
    ad = plan_creation(brief("ad", duration=15, topics=("新英雄",)), clips, 30)["plans"][0]
    assert ad["id"] == "ad-hook" and ad["modeLabel"] == "广告/买量"
    assert [s["role"] for s in ad["segments"]][:2] == ["开场钩子", "卖点"]
    # The topic clip scores highest (brief match), so it becomes the hook.
    assert ad["segments"][0]["eventId"] == "e12" and ad["segments"][1]["eventId"] == "e3"
    assert ad["segments"][-1]["role"] == "行动号召"
    assert ad["segments"][0]["outputFrames"] > ad["segments"][1]["outputFrames"]


def test_new_mode_scripts_open_and_close_in_their_own_words():
    rows = [{"clipId": "a", "scriptDraft": "角色奔跑", "outputStartFrame": 0}]
    ad = build_narration_script(brief("ad", duration=30), rows, 900, 30)["text"]
    assert ad.startswith("一起来玩代号Atom。") and ad.endswith("现在就来体验。")
    commentary = build_narration_script(brief("commentary", duration=30), rows, 900, 30)["text"]
    assert commentary.endswith("感谢收看。")


def test_local_render_history_reorders_generic_structures_only():
    from gamingcreator.application.creation_feedback import plan_preferences

    facts = [f"画面{i}出现敌人" for i in range(6)]
    template = plan_creation(brief("feature_showcase"), material(facts), 30)
    assert template["ordering"] == {"basis": "template", "renderedByPlan": {}}
    summary = {
        "rows": [
            {"planId": "reverse", "render": True},
            {"planId": "reverse", "render": True},
            {"planId": "chronological", "render": False},
            {"planId": "hook-first", "render": True},
        ]
    }
    habits = plan_preferences(summary)
    assert habits == {"hook-first": 1, "reverse": 2}
    report = plan_creation(brief("feature_showcase"), material(facts), 30, habits)
    ids = [p["id"] for p in report["plans"]]
    # The content-mode template stays first (recommended); habits move the generic orders.
    assert ids[0] == template["plans"][0]["id"] and report["plans"][0]["mode"]
    assert ids[1:] == ["reverse", "hook-first", "chronological"]
    assert report["plans"][1]["localRenders"] == 2 and report["plans"][1]["rankedByHistory"]
    assert "localRenders" not in report["plans"][3]
    assert report["ordering"]["basis"] == "local-render-history"
    # History never decorates the mode template, and an unmoved structure is not "ranked".
    mode_id = template["plans"][0]["id"]
    same = plan_creation(
        brief("feature_showcase"), material(facts), 30, {mode_id: 5, "chronological": 1}
    )
    assert "localRenders" not in same["plans"][0]
    assert same["plans"][1]["id"] == "chronological" and not same["plans"][1]["rankedByHistory"]
    assert same["ordering"]["basis"] == "template"
    assert plan_creation(brief("feature_showcase"), material(facts), 30, {"x": 0, "y": True})[
        "ordering"
    ] == {"basis": "template", "renderedByPlan": {}}


def test_edit_habit_trim_suggestion_shortens_records_and_skips_when_rare():
    from gamingcreator.application.creation_feedback import TRIM_TIP, trim_suggestion

    facts = [f"画面{i}出现敌人" for i in range(6)]
    clips = material(facts)
    baseline = plan_creation(brief("feature_showcase"), clips, 30)
    # High trim share (>=3 and >=50%) applies 1s cap and records the rule.
    heavy = {"裁剪": 5, "删镜头": 1, "变速": 1}
    assert trim_suggestion(heavy)["applied"] is True
    shortened = plan_creation(brief("feature_showcase"), clips, 30, edit_kinds=heavy)
    tip = shortened["ordering"]["editHabits"]["trimSuggestion"]
    assert tip["applied"] is True and tip["rule"] == "max-output-seconds-per-segment=1"
    assert tip["trimEdits"] == 5 and tip["totalEditEvents"] == 7
    assert shortened["ordering"]["editHabits"]["editKinds"] == heavy
    for plan in shortened["plans"]:
        assert plan["advisories"][0] == TRIM_TIP
        assert all(segment["outputFrames"] <= 30 for segment in plan["segments"])
    # At least one plan had a longer baseline segment that the cap actually cuts.
    assert any(
        before["outputFrames"] > after["outputFrames"]
        for before, after in zip(
            baseline["plans"][0]["segments"], shortened["plans"][0]["segments"], strict=False
        )
    )
    # Rare trims: record observations, do not change durations or tip.
    light = {"裁剪": 1, "删镜头": 4}
    assert trim_suggestion(light)["applied"] is False
    rare = plan_creation(brief("feature_showcase"), clips, 30, edit_kinds=light)
    assert rare["ordering"]["editHabits"]["trimSuggestion"]["applied"] is False
    assert TRIM_TIP not in rare["plans"][0]["advisories"]
    assert [s["outputFrames"] for s in rare["plans"][0]["segments"]] == [
        s["outputFrames"] for s in baseline["plans"][0]["segments"]
    ]
    # edit_kinds=None keeps the pre-T9 ordering shape (no editHabits key).
    assert "editHabits" not in baseline["ordering"]
