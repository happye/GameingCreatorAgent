"""Offline extraction of verifiable fields from activity rule text (no model).

Every extracted value carries the exact source line it came from, so a person can check it.
Anything ambiguous (negated, excluded, conflicting, several candidates, out of range, wrong
unit or subject) stays None: a cited wrong value is worse than an empty field.
"""

import re
from datetime import date
from typing import Any

PLATFORMS = {
    "bilibili": ("b站", "bilibili", "哔哩哔哩"),
    "douyin": ("抖音", "douyin"),
    "kuaishou": ("快手", "kuaishou"),
    "xiaohongshu": ("小红书", "xiaohongshu"),
}
MAX_TEXT = 200_000
_NUM = r"(\d+(?:\.\d+)?)"
_UNIT = r"(秒钟?|s|分钟|min)"
_NEGATION = r"禁止|不得|不允许|严禁|不可|请勿|勿|不要|不能|不接受|不支持|非|拒绝|不予|不含|除外|不包括|排除|以外"
_FULL = r"(\d{4})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?(?:\s*(\d{1,2})[:：](\d{2}))?"
_SHORT = (
    r"(?:(\d{4})\s*[年./-]\s*)?(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?(?:\s*(\d{1,2})[:：](\d{2}))?"
)
_RANGE = r"\s*(?:至|到|-|~|～|—|–)\s*"
_LABEL = (
    r"(?:活动名称|活动主题|赛事名称|活动时间|投稿时间|征集时间|参与平台|发布平台|投稿平台)\s*[:：]"
)
_MIN_VERBS = r"不少于|不低于|不得少于|不能少于|至少|最短|≥|≧|>=|大于等于"
_MAX_VERBS = r"不超过|不得超过|不能超过|不多于|最长|≤|≦|<=|小于等于"
# Only the submitted video itself: 直播/观看/游戏时长 and 示例/素材/原视频 are other things.
_DURATION_TOPIC = r"(?<!示例)(?<!素材)(?<!参考)(?<!原)(?:视频|作品|成片|投稿)的?(?:时长|长度)"
_GAP = r"[^。；;\n（(]"
_CLAUSE_MARKS = "，,。；;、（(）)"
_SENTENCE_MARKS = "，,。；;（(）)"
# 1分钟30秒 style compound values are refused rather than half-read.
_COMPOUND = r"\d+(?:\.\d+)?\s*(?:分钟|分|min)\s*\d+(?:\.\d+)?\s*(?:秒|s)"


def _evidence(lines: list[str], index: int) -> dict[str, Any]:
    return {"line": index + 1, "text": lines[index].strip()[:300]}


def _seconds(value: str, unit: str) -> float:
    return float(value) * (60 if unit in ("分钟", "min") else 1)


def _stamp(year: int, month: int, day: int, hour: str | None, minute: str | None) -> str | None:
    try:
        date(year, month, day)
    except ValueError:
        return None
    if hour is not None and (int(hour) > 23 or minute is None or int(minute) > 59):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}" + (f" {int(hour):02d}:{minute}" if hour else "")


def _normalize_ocr(line: str) -> str:
    """Fix common OCR confusions before matching; never invent missing facts."""
    # 杪 (tip of a branch) is a frequent misread of 秒 in screenshots/PDFs.
    return line.replace("杪", "秒").replace("≧", "≥").replace("≦", "≤")


def _period_bounds(
    y1: str,
    m1: str,
    d1: str,
    h1: str | None,
    n1: str | None,
    y2: str | None,
    m2: str,
    d2: str,
    h2: str | None,
    n2: str | None,
) -> dict[str, str] | None:
    # A missing end year continues the start year; a wrapped month would be a guess.
    if not y2 and int(m2) < int(m1):
        return None
    start = _stamp(int(y1), int(m1), int(d1), h1, n1)
    end = _stamp(int(y2) if y2 else int(y1), int(m2), int(d2), h2, n2)
    if start is None or end is None or end < start:
        return None
    return {"start": start, "end": end}


def _period(line: str) -> dict[str, str] | None:
    # Several ranges (phases) or a pending change are not one stated activity period.
    if re.search(r"延期|顺延|另行通知|待定|调整为|第一阶段|第二阶段|第三阶段", line):
        return None
    match = re.search(_FULL + _RANGE + _SHORT, line)
    if match and len(re.findall(_SHORT + _RANGE + _SHORT, line)) == 1:
        return _period_bounds(*match.groups())
    # 自 START 起 … 至/到 END（止/结束/截止）— both ends stated, no invented start.
    since = re.search(
        r"自\s*"
        + _FULL
        + r"\s*起\s*(?:，|,)?\s*(?:至|到|截止到)\s*"
        + _SHORT
        + r"\s*(?:止|结束|截止|前)?",
        line,
    )
    if since:
        return _period_bounds(*since.groups())
    # START 起至/到 END without a leading 自, still both ends explicit.
    rising = re.search(
        _FULL + r"\s*起\s*(?:至|到|截止到)\s*" + _SHORT + r"\s*(?:止|结束|截止|前)?",
        line,
    )
    if rising and len(re.findall(_SHORT + r"\s*起", line)) == 1:
        return _period_bounds(*rising.groups())
    return None


