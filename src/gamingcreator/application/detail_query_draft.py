"""Finite positive query grammar with complete original-text accounting; no I/O."""

import json
import re
from dataclasses import dataclass
from typing import Literal, TypedDict

from gamingcreator.domain.actor_details import (
    MAX_QUERY_CONDITIONS,
    AttributeConstraint,
    AttributeKind,
    QueryConstraint,
    attribute_value_options,
    canonical_constraint_json,
    normalize_attribute_value,
    values_are_exclusive,
)

DRAFT_SCHEMA_VERSION = "actor-detail-query-draft-v1"
MAX_DRAFT_CHARACTERS = 2048


class _Span(TypedDict):
    start: int
    end: int
    text: str
    kind: Literal["recognized", "connector", "unparsed"]
    reason: str


@dataclass(frozen=True, slots=True)
class _Rule:
    pattern: re.Pattern[str]
    conditions: tuple[tuple[AttributeKind, str], ...]
    family: str


_COLORS = {
    "white": ("白", "白色", "white"),
    "black": ("黑", "黑色", "black"),
    "red": ("红", "红色", "red"),
    "blue": ("蓝", "蓝色", "blue"),
    "brown": ("棕", "棕色", "brown"),
    "orange": ("橙", "橙色", "orange"),
    "gray": ("灰", "灰色", "gray", "grey"),
    "green": ("绿", "绿色", "green"),
    "yellow": ("黄", "黄色", "yellow"),
    "purple": ("紫", "紫色", "purple"),
    "light": ("浅色", "light-colored", "light coloured"),
    "dark": ("深色", "dark-colored", "dark coloured"),
}
_GARMENTS = {
    "upper_garment": ("上装", "top", "upper garment"),
    "coat": ("外套", "coat", "jacket"),
    "scarf": ("围巾", "scarf"),
    "shorts": ("短裤", "shorts"),
    "trousers": ("长裤", "trousers", "pants"),
    "armor": ("盔甲", "armor", "armour"),
    "gloves": ("手套", "gloves"),
}
_ALIASES: dict[AttributeKind, dict[str, tuple[str, ...]]] = {
    AttributeKind.HELD_SHAPE: {
        "flat_object": ("扁平物体", "扁平物", "flat object"),
        "blue_flat_object": ("蓝色扁平物体", "蓝色扁平物", "blue flat object"),
        "long_rod": ("长杆", "long rod"),
        "curved_object": ("弯曲物体", "curved object"),
    },
    AttributeKind.HELD_CLASS: {
        "weapon": ("武器", "weapon"),
        "staff": ("权杖", "staff"),
        "tool": ("工具", "tool"),
    },
    AttributeKind.ACTION: {
        "look_up": ("抬头", "look up", "looking up"),
        "move": ("移动", "move", "moving"),
        "run": ("奔跑", "run", "running"),
        "jump": ("跳跃", "jump", "jumping"),
        "raise_item": ("举起持有物", "raise item", "raising item"),
        "shoot": ("射击", "shoot", "shooting"),
    },
    AttributeKind.EFFECT: {
        "light_arc": ("光弧", "light arc"),
        "light_ring": ("光环", "light ring"),
        "projectile": ("投射物", "projectile"),
    },
    AttributeKind.ENVIRONMENT: {
        "water": ("水面", "water"),
        "stone_platform": ("石块平台", "stone platform"),
        "sandy_ground": ("沙地", "sandy ground"),
        "indoors": ("室内", "indoors"),
        "outdoors": ("室外", "outdoors"),
    },
}
_LABELS = {
    AttributeKind.HAIR_COLOR: "发色",
    AttributeKind.CLOTHING_COLOR: "衣物颜色",
    AttributeKind.CLOTHING_SHAPE: "衣物形状",
    AttributeKind.HELD_SHAPE: "持有物形状",
    AttributeKind.HELD_CLASS: "持有物类别",
    AttributeKind.ACTION: "动作",
    AttributeKind.EFFECT: "可见效果",
    AttributeKind.ENVIRONMENT: "环境",
}


def _phrase(value: str) -> str:
    return r"\s+".join(re.escape(word) for word in value.split(" "))


