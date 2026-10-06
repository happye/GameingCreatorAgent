"""Bind local human review to an exact regenerated pilot template; no I/O or scoring."""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import cast

MAX_REVIEW_BYTES = 1_048_576
DIMENSIONS = (
    "objectMistakenForActor",
    "shotBoundariesAreReal",
    "positiveDescriptionsRetained",
    "queriedClipUsable",
)
EDITABLE_CASE_FIELDS = frozenset((*DIMENSIONS, "reviewedTemporalEntityIds", "statement"))
EDITABLE_ROOT_FIELDS = frozenset(("recordedOn", "reviewer", "cases"))


@dataclass(frozen=True, slots=True)
class PilotReview:
    payload_json: str
    recorded_on: str | None
    reviewer: str | None
    judged_case_ids: tuple[str, ...]


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("人工记录必须使用JSON对象。")
    return cast(dict[str, object], value)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("人工记录包含重复JSON字段。")
        result[key] = value
    return result


def _nonfinite(value: str) -> object:
    raise ValueError("人工记录不接受非有限数字。")


def canonical_review_json(value: object) -> str:
    try:
        return (
            json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
        )
    except (TypeError, ValueError, RecursionError):
        raise ValueError("人工记录不是有效的有界JSON。") from None


def _text(value: object, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError("填写人或说明必须是长度合适的非空文字。")
    return value


def _cases(value: object) -> dict[str, dict[str, object]]:
    if type(value) is not list or len(value) != 2:
        raise ValueError("人工记录必须包含原来的两个候选。")
    result = {}
    for raw in value:
        row = _object(raw)
        key = _text(row.get("caseId"), 128)
        if key in result:
            raise ValueError("人工记录包含重复候选。")
        result[key] = row
    return result


def review_entity_ids(comparison: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Extract only entity IDs from the caller's current, source-validated comparison."""
    result: dict[str, tuple[str, ...]] = {}
    for key, row in _cases(comparison["cases"]).items():
        temporal = _object(row["temporal"])
        scene = temporal["scene"]
        if scene is None:
            if temporal["payloadHash"] is not None or temporal["state"] != "no_saved_result":
                raise ValueError("新版来源状态不一致。")
            result[key] = ()
            continue
        entities = _object(scene)["entities"]
        if type(entities) is not list or len(entities) > 72:
            raise ValueError("新版实体来源不正确。")
        ids = tuple(_text(_object(raw)["entityId"], 128) for raw in entities)
        if len(set(ids)) != len(ids) or temporal["payloadHash"] is None:
            raise ValueError("新版实体来源不正确。")
        result[key] = ids
    return result


def validate_pilot_review(
    text: str,
    *,
    expected_template: dict[str, object],
    entity_ids_by_case: dict[str, tuple[str, ...]],
) -> PilotReview:
    """Expected identities must come from current source validation, never the uploaded record."""
    if type(text) is not str:
        raise ValueError("人工记录必须是JSON文字。")
    try:
        if len(text.encode("utf-8")) > MAX_REVIEW_BYTES:
            raise ValueError("人工记录不能超过1MiB。")
        record = _object(json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite))
        canonical_review_json(record).encode("utf-8")
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("人工记录不是有效的UTF-8 JSON。") from None
    if set(record) != set(expected_template):
        raise ValueError("人工记录字段缺失或多出。")
    readonly = set(record) - EDITABLE_ROOT_FIELDS
    if canonical_review_json({key: record[key] for key in readonly}) != canonical_review_json(
        {key: expected_template[key] for key in readonly}
    ):
        raise ValueError("人工记录的冻结来源或验收边界已改变。")
    recorded_on, reviewer = record["recordedOn"], record["reviewer"]
    if (recorded_on is None) != (reviewer is None):
        raise ValueError("日期和填写人须同时填写或同时留空。")
    if recorded_on is not None:
        recorded_on = _text(recorded_on, 10)
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", recorded_on):
            raise ValueError("日期须使用YYYY-MM-DD。")
        try:
            date.fromisoformat(recorded_on)
        except ValueError:
            raise ValueError("人工记录日期不存在。") from None
        reviewer = _text(reviewer, 120)
    expected_rows, rows = _cases(expected_template["cases"]), _cases(record["cases"])
    if set(rows) != set(expected_rows) or set(entity_ids_by_case) != set(expected_rows):
        raise ValueError("人工记录候选与当前来源不一致。")
    judged = []
    ordered = []
    for key, expected in expected_rows.items():
        row = rows[key]
        if set(row) != set(expected):
            raise ValueError("候选记录字段缺失或多出。")
        anchors = set(expected) - EDITABLE_CASE_FIELDS
        if canonical_review_json({name: row[name] for name in anchors}) != canonical_review_json(
            {name: expected[name] for name in anchors}
        ):
            raise ValueError("候选、模型结果或原画面与当前来源不一致。")
        values = [row[name] for name in DIMENSIONS]
        if any(value is not None and type(value) is not bool for value in values):
            raise ValueError("四个判断只能填写true、false或null。")
        targets = row["reviewedTemporalEntityIds"]
        if targets is not None:
            if (
                type(targets) is not list
                or not 1 <= len(targets) <= 72
                or any(type(target) is not str for target in targets)
                or len(set(cast(list[str], targets))) != len(targets)
                or any(target not in entity_ids_by_case[key] for target in targets)
            ):
                raise ValueError("只可引用当前新版结果中不重复的实体。")
        statement = row["statement"]
        if statement is not None:
            _text(statement, 2048)
        has_judgment = any(value is not None for value in values)
        has_content = has_judgment or targets is not None or statement is not None
        if expected["temporalPayloadHash"] is None and has_content:
            raise ValueError("新版暂无真实结果，不能填写判断、实体或说明。")
        if has_content and (recorded_on is None or reviewer is None):
            raise ValueError("填写核对内容前须登记日期和填写人。")
        if has_judgment and statement is None:
            raise ValueError("填写判断时须说明画面依据。")
        if has_judgment:
            judged.append(key)
        ordered.append(row)
    record["cases"] = ordered
    return PilotReview(
        canonical_review_json(record),
        recorded_on,
        cast(str | None, reviewer),
        tuple(judged),
    )