def _clause(line: str, position: int, marks: str = _CLAUSE_MARKS) -> str:
    """The fragment around position, so a negation in another clause is ignored."""
    starts = [line.rfind(mark, 0, position) for mark in marks]
    ends = [i for i in (line.find(mark, position) for mark in marks) if i >= 0]
    return line[max(starts) + 1 : min(ends) if ends else len(line)]


def _negated(line: str, position: int, marks: str = _CLAUSE_MARKS) -> bool:
    return bool(re.search(_NEGATION, _clause(line, position, marks)))


def _merge_compound(match: re.Match[str]) -> str:
    minutes, seconds = re.findall(r"\d+(?:\.\d+)?", match.group(0))
    return f"{float(minutes) * 60 + float(seconds):g}秒"


def _durations(line: str) -> tuple[float | None, float | None]:
    # "1分钟30秒" is unambiguous minutes+seconds: read it as 90秒 (a bare "4分" stays ignored).
    line = re.sub(_COMPOUND, _merge_compound, line)
    span = re.search(
        rf"{_DURATION_TOPIC}{_GAP}{{0,8}}?{_NUM}\s*{_UNIT}?{_RANGE}{_NUM}\s*{_UNIT}", line
    )
    if span:
        shortest = _seconds(span.group(1), span.group(2) or span.group(4))
        longest = _seconds(span.group(3), span.group(4))
        return (shortest, longest) if shortest < longest else (None, None)
    low = re.search(rf"{_DURATION_TOPIC}{_GAP}{{0,8}}?(?:{_MIN_VERBS})\s*{_NUM}\s*{_UNIT}", line)
    high = re.search(
        rf"{_DURATION_TOPIC}{_GAP}{{0,12}}?(?:{_MAX_VERBS})\s*{_NUM}\s*{_UNIT}", line
    ) or re.search(rf"{_DURATION_TOPIC}{_GAP}{{0,8}}?{_NUM}\s*{_UNIT}以内", line)
    return (
        _seconds(low.group(1), low.group(2)) if low else None,
        _seconds(high.group(1), high.group(2)) if high else None,
    )


def _orientation(line: str) -> str | None:
    # A bare 9:16 only counts next to an aspect word, so clock times never match.
    ratio = bool(re.search(r"比例|画幅|尺寸|画面|分辨率", line))
    vertical = re.search(r"竖屏|竖版", line) or (
        re.search(r"(?<![\d:：.\s])9\s*[:：]\s*16(?!\d)", line) if ratio else None
    )
    horizontal = re.search(r"横屏|横版", line) or (
        re.search(r"(?<![\d:：.\s])16\s*[:：]\s*9(?!\d)", line) if ratio else None
    )
    if bool(vertical) == bool(horizontal):
        return None  # Neither, or both offered: not a requirement.
    match = vertical or horizontal
    assert match is not None
    clause = _clause(line, match.start())
    # "本游戏为竖屏手游" describes the game, not the submission.
    if _negated(line, match.start()) or re.search(r"游戏为|手游|游戏是", clause):
        return None
    return "vertical" if vertical else "horizontal"


def _platforms(line: str) -> list[str]:
    if not re.search(r"参与平台|发布平台|投稿平台|投稿至|投稿到|发布到|发布于", line):
        return []
    lowered = line.casefold()
    hits = []
    for key, names in PLATFORMS.items():
        for name in names:
            position = lowered.find(name)
            # Whole sentence, not 、-separated items: "除抖音、快手以外" excludes both.
            if position >= 0 and not _negated(lowered, position, _SENTENCE_MARKS):
                hits.append((position, key))
    return [key for _, key in sorted(hits)]


def _topics(line: str) -> list[str]:
    found = []
    # A closed #话题# always counts; an open #话题 only on a line about topics/tags.
    open_allowed = bool(re.search(r"话题|标签|tag", line, re.IGNORECASE))
    for match in re.finditer(r"(?<![\w/#])#([^#\s，,。；;、！!？?（）()【】\[\]]{1,30})(#?)", line):
        topic, closed = match.group(1), bool(match.group(2))
        clause = _clause(line, match.start(), _SENTENCE_MARKS)
        if (
            (closed or open_allowed)
            and re.search(r"\D", topic)
            and not _negated(line, match.start())
            # Optional or recommended topics are not requirements.
            and not re.search(r"可选|推荐|建议|可以|可带|自愿", clause)
        ):
            found.append(topic)
    quoted = re.search(
        r"(?:带上|添加|带|加上|使用)(?:话题|标签|tag)\s*[:：]?\s*[「“\"](.{1,30}?)[」”\"]", line
    )
    if (
        quoted
        and not _negated(line, quoted.start())
        and not re.search(r"可选|推荐|建议|可以|可带|自愿", _clause(line, quoted.start()))
    ):
        found.append(quoted.group(1))
    return found