def _pattern(value: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + value + r")(?![A-Za-z0-9_])", re.IGNORECASE)


def _logic_pattern(chinese: str, english: str) -> re.Pattern[str]:
    return re.compile(
        r"(?:" + chinese + r")|(?<![A-Za-z0-9_])(?:" + english + r")(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )


def _chinese(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _rules() -> tuple[_Rule, ...]:
    rules = []

    def add(pattern: str, family: str, *atoms: tuple[AttributeKind, str]) -> None:
        normalized = tuple((kind, normalize_attribute_value(kind, value)) for kind, value in atoms)
        rules.append(_Rule(_pattern(pattern), normalized, family))

    for color, aliases in _COLORS.items():
        for alias in aliases:
            expression = (
                r"(?:有着|有)?" + _phrase(alias) + r"的?(?:头发|发)"
                if _chinese(alias)
                else r"(?:with\s+)?" + _phrase(alias) + r"(?:\s+hair|[-\s]haired)"
            )
            add(expression, "hair", (AttributeKind.HAIR_COLOR, color))
    for shape, aliases in _GARMENTS.items():
        for alias in aliases:
            chinese = _chinese(alias)
            prefix = (
                r"(?:穿着|身穿|穿|戴着)?(?:一件|一条|一双)?"
                if chinese
                else r"(?:wearing\s+)?(?:a\s+|an\s+)?"
            )
            add(prefix + _phrase(alias), "clothing", (AttributeKind.CLOTHING_SHAPE, shape))
            for color, color_aliases in _COLORS.items():
                for color_alias in color_aliases:
                    if _chinese(color_alias) != chinese:
                        continue
                    pattern = (
                        prefix
                        + _phrase(color_alias)
                        + (r"的?" if chinese else r"\s+")
                        + _phrase(alias)
                    )
                    add(
                        pattern,
                        "clothing",
                        (AttributeKind.CLOTHING_COLOR, color),
                        (AttributeKind.CLOTHING_SHAPE, shape),
                    )
    for kind, values in _ALIASES.items():
        for value, aliases in values.items():
            for alias in aliases:
                prefix = suffix = ""
                if kind in (AttributeKind.HELD_SHAPE, AttributeKind.HELD_CLASS):
                    prefix = (
                        r"(?:拿着|手持|持有|握着)?(?:一个|一根|一件)?"
                        if _chinese(alias)
                        else r"(?:(?:holding|holds|carrying)\s+)?(?:a\s+|an\s+)?"
                    )
                elif kind == AttributeKind.ENVIRONMENT:
                    prefix = (
                        r"(?:在|背景是|场景是|环境是)?"
                        if _chinese(alias)
                        else r"(?:(?:on|in|at)\s+(?:(?:the|a|an)\s+)?)?"
                    )
                    suffix = r"(?:上|里|中)?" if _chinese(alias) else ""
                add(
                    prefix + _phrase(alias) + suffix,
                    "held" if kind.value.startswith("held_") else kind.value,
                    (kind, value),
                )
    return tuple(rules)


_RULES = _rules()
_SUBJECT = _pattern(
    r"(?:同一(?:个|名)|一(?:个|名)|这个|这名)?(?:角色|人物|人)"
    r"|(?:(?:a|the|same|one)\s+)?(?:character|person|actor)"
)
_COMMAND = _pattern(
    r"请?(?:找出|查找|寻找|搜索|查询|找到|找)|(?:find|show|search for)(?:\s+me)?(?:\s+clips?\s+of)?"
)
_AND = _pattern(r"以及|并且|而且|和|且|与|并|and")
_DE = re.compile("的")
_FORBIDDEN = (
    (
        _logic_pattern(
            r"不是|不要|没有|并非|而非|不|没|未(?!知)|无|非",
            r"without|not|no|never|neither|nor|isn['’]t|is\s+not|don['’]t|doesn['’]t|didn['’]t"
            r"|instead\s+of|rather\s+than",
        ),
        "否定或替代条件尚未支持，不能转换为肯定条件。",
    ),
    (
        _logic_pattern(r"或者|或是|或|还是|任一|其中之一|(?<!<)/|／|\|", r"or|and/or|either"),
        "或者/任选条件尚未支持，不能转换为全部满足。",
    ),
    (
        _logic_pattern(
            r"先|然后|随后|之后|之前|后|前|时|再|接着|同时|一直|全程|持续|逐渐|突然",
            r"then|before|after|while|followed\s+by|always",
        ),
        "先后、持续或同时关系尚未支持。",
    ),
    (
        _logic_pattern(
            r"旁边|身后|前面|后面|左侧|右侧|对面|之间|靠近|面对|朝着|对着|跟着|攻击|击中|追着|一起",
            r"beside|behind|in\s+front\s+of|next\s+to|near|facing|towards|attacking|chasing|together\s+with",
        ),
        "人物之间、位置或交互关系尚未支持。",
    ),
    (
        _logic_pattern(
            r"(?:两个|两名|三个|三名|多个|多名|另一个|另一名|不同|其他)(?=.{0,30}(?:角色|人物|人))",
            r"(?:two|three|both|multiple|several|another|other)(?=.{0,60}\b(?:characters?|persons?|people|actors?)\b)|characters|people|actors|persons",
        ),
        "多个主体条件尚未支持，不能合成同一人物条件。",
    ),
    (
        _logic_pattern(
            r"(?:和|与)(?=(?:一个|一名).{0,30}(?:角色|人物|人))",
            r"with(?=.{0,80}\b(?:character|person|actor)\b)"
            r"|and(?=\s+(?:a|an|one|the|another)\b.{0,70}\b(?:character|person|actor)\b)",
        ),
        "多个主体或主体之间的关系尚未支持。",
    ),
)
_ITEM_SEPARATOR = _logic_pattern(r"[,，、;；。.]|以及|并且|和|与", r"and")
_PUNCTUATION = frozenset(",，、。.;；:：!?！？")
_UNKNOWN = "这段文字尚未支持，未加入条件。"


def _span(
    text: str,
    start: int,
    end: int,
    kind: Literal["recognized", "connector", "unparsed"],
    reason: str,
) -> _Span:
    return {"start": start, "end": end, "text": text[start:end], "kind": kind, "reason": reason}


def draft_detail_query(text: str) -> dict[str, object]:
    """Draft a bounded manifest; the caller must obtain explicit user confirmation."""
    if type(text) is not str or len(text) > MAX_DRAFT_CHARACTERS:
        raise ValueError("Detail query draft requires at most 2048 Unicode characters.")
    if any("\ud800" <= character <= "\udfff" for character in text):
        raise ValueError("Detail query draft requires valid Unicode scalar values.")
    spans: list[_Span] = []
    connector_roles: dict[int, str] = {}
    actor: list[AttributeConstraint] = []
    environment: list[AttributeConstraint] = []
    families = {"clothing": 0, "held": 0}
    signatures: set[tuple[tuple[AttributeKind, str], ...]] = set()
    condition_count = 0
    unsupported = len(tuple(_SUBJECT.finditer(text))) > 1
    last_held_end: int | None = None
    ambiguous_held = False
    position = 0
    while position < len(text):
        forbidden = next(
            (
                (pattern.match(text, position), reason)
                for pattern, reason in _FORBIDDEN
                if pattern.match(text, position)
            ),
            None,
        )
        if forbidden is not None:
            match, reason = forbidden
            assert match is not None
            spans.append(_span(text, position, match.end(), "unparsed", reason))
            unsupported = True
            position = match.end()
            continue
        candidates = [
            (match, rule)
            for rule in _RULES
            if (match := rule.pattern.match(text, position)) is not None
        ]
        if candidates:
            match, rule = max(candidates, key=lambda candidate: candidate[0].end())
            condition_count += len(rule.conditions)
            group = (
                rule.family + str(families[rule.family] + 1)
                if rule.family in families
                else rule.family
            )
            conditions = [
                AttributeConstraint(kind, value, group) for kind, value in rule.conditions
            ]
            reason = ""
            if condition_count > MAX_QUERY_CONDITIONS:
                unsupported = True
                reason = "条件总数超过16项，不能截取一部分代替原要求。"
            elif (
                rule.family == "held"
                and last_held_end is not None
                and _ITEM_SEPARATOR.search(text[last_held_end:position]) is None
            ):
                ambiguous_held = True
                reason = "相邻持有物描述可能指同一物体，不能自动拆成多个对象；请明确编辑。"
            elif rule.conditions in signatures:
                reason = "重复出现同一条件，暂保留第一次；请确认是否确实需要多个对象。"
            elif any(
                old.kind == new.kind
                and old.part_group == new.part_group
                and values_are_exclusive(new.kind, old.value, new.value)
                for old in actor + environment
                for new in conditions
            ):
                reason = "同一部件有互斥条件，请修改或明确只核对哪一部分。"
            if reason:
                spans.append(_span(text, position, match.end(), "unparsed", reason))
            else:
                if rule.family in families:
                    families[rule.family] += 1
                signatures.add(rule.conditions)
                target = environment if rule.family == "environment" else actor
                target.extend(conditions)
                labels = [
                    f"{_LABELS[item.kind]}：{dict(attribute_value_options(item.kind))[item.value]}"
                    for item in conditions
                ]
                spans.append(
                    _span(
                        text,
                        position,
                        match.end(),
                        "recognized",
                        "已识别为" + "、".join(labels) + "。",
                    )
                )
            if rule.family == "held":
                last_held_end = match.end()
            position = match.end()
            continue
        if text[position].isspace() or text[position] in _PUNCTUATION:
            end = position + 1
            while end < len(text) and (text[end].isspace() or text[end] in _PUNCTUATION):
                end += 1
            spans.append(_span(text, position, end, "connector", "保留原句空白或分隔标点。"))
            position = end
            continue
        connector = next(
            (
                (pattern.match(text, position), role)
                for pattern, role in (
                    (_COMMAND, "command"),
                    (_SUBJECT, "subject"),
                    (_AND, "and"),
                    (_DE, "de"),
                )
                if pattern.match(text, position)
            ),
            None,
        )
        if connector is not None:
            match, role = connector
            assert match is not None
            index = len(spans)
            spans.append(
                _span(text, position, match.end(), "connector", "明确的同主体查询连接词。")
            )
            connector_roles[index] = role
            position = match.end()
            continue
        if spans and spans[-1]["kind"] == "unparsed" and spans[-1]["reason"] == _UNKNOWN:
            spans[-1]["end"] = position + 1
            spans[-1]["text"] = text[spans[-1]["start"] : position + 1]
        else:
            spans.append(_span(text, position, position + 1, "unparsed", _UNKNOWN))
        position += 1
    for index, role in connector_roles.items():
        before = next(
            (item for item in reversed(spans[:index]) if item["kind"] != "connector"), None
        )
        after = next((item for item in spans[index + 1 :] if item["kind"] != "connector"), None)
        valid = bool(actor) and (
            (role == "command" and before is None)
            or role == "subject"
            or (
                role == "and"
                and before is not None
                and after is not None
                and before["kind"] == after["kind"] == "recognized"
            )
            or (
                role == "de"
                and before is not None
                and before["kind"] == "recognized"
                and any(
                    candidate == "subject"
                    for number, candidate in connector_roles.items()
                    if number == index + 1
                )
            )
        )
        if not valid or (unsupported and role == "subject"):
            spans[index]["kind"] = "unparsed"
            spans[index]["reason"] = (
                "多个主体尚未支持。"
                if unsupported and role == "subject"
                else "该连接词没有完整的已支持上下文。"
            )
    if not actor:
        for item in spans:
            if item["kind"] == "recognized":
                item["kind"] = "unparsed"
                item["reason"] = "只有环境条件还不能形成同主体查询，请补充人物条件。"
    unparsed = [item.copy() for item in spans if item["kind"] == "unparsed"]
    constraint = (
        None
        if unsupported or ambiguous_held or not actor
        else json.loads(
            canonical_constraint_json(QueryConstraint(tuple(actor), tuple(environment)))
        )
    )
    status = (
        "unsupported"
        if unsupported or not text.strip()
        else "needs_review"
        if unparsed or not actor
        else "ready"
    )
    return {
        "schemaVersion": DRAFT_SCHEMA_VERSION,
        "originalText": text,
        "status": status,
        "spanOffsetUnit": "unicode-code-point",
        "constraint": constraint,
        "spans": spans,
        "unparsed": unparsed,
    }
