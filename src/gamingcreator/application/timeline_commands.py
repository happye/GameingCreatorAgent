"""Deterministic Chinese timeline commands mapped onto editable clip rows (no model, no I/O).

Each clause must fully match one whitelisted sentence pattern. Extra words (除/外/取消/不要/
之后…) therefore make the clause unrecognized and the whole command is refused: a wrong edit
is worse than no edit.
"""

import re
from collections.abc import Callable
from copy import deepcopy
from fractions import Fraction
from typing import Any

from gamingcreator.application.rendering import output_start_frames

SPEEDS = {Fraction(1, 2): "0.5倍", Fraction(1): "原速", Fraction(2): "2倍"}
EXAMPLES = (
    "前5秒太慢、删掉第3个镜头、第三个镜头删掉、第2个和第3个镜头慢放、整体快放、整体快一点、"
    "把最后一个镜头移到最前、把第4个镜头放到第1个镜头后面、把第2个镜头挪到片尾、"
    "交换第1个和第2个、对调第一个和第五个、第4个镜头缩短到1.5秒、去掉开头半秒、"
    "删掉最后1秒、第1个镜头剪掉结尾半秒、去掉转场、加交叉淡化、改回原速"
)
_DIGITS = {
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
_NUM = r"(?:\d+(?:\.\d+)?|[零一二两三四五六七八九十]+|半)"
_UNIT = r"(?:个|段)?(?:镜头|片段)?"
_SEP = r"(?:、|和|与|及|跟)"
_REFLIST = rf"第{_NUM}{_UNIT}(?:{_SEP}第?{_NUM}{_UNIT})*"
_SPAN = rf"第{_NUM}{_UNIT}(?:到|至)第?{_NUM}{_UNIT}"
_LAST = r"最后一(?:个|段)(?:镜头|片段)?"
_ALL = r"(?:全部|所有|整体|全片|整个视频|每个镜头)(?:的?镜头)?"
_WINDOW = rf"(?:前|后|最后){_NUM}秒(?:内?的?镜头)?"
_TARGET = rf"(?:{_SPAN}|{_REFLIST}|{_LAST}|{_ALL}|{_WINDOW})"
_SINGLE = rf"(?:第{_NUM}{_UNIT}|{_LAST})"
_FAST = (
    r"快放|加速|加快|快一点|太慢了?|拖沓|太拖沓了?|改成?2倍速?|改为2倍速?|2倍速|两倍速|改成?两倍速?"
)
_SLOW = (
    r"慢放|放慢|减速|慢一点|太快了?|改成?0\.5倍速?|改为0\.5倍速?|0\.5倍速?|改成?半速|改为半速|半速"
)
_RESTORE = r"恢复原速|恢复正常速度|恢复正常|改回原速|改成?原速|改为原速|原速|1倍速|一倍速"
_TR = r"交叉淡化|淡入淡出|转场|淡化"


class CommandError(ValueError):
    pass


def _number(token: str) -> Fraction:
    try:
        if token == "半":
            return Fraction(1, 2)
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            return Fraction(token)
        if token.count("十") == 1 and len(token) <= 3:
            tens, _, ones = token.partition("十")
            return Fraction((_DIGITS[tens] if tens else 1) * 10 + (_DIGITS[ones] if ones else 0))
        if len(token) == 1:
            return Fraction(_DIGITS[token])
    except KeyError:
        pass
    raise CommandError(f"无法识别数字“{token}”。")


def _speed(row: dict[str, Any]) -> Fraction:
    value = row["speed"]
    return Fraction(value["numerator"], value["denominator"])


def _frames(row: dict[str, Any], fps: int) -> int:
    speed = _speed(row)
    source: int = row["endUs"] - row["startUs"]
    return source * fps * speed.denominator // (1_000_000 * speed.numerator)


def _check(clips: object, fps: object) -> list[dict[str, Any]]:
    if type(fps) is not int or not 1 <= fps <= 120:
        raise CommandError("无效帧率。")
    if not isinstance(clips, list) or not clips:
        raise CommandError("没有可修改的镜头。")
    rows: list[dict[str, Any]] = []
    for clip in clips:
        if not isinstance(clip, dict) or set(clip) != {
            "clipId",
            "startUs",
            "endUs",
            "speed",
            "transitionIn",
        }:
            raise CommandError("镜头字段不完整。")
        speed, transition = clip["speed"], clip["transitionIn"]
        if (
            not isinstance(clip["clipId"], str)
            or type(clip["startUs"]) is not int
            or type(clip["endUs"]) is not int
            or not 0 <= clip["startUs"] < clip["endUs"]
            or not isinstance(speed, dict)
            or set(speed) != {"numerator", "denominator"}
            or (speed.get("numerator"), speed.get("denominator")) not in ((1, 2), (1, 1), (2, 1))
            or not isinstance(transition, dict)
            or set(transition) != {"type", "frames"}
            or type(transition.get("frames")) is not int
            or transition.get("type") not in ("cut", "crossfade")
        ):
            raise CommandError("镜头字段无效。")
        rows.append(deepcopy(clip))
    if len({row["clipId"] for row in rows}) != len(rows):
        raise CommandError("镜头身份重复。")
    return rows


def _starts(rows: list[dict[str, Any]], fps: int) -> tuple[int, ...]:
    lengths = tuple(_frames(row, fps) for row in rows)
    transitions = tuple(row["transitionIn"]["frames"] for row in rows)
    try:
        return output_start_frames(lengths, transitions)
    except ValueError:
        return output_start_frames(lengths)


def _index(token: str, rows: list[dict[str, Any]]) -> int:
    value = _number(token)
    if value.denominator != 1 or not 1 <= value <= len(rows):
        raise CommandError(f"只有 {len(rows)} 个镜头，没有第{token}个。")
    return int(value) - 1


def _resolve(target: str, rows: list[dict[str, Any]], fps: int) -> tuple[list[int], str]:
    """Indices for a target phrase that already fully matched _TARGET."""
    if re.fullmatch(_LAST, target):
        return [len(rows) - 1], "最后一个镜头"
    if re.fullmatch(_ALL, target):
        return list(range(len(rows))), "全部镜头"
    window = re.fullmatch(rf"(前|后|最后)({_NUM})秒(?:内?的?镜头)?", target)
    if window:
        starts = _starts(rows, fps)
        ends = [s + _frames(r, fps) for s, r in zip(starts, rows, strict=True)]
        limit = _number(window.group(2)) * fps
        if window.group(1) == "前":
            picked = [i for i, s in enumerate(starts) if s < limit]
        else:
            picked = [i for i, e in enumerate(ends) if e > max(ends) - limit]
        return picked, f"{window.group(1)}{window.group(2)}秒内的镜头"
    if not re.search(r"个|段|镜头|片段", target):
        raise CommandError(f"“{target}”不是镜头编号，请说“第3个镜头”。")
    numbers = re.findall(_NUM, target.replace("镜头", "").replace("片段", ""))
    span = re.fullmatch(_SPAN, target)
    if span and re.search("到|至", target):
        first, last = sorted(_index(n, rows) for n in numbers)
        picked = list(range(first, last + 1))
    else:
        picked = [_index(n, rows) for n in numbers]
    if len(set(picked)) != len(picked):
        raise CommandError("同一个镜头被重复提到。")
    return picked, "、".join(f"第{i + 1}个" for i in picked) + "镜头"


def _single(target: str, rows: list[dict[str, Any]], fps: int) -> int:
    picked, _ = _resolve(target, rows, fps)
    if len(picked) != 1:
        raise CommandError("这一操作一次只能针对一个镜头。")
    return picked[0]


def _set_speed(
    rows: list[dict[str, Any]], picked: list[int], label: str, speed: Fraction, fps: int
) -> list[str]:
    if not picked:
        raise CommandError(f"{label}里没有镜头。")
    changed = [i for i in picked if _speed(rows[i]) != speed]
    if not changed:
        raise CommandError(f"{label}已经是{SPEEDS[speed]}，没有可改的。")
    changes = []
    for i in changed:
        before = _frames(rows[i], fps)
        rows[i]["speed"] = {"numerator": speed.numerator, "denominator": speed.denominator}
        if _frames(rows[i], fps) <= 0:
            raise CommandError(f"第{i + 1}个镜头太短，不能再加速。")
        changes.append(
            f"第{i + 1}个镜头改为{SPEEDS[speed]}"
            f"（{before / fps:.2f}→{_frames(rows[i], fps) / fps:.2f}秒）"
        )
    return changes


def _trim(
    rows: list[dict[str, Any]],
    i: int,
    fps: int,
    keep: Fraction | None,
    head: Fraction | None,
    tail: Fraction | None,
) -> str:
    row, speed = rows[i], _speed(rows[i])
    before = _frames(row, fps)
    if keep is not None:
        new_end = row["startUs"] + int(keep * speed * 1_000_000)
        if new_end >= row["endUs"]:
            raise CommandError(f"第{i + 1}个镜头只有{before / fps:.2f}秒，只能缩短。")
        row["endUs"] = new_end
    else:
        amount = head if head is not None else tail
        assert amount is not None
        shift = int(amount * speed * 1_000_000)
        if shift >= row["endUs"] - row["startUs"]:
            raise CommandError(f"第{i + 1}个镜头只有{before / fps:.2f}秒，不能减去这么多。")
        if head is not None:
            row["startUs"] += shift
        else:
            row["endUs"] -= shift
    if _frames(row, fps) <= 0:
        raise CommandError(f"第{i + 1}个镜头缩短后不足一帧。")
    return f"第{i + 1}个镜头{before / fps:.2f}→{_frames(row, fps) / fps:.2f}秒"


Handler = Callable[[re.Match[str], list[dict[str, Any]], int], list[str]]
_RULES: list[tuple[str, Handler]] = []


def rule(pattern: str) -> Callable[[Handler], Handler]:
    def register(handler: Handler) -> Handler:
        _RULES.append((pattern, handler))
        return handler

    return register


def _delete(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    target = m.group("t")
    if re.fullmatch(_ALL, target) or re.fullmatch(_WINDOW, target):
        raise CommandError("删除只按镜头编号，例如“删掉第3个镜头”；按秒去掉请说“删掉最后1秒”。")
    picked, label = _resolve(target, rows, fps)
    if len(picked) >= len(rows):
        raise CommandError("不能删掉全部镜头，至少保留一个。")
    for i in sorted(picked, reverse=True):
        rows.pop(i)
    return [f"删掉{label}（{len(picked)}个）"]


_DELETE = r"删掉|删除|去掉|剪掉|移除"


def _speed_rule(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    word = m.group("s")
    speed = (
        Fraction(1)
        if word == "恢复" or re.fullmatch(_RESTORE, word)
        else Fraction(1, 2)
        if re.fullmatch(_SLOW, word)
        else Fraction(2)
    )
    picked, label = _resolve(m.group("t"), rows, fps)
    if word in ("快一点", "慢一点"):
        # Relative: one step along 0.5x → 1x → 2x for each clip, never skipping a step.
        ladder = sorted(SPEEDS)
        step = 1 if word == "快一点" else -1
        changes: list[str] = []
        for i in picked:
            position = ladder.index(_speed(rows[i])) + step
            if not 0 <= position < len(ladder):
                raise CommandError(
                    f"第{i + 1}个镜头已经是{SPEEDS[_speed(rows[i])]}，不能再{word[0]}。"
                )
            changes += _set_speed(rows, [i], f"第{i + 1}个镜头", ladder[position], fps)
        return changes
    return _set_speed(rows, picked, label, speed, fps)


@rule(rf"(?P<t>{_SINGLE})(?:移到|放到|挪到|调到|移至|放在)(?P<p>.+)")
def _move(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    source = _single(m.group("t"), rows, fps)
    place = m.group("p")
    row = rows[source]
    if re.fullmatch(r"最前面?|开头|片头|第一位", place):
        rows.insert(0, rows.pop(source))
        where = "最前"
    elif re.fullmatch(r"最后面?|末尾|结尾|片尾|最后一位", place):
        rows.append(rows.pop(source))
        where = "最后"
    elif position := re.fullmatch(rf"第({_NUM})位", place):
        target = _index(position.group(1), rows)
        rows.insert(target, rows.pop(source))
        where = f"第{target + 1}位"
    elif anchor := re.fullmatch(
        rf"(?P<a>{_SINGLE})(?:的)?(?P<side>前面|之前|后面|之后)?(?:位置)?", place
    ):
        target = _single(anchor.group("a"), rows, fps)
        if target == source:
            raise CommandError("移动目标必须是另一个镜头。")
        side = anchor.group("side")
        if side is None:
            rows.insert(target, rows.pop(source))
            where = f"第{target + 1}位"
        else:
            other = rows[target]
            rows.pop(source)
            rows.insert(rows.index(other) + (1 if "后" in side else 0), row)
            where = f"原第{target + 1}个镜头{'后面' if '后' in side else '前面'}"
    else:
        raise CommandError(f"没听懂要移到哪里：“{place}”。")
    if rows.index(row) == source:
        raise CommandError(f"第{source + 1}个镜头已经在这个位置，顺序没有变化。")
    return [f"第{source + 1}个镜头移到{where}"]


def _swap(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    picked, _ = _resolve(m.group("t"), rows, fps)
    if len(picked) != 2 or re.search("到|至", m.group("t")):
        raise CommandError("交换需要恰好两个镜头，例如“交换第1个和第2个”。")
    a, b = picked
    rows[a], rows[b] = rows[b], rows[a]
    return [f"交换第{a + 1}个和第{b + 1}个镜头"]


rule(rf"(?:交换|对调|互换)(?P<t>{_REFLIST})")(_swap)
rule(rf"(?P<t>{_REFLIST})(?:交换|对调|互换)")(_swap)

_TRIM = r"缩短|裁短|剪短|截短"
_CUT = r"去掉|剪掉|裁掉|删掉|删除"


@rule(rf"(?P<t>{_SINGLE})的?(?:{_TRIM})到(?P<n>{_NUM})秒")
def _trim_to(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    return [_trim(rows, _single(m.group("t"), rows, fps), fps, _number(m.group("n")), None, None)]


@rule(rf"(?P<t>{_SINGLE})的?(?:{_TRIM}|减少)(?P<n>{_NUM})秒")
def _trim_by(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    return [_trim(rows, _single(m.group("t"), rows, fps), fps, None, None, _number(m.group("n")))]


def _cut_edge(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    head = m.group("e") in ("开头", "前面", "前", "片头")
    target = m.group("t")
    # Without a clip, “去掉开头/最后N秒” trims the video's first or last clip.
    i = _single(target, rows, fps) if target else (0 if head else len(rows) - 1)
    amount = _number(m.group("n"))
    return [_trim(rows, i, fps, None, amount if head else None, None if head else amount)]


_EDGE = r"开头|前面|前|片头|结尾|末尾|最后|片尾"
rule(rf"(?:{_CUT})(?:(?P<t>{_SINGLE})的?)?(?P<e>{_EDGE})的?(?P<n>{_NUM})秒")(_cut_edge)
rule(rf"(?P<t>{_SINGLE})的?(?:{_CUT})(?P<e>{_EDGE})的?(?P<n>{_NUM})秒")(_cut_edge)


@rule(
    rf"(?:去掉|取消|删掉|删除|移除|不要)(?:全部|所有)?的?(?:{_TR})|(?:全部|都)?(?:改成|改为|用)?(?:直接切换|硬切)"
)
def _remove_transitions(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    changed = [i for i, row in enumerate(rows) if row["transitionIn"]["type"] != "cut"]
    if not changed:
        raise CommandError("当前没有转场。")
    for i in changed:
        rows[i]["transitionIn"] = {"type": "cut", "frames": 0}
    return [f"去掉{len(changed)}处交叉淡化，全部直接切换"]


@rule(rf"(?:全部|所有|都)?(?:加|添加|增加|用|改成|改为)上?(?:{_TR})")
def _add_transitions(m: re.Match[str], rows: list[dict[str, Any]], fps: int) -> list[str]:
    frames = max(1, round(fps * 0.2))
    added = 0
    for i in range(1, len(rows)):
        if (
            rows[i]["transitionIn"]["type"] == "cut"
            and 2 * frames < _frames(rows[i], fps)
            and 2 * frames < _frames(rows[i - 1], fps)
        ):
            rows[i]["transitionIn"] = {"type": "crossfade", "frames": frames}
            added += 1
    if not added:
        raise CommandError("镜头太短或已有转场，没有可加交叉淡化的连接。")
    return [f"为{added}处连接加{frames}帧交叉淡化"]


# Generic delete/speed rules come last so specific trims and transitions win.
rule(rf"(?:{_DELETE})(?P<t>{_TARGET})")(_delete)
rule(rf"(?P<t>{_TARGET})(?:{_DELETE})")(_delete)
rule(rf"(?P<t>{_TARGET})(?:都|全部|统一)?的?(?P<s>{_FAST}|{_SLOW}|{_RESTORE})")(_speed_rule)
rule(rf"(?P<s>快放|慢放|加速|减速|放慢|加快)(?P<t>{_TARGET})")(_speed_rule)
rule(rf"(?P<s>恢复)(?P<t>{_TARGET})的?(?:原速|正常速度)")(_speed_rule)


def _clause(clause: str, rows: list[dict[str, Any]], fps: int) -> list[str]:
    for pattern, handler in _RULES:
        match = re.fullmatch(pattern, clause)
        if match:
            return handler(match, rows, fps)
    raise CommandError(f"没听懂“{clause}”。目前支持：{EXAMPLES}。")


def guard_transitions(rows: list[dict[str, Any]], fps: int) -> list[str]:
    """Shots too short for their crossfades fall back to cuts; returns the change notes."""
    changes = []
    rows[0]["transitionIn"] = {"type": "cut", "frames": 0}
    for i in range(1, len(rows)):
        frames = rows[i]["transitionIn"]["frames"]
        outgoing = rows[i + 1]["transitionIn"]["frames"] if i + 1 < len(rows) else 0
        if frames and (
            frames + outgoing >= _frames(rows[i], fps)
            or frames + rows[i - 1]["transitionIn"]["frames"] >= _frames(rows[i - 1], fps)
        ):
            rows[i]["transitionIn"] = {"type": "cut", "frames": 0}
            changes.append(f"第{i + 1}个镜头太短，入场淡化改为直接切换")
    return changes


def apply_timeline_command(text: object, clips: object, fps: object) -> dict[str, object]:
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        raise CommandError("请输入1–500字的修改要求。")
    rows = _check(clips, fps)
    assert isinstance(fps, int)
    before = max(s + _frames(r, fps) for s, r in zip(_starts(rows, fps), rows, strict=True))
    changes: list[str] = []
    # Clauses run in order; clip numbers always refer to the order after the previous clause.
    parts = re.split(r"[，,。；;！!\r\n]|然后|并且|接着|同时|再|并", text)
    for part in parts:
        clause = re.sub(r"^(?:请|帮我|把|将)+|(?:吧|了|一下)+$", "", re.sub(r"\s+", "", part))
        if clause:
            changes += _clause(clause, rows, fps)
    if not changes:
        raise CommandError("没有可执行的修改。")
    changes += guard_transitions(rows, fps)
    starts = _starts(rows, fps)
    after = max(s + _frames(r, fps) for s, r in zip(starts, rows, strict=True))
    return {
        "schemaVersion": "timeline-command-v1",
        "parser": "rule-v4-corpus",
        "clips": rows,
        "changes": changes,
        "beforeSeconds": before / fps,
        "afterSeconds": after / fps,
    }