def _single(candidates: list[tuple[Any, dict[str, Any]]]) -> dict[str, Any] | None:
    """One value when every mention agrees; differing values are a conflict, not a choice."""
    if not candidates or len({repr(value) for value, _ in candidates}) != 1:
        return None
    value, evidence = candidates[0]
    return {"value": value, **evidence}


def extract_activity_rules(text: object) -> dict[str, object]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("活动规则内容为空。")
    if len(text) > MAX_TEXT:
        raise ValueError("活动规则过长（超过20万字）。")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    names, activity, submission, minimums, maximums, orientations = [], [], [], [], [], []
    platforms: list[dict[str, Any]] = []
    topics: list[dict[str, Any]] = []
    forbidden: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        stripped = _normalize_ocr(line.strip())
        evidence = _evidence(lines, index)
        # Ends at a full-width space, sentence mark, a known label, or any space-led "XX：".
        name = re.search(
            rf"(?:活动名称|活动主题|赛事名称)\s*[:：]\s*(.+?)\s*"
            rf"(?=　|[，,；;。]|{_LABEL}|\s+[^\s:：]{{1,8}}[:：]|$)",
            stripped,
        )
        if name and name.group(1).strip():
            names.append((name.group(1).strip(), evidence))
        period = _period(stripped)
        first_date = re.search(_FULL, stripped)
        if period and first_date:
            # The label closest before the dates decides what kind of period it is.
            labels = re.findall(
                r"活动时间|活动周期|活动日期|投稿时间|征集时间|报名时间|截止时间|截止日期",
                stripped[: first_date.start()],
            )
            if labels and labels[-1] in ("活动时间", "活动周期", "活动日期"):
                activity.append((period, evidence))
            elif labels:
                submission.append((period, evidence))
            elif re.search(r"自.+起|(?:截止到|截止日期|截止时间)", stripped):
                # Explicit 自…起 or 截止 window with both ends already verified by _period.
                submission.append((period, evidence))
        low, high = _durations(stripped)
        if low is not None:
            minimums.append((low, evidence))
        if high is not None:
            maximums.append((high, evidence))
        orientation = _orientation(stripped)
        if orientation:
            orientations.append((orientation, evidence))
        # Platforms only from lines that say where to publish, never from prohibitions.
        for key in _platforms(stripped):
            if key not in {p["value"] for p in platforms}:
                platforms.append({"value": key, **evidence})
        for topic in _topics(line):
            if topic not in {t["value"] for t in topics}:
                topics.append({"value": topic, **evidence})
        heading = re.fullmatch(r"[【\[][^】\]]{0,10}[】\]][:：]?", stripped)
        # Duration limits phrased with 不得 are requirements, already captured above.
        if (
            re.search(r"禁止|不得|不允许|严禁|不可使用|请勿", line)
            and not heading
            # "禁止出现以下内容：" introduces the list items that follow.
            and not re.search(r"[:：]$", stripped)
            and not re.search(rf"{_DURATION_TOPIC}|{_NUM}\s*{_UNIT}", line)
        ):
            value = re.sub(r"^\s*[\d一二三四五六七八九十]+[.、)）]\s*", "", stripped)[:120]
            forbidden.append({"value": value, **evidence})
    fields: dict[str, Any] = {
        "name": _single(names[:1]),
        # The stated activity period wins over a separate submission window.
        "period": _single(activity) if activity else _single(submission),
        "platforms": platforms or None,
        "minDurationSeconds": _single(minimums),
        "maxDurationSeconds": _single(maximums),
        "orientation": _single(orientations),
        "requiredTopics": topics or None,
        "forbidden": forbidden or None,
    }
    low_field, high_field = fields["minDurationSeconds"], fields["maxDurationSeconds"]
    if low_field and high_field and low_field["value"] > high_field["value"]:
        # Contradictory limits are surfaced as unknown rather than silently clamped.
        fields["minDurationSeconds"] = fields["maxDurationSeconds"] = None
    known = sum(value is not None for value in fields.values())
    return {
        "schemaVersion": "activity-rules-v3",
        "extractor": "offline-pattern-v3",
        "fields": fields,
        "knownFields": known,
        "totalFields": len(fields),
        "status": "extracted-human-check-required",
    }
