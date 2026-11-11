"""P019 one-sentence brief: only stated fields are filled; the sentence is kept as the objective."""

import pytest

from gamingcreator.application.brief_sentence import parse_brief_sentence


def fields(text):
    return parse_brief_sentence(text)["fields"]


def test_full_sentence():
    result = fields(
        "给新玩家做一个《漫画群星：大集结》1分钟的玩法展示，发B站，要有3V3和大乱斗，不要加载画面"
    )
    assert result == {
        "objective": "给新玩家做一个《漫画群星：大集结》1分钟的玩法展示，发B站，要有3V3和大乱斗，不要加载画面",
        "game": "漫画群星：大集结",
        "targetDuration": 60,
        "contentType": "feature_showcase",
        "platform": "bilibili",
        "mandatoryTopics": ["3V3", "大乱斗"],
        "exclude": ["加载画面"],
        "audience": "新玩家",
    }


@pytest.mark.parametrize(
    "text,seconds",
    [
        ("做个30秒的高光", 30),
        ("一分半的攻略", 90),
        ("半分钟抖音视频", 30),
        ("2分30秒解说", 150),
        ("十五分钟实况精剪", 900),
        ("90s 集锦", 90),
    ],
)
def test_durations(text, seconds):
    assert fields(text)["targetDuration"] == seconds


@pytest.mark.parametrize(
    "text,kind,platform",
    [
        ("Boss 通关攻略，发抖音", "guide", "douyin"),
        ("精彩集锦给小红书", "highlight", "xiaohongshu"),
        ("参加快手活动投稿", "campaign", "kuaishou"),
        ("新版本买量广告", "ad", None),
    ],
)
def test_type_and_platform(text, kind, platform):
    result = fields(text)
    assert result["contentType"] == kind
    assert result.get("platform") == platform


def test_unstated_fields_are_not_invented():
    result = fields("随便剪一下")
    assert result == {"objective": "随便剪一下"}
    assert parse_brief_sentence("随便剪一下")["recognized"] == []


@pytest.mark.parametrize("bad", ["", "   ", None, "x" * 501, 3])
def test_refusals(bad):
    with pytest.raises(ValueError):
        parse_brief_sentence(bad)


def test_retest_sentence_from_2026_11_11():
    """The user's J1 sentence: topics across commas, type not taken from a topic, game by name."""
    text = "给新玩家做个漫画群星：大集结的3V3和1V1的玩法展示。发布到B站，要有可玩角色介绍，技能解说、玩法思路、游戏特色。"
    result = parse_brief_sentence(text, ["漫画群星：大集结", "代号：Atom"])["fields"]
    assert result["game"] == "漫画群星：大集结"
    assert result["contentType"] == "feature_showcase"
    assert result["platform"] == "bilibili"
    assert result["mandatoryTopics"] == ["可玩角色介绍", "技能解说", "玩法思路", "游戏特色"]


def test_topic_list_stops_at_another_instruction():
    result = fields("要有Boss战，发B站，30秒高光")
    assert result["mandatoryTopics"] == ["Boss战"] and result["platform"] == "bilibili"
