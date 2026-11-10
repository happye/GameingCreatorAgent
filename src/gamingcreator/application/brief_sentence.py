"""One-sentence brief → structured brief fields, by local rules (P019; no model, no network).

Only what the sentence states is returned; everything else stays as the user set it. The
whole sentence becomes the objective so nothing the user wrote is lost.
"""

from __future__ import annotations

import re
from fractions import Fraction

MAX_CHARS = 500
TYPES = (
    ("guide", ("攻略", "教程", "通关", "教学", "怎么打")),
    ("highlight", ("高光", "集锦", "精彩", "名场面")),
    ("commentary", ("解说",)),
    ("live_cut", ("实况", "精剪", "直播切片")),
    ("campaign", ("活动", "投稿", "征稿", "参赛")),
    ("ad", ("广告", "买量", "推广", "宣传片")),
    ("feature_showcase", ("玩法", "展示", "介绍", "安利", "试玩")),
)
PLATFORMS = (
    ("bilibili", ("b站", "哔哩", "bilibili")),
    ("douyin", ("抖音", "douyin")),
    ("kuaishou", ("快手", "kuaishou")),
    ("xiaohongshu", ("小红书", "红书")),
)
DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
AUDIENCES = (
    "新玩家",
    "老玩家",
    "新手",
    "萌新",
    "小白",
    "硬核玩家",
    "休闲玩家",
    "粉丝",
    "路人",
    "玩家",
)


def _number(token: str) -> Fraction | None:
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return Fraction(token)
    if token == "半":
        return Fraction(1, 2)
    if not re.fullmatch(r"[零一二两三四五六七八九十百]+", token):
        return None
    total, current = 0, 0
    for char in token:
        if char == "百":
            total, current = total + (current or 1) * 100, 0
        elif char == "十":
            total, current = total + (current or 1) * 10, 0
        else:
            current = DIGITS[char]
    return Fraction(total + current)


def _duration(text: str) -> int | None:
    minutes = re.search(
        r"(\d+(?:\.\d+)?|[零一二两三四五六七八九十百]+|半)\s*(?:分钟|分|min)(半)?", text
    )
    seconds = re.search(r"(\d+(?:\.\d+)?|[零一二两三四五六七八九十百]+)\s*(?:秒|s\b)", text)
    total = Fraction(0)
    if minutes and (value := _number(minutes.group(1))) is not None:
        total += value * 60 + (30 if minutes.group(2) else 0)
    if seconds and (value := _number(seconds.group(1))) is not None:
        total += value
    seconds_total = int(total)
    return seconds_total if 1 <= seconds_total <= 86400 else None


def _items(match: re.Match[str] | None) -> list[str]:
    if match is None:
        return []
    parts = re.split(r"[、和与及跟/]|以及", match.group(1))
    return [p.strip(" 的") for p in parts if p.strip(" 的")][:10]


def parse_brief_sentence(text: object) -> dict[str, object]:
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
        raise ValueError("请输入1–500字的一句话需求。")
    sentence = re.sub(r"\s+", " ", text.strip())
    lower = sentence.casefold()
    fields: dict[str, object] = {"objective": sentence}
    notes: list[str] = []
    game = re.search(r"《([^》]{1,100})》", sentence)
    if game:
        fields["game"] = game.group(1).strip()
        notes.append(f"游戏：{fields['game']}")
    if (seconds := _duration(sentence)) is not None:
        fields["targetDuration"] = seconds
        notes.append(f"时长：{seconds} 秒")
    for value, words in TYPES:
        if any(word in lower for word in words):
            fields["contentType"] = value
            notes.append(f"类型：{words[0]}")
            break
    for name, aliases in PLATFORMS:
        if any(alias in lower for alias in aliases):
            fields["platform"] = name
            notes.append(f"平台：{aliases[0]}")
            break
    topics = _items(
        re.search(
            r"(?:要有|包含|突出|重点(?:讲|放)?|带上|必须有|一定要有)([^，,。；;！!？?]+)", sentence
        )
    )
    if topics:
        fields["mandatoryTopics"] = topics
        notes.append(f"必须主题：{'、'.join(topics)}")
    exclude = _items(re.search(r"(?:不要|别放|排除|去掉)([^，,。；;！!？?]+)", sentence))
    if exclude:
        fields["exclude"] = exclude
        notes.append(f"排除：{'、'.join(exclude)}")
    audience = re.search(r"(?:给|面向|适合)(" + "|".join(AUDIENCES) + ")", sentence)
    if audience:
        fields["audience"] = audience.group(1)
        notes.append(f"观众：{fields['audience']}")
    return {
        "schemaVersion": "brief-sentence-v1",
        "parser": "rule-v1",
        "fields": fields,
        "recognized": notes,
    }
