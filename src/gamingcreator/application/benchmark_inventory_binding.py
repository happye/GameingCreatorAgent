"""Bind a source-inventory report to frozen sources; evidence only, never assigns groups.

Pure functions over bytes and dicts: the freeze bundle stores the report bytes and the derived
document below is recomputed from them on every read, so a stored report is the only input.
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import PureWindowsPath
from typing import cast

from gamingcreator.application.source_inventory import LIMITATIONS, SCHEMA

INVENTORY_FILE = "source-inventory.json"
MAX_INVENTORY_BYTES = 4_194_304
SOURCE_STATUSES = ("compared", "notComparable", "failed", "absent")

_SHA = re.compile(r"[0-9a-f]{64}")
_REPORT_FIELDS = {
    "schemaVersion",
    "humanDecisionRequired",
    "parameters",
    "ffmpegVersion",
    "sources",
    "duplicateGroups",
    "notComparable",
    "failedSources",
    "sharedFootageCandidates",
    "limitations",
}
_SOURCE_FIELDS = {
    "sourceId",
    "path",
    "byteSize",
    "sha256",
    "durationUs",
    "video",
    "sampledFrames",
    "informativeFrames",
}
_VIDEO_FIELDS = {"codec", "width", "height", "frameRate"}
_DUPLICATE_FIELDS = {"sha256", "sourceIds", "paths"}
_SKIPPED_FIELDS = {"sourceId", "path", "informativeFrames", "sampledFrames", "reason"}
_FAILED_FIELDS = {"sourceId", "path", "code", "message"}
_INT_CANDIDATE = (
    "offsetSamples",
    "comparedVotes",
    "matchedVotes",
    "matchedFramesA",
    "clusterCount",
)
_FLOAT_CANDIDATE = (
    "offsetSeconds",
    "matchRate",
    "backgroundMatchRate",
    "correctedPValue",
    "log10CorrectedPValue",
    "aFirstSeconds",
    "aLastSeconds",
    "bFirstSeconds",
    "bLastSeconds",
)
_CANDIDATE_FIELDS = {"sourceA", "sourceB", "pathA", "pathB", *_INT_CANDIDATE, *_FLOAT_CANDIDATE}


def _bad(message: str) -> ValueError:
    return ValueError(f"素材盘点报告无效：{message}")


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise _bad("含重复JSON字段。")
        result[key] = value
    return result


def _nonfinite(value: str) -> object:
    raise _bad("不接受非有限数字。")


def _object(value: object, fields: set[str], name: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise _bad(f"{name}字段缺失或包含未知字段。")
    return cast(dict[str, object], value)


def _list(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise _bad(f"{name}必须是列表。")
    return cast(list[object], value)


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 16_384:
        raise _bad(f"{name}必须是非空文字。")
    return value


def _int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value < 2**63:
        raise _bad(f"{name}必须是有界整数。")
    return value


def _float(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(cast(float, value)):
        raise _bad(f"{name}必须是有限数字。")
    return float(cast(float, value))


def parse_inventory(data: bytes) -> dict[str, object]:
    """Strictly validate one ``source-inventory-v1`` report; the bytes stay the source of truth."""
    if len(data) > MAX_INVENTORY_BYTES:
        raise _bad("超过4MiB上限，未静默放宽。")
    try:
        loaded = json.loads(
            data.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_nonfinite
        )
    except (UnicodeError, RecursionError, json.JSONDecodeError):
        raise _bad("不是有效的UTF-8 JSON。") from None
    report = _object(loaded, _REPORT_FIELDS, "报告")
    if report["schemaVersion"] != SCHEMA:
        raise _bad("版本不是source-inventory-v1。")
    if report["humanDecisionRequired"] is not True:
        raise _bad("humanDecisionRequired必须为true。")
    if report["limitations"] != list(LIMITATIONS):
        raise _bad("限制说明与生成端不一致。")
    _text(report["ffmpegVersion"], "ffmpegVersion")
    parameters = report["parameters"]
    if type(parameters) is not dict or not parameters:
        raise _bad("parameters必须是非空对象。")
    known: dict[str, dict[str, object]] = {}
    for item in _list(report["sources"], "sources"):
        row = _object(item, _SOURCE_FIELDS, "来源")
        identifier = _text(row["sourceId"], "sourceId")
        if identifier in known:
            raise _bad("sourceId重复。")
        _text(row["path"], "path")
        _int(row["byteSize"], "byteSize")
        if type(row["sha256"]) is not str or _SHA.fullmatch(row["sha256"]) is None:
            raise _bad("sha256格式无效。")
        _int(row["durationUs"], "durationUs", minimum=1)
        video = _object(row["video"], _VIDEO_FIELDS, "video")
        _text(video["codec"], "codec")
        _int(video["width"], "width", minimum=1)
        _int(video["height"], "height", minimum=1)
        _text(video["frameRate"], "frameRate")
        sampled = _int(row["sampledFrames"], "sampledFrames")
        if _int(row["informativeFrames"], "informativeFrames") > sampled:
            raise _bad("有效帧数不能超过采样帧数。")
        known[identifier] = row
    skipped: set[str] = set()
    for item in _list(report["notComparable"], "notComparable"):
        row = _object(item, _SKIPPED_FIELDS, "未比较来源")
        identifier = _text(row["sourceId"], "sourceId")
        if (
            identifier not in known
            or identifier in skipped
            or row["path"] != known[identifier]["path"]
        ):
            raise _bad("未比较来源引用未知或重复来源。")
        _int(row["informativeFrames"], "informativeFrames")
        _int(row["sampledFrames"], "sampledFrames")
        _text(row["reason"], "reason")
        skipped.add(identifier)
    failed: set[str] = set()
    for item in _list(report["failedSources"], "failedSources"):
        row = _object(item, _FAILED_FIELDS, "失败来源")
        identifier = _text(row["sourceId"], "sourceId")
        if identifier in known or identifier in failed:
            raise _bad("失败来源编号重复。")
        _text(row["path"], "path")
        _text(row["code"], "code")
        _text(row["message"], "message")
        failed.add(identifier)
    for item in _list(report["duplicateGroups"], "duplicateGroups"):
        row = _object(item, _DUPLICATE_FIELDS, "重复组")
        identifiers = _list(row["sourceIds"], "sourceIds")
        if (
            len(identifiers) < 2
            or any(type(value) is not str or value not in known for value in identifiers)
            or {known[cast(str, value)]["sha256"] for value in identifiers} != {row["sha256"]}
            or len(_list(row["paths"], "paths")) != len(identifiers)
        ):
            raise _bad("重复组与来源不一致。")
    for item in _list(report["sharedFootageCandidates"], "sharedFootageCandidates"):
        row = _object(item, _CANDIDATE_FIELDS, "共用画面候选")
        first, second = row["sourceA"], row["sourceB"]
        if (
            type(first) is not str
            or type(second) is not str
            or first not in known
            or second not in known
            or first == second
            or row["pathA"] != known[first]["path"]
            or row["pathB"] != known[second]["path"]
            or known[first]["sha256"] == known[second]["sha256"]
        ):
            raise _bad("共用画面候选引用未知来源或同字节副本。")
        for key in _INT_CANDIDATE:
            _int(row[key], key, minimum=-(2**62))
        for key in _FLOAT_CANDIDATE:
            _float(row[key], key)
        if cast(int, row["matchedVotes"]) > cast(int, row["comparedVotes"]):
            raise _bad("相近票数不能超过可比票数。")
    return report


def _path_key(path: str) -> str:
    return str(PureWindowsPath(path)).casefold()


def derive_source_inventory(
    data: bytes, frozen_sources: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """Per-frozen-source coverage and shared-footage pairs mapped to frozen ids."""
    report = parse_inventory(data)
    inventory = {
        cast(str, row["sourceId"]): row for row in cast(list[dict[str, object]], report["sources"])
    }
    skipped = {
        cast(str, row["sourceId"]) for row in cast(list[dict[str, object]], report["notComparable"])
    }
    failed_by_path: dict[str, list[str]] = {}
    for row in cast(list[dict[str, object]], report["failedSources"]):
        failed_by_path.setdefault(_path_key(cast(str, row["path"])), []).append(
            cast(str, row["sourceId"])
        )
    by_sha: dict[str, list[str]] = {}
    for identifier, row in inventory.items():
        by_sha.setdefault(cast(str, row["sha256"]), []).append(identifier)
    frozen_ids: dict[str, list[str]] = {}
    rows: list[dict[str, object]] = []
    for source in frozen_sources:
        identifier = cast(str, source["id"])
        matches = by_sha.get(cast(str, source["sha256"]), [])
        if any(inventory[value]["durationUs"] != source["durationUs"] for value in matches):
            raise _bad("同一SHA256的时长与冻结来源不同，输入不一致。")
        if matches:
            status = (
                "compared" if any(value not in skipped for value in matches) else "notComparable"
            )
            related = list(matches)
        else:
            related = failed_by_path.get(_path_key(cast(str, source["path"])), [])
            status = "failed" if related else "absent"
        rows.append({"id": identifier, "status": status, "inventorySourceIds": list(related)})
        for value in matches:
            frozen_ids.setdefault(value, []).append(identifier)
    pairs: list[dict[str, object]] = []
    unplanned = 0
    for item in cast(list[dict[str, object]], report["sharedFootageCandidates"]):
        first = frozen_ids.get(cast(str, item["sourceA"]), [])
        second = frozen_ids.get(cast(str, item["sourceB"]), [])
        if not first or not second:
            unplanned += 1
            continue
        for left in first:
            for right in second:
                pairs.append(
                    {
                        "sourceA": left,
                        "sourceB": right,
                        "inventorySourceA": item["sourceA"],
                        "inventorySourceB": item["sourceB"],
                        "offsetSamples": item["offsetSamples"],
                        "offsetSeconds": item["offsetSeconds"],
                        "comparedVotes": item["comparedVotes"],
                        "matchedVotes": item["matchedVotes"],
                        "log10CorrectedPValue": item["log10CorrectedPValue"],
                    }
                )
    return {
        "reportSha256": hashlib.sha256(data).hexdigest(),
        "reportVersion": report["schemaVersion"],
        "parameters": report["parameters"],
        "ffmpegVersion": report["ffmpegVersion"],
        "sources": rows,
        "sharedFootage": pairs,
        "unplannedSourceEvidenceCount": unplanned,
        "limitations": report["limitations"],
        "humanDecisionRequired": True,
        "absenceIsNotIndependence": True,
    }


def inventory_blockers(
    derived: Mapping[str, object] | None, policy: Mapping[str, tuple[str | None, str]]
) -> set[str]:
    """Blockers from the derived document; ``policy`` is ``{source id: (group, partition)}``."""
    if derived is None:
        return {"source_inventory_missing"}
    rows = cast(list[dict[str, object]], derived["sources"])
    if {cast(str, row["id"]) for row in rows} != set(policy) or len(rows) != len(policy):
        raise ValueError("素材盘点来源与冻结来源不一致。")
    states = {row["status"] for row in rows}
    if not states <= set(SOURCE_STATUSES):
        raise ValueError("素材盘点来源状态无效。")
    blockers: set[str] = set()
    if states & {"absent", "failed"}:
        blockers.add("source_inventory_incomplete")
    if "notComparable" in states:
        blockers.add("source_inventory_not_comparable")
    for pair in cast(list[dict[str, object]], derived["sharedFootage"]):
        group_a, partition_a = policy[cast(str, pair["sourceA"])]
        group_b, partition_b = policy[cast(str, pair["sourceB"])]
        if group_a is not None and group_b is not None and group_a != group_b:
            blockers.add("shared_footage_has_different_recording_groups")
        if partition_a != partition_b:
            blockers.add("shared_footage_crosses_partitions")
    return blockers


def inventory_result(derived: Mapping[str, object] | None) -> dict[str, object]:
    """Short coverage summary for the CLI result; no evidence is never reported as independence."""
    note = "未发现共用画面证据不等于独立；录制组仍须人工确认。"
    if derived is None:
        return {"provided": False, "note": "未提供素材盘点报告，冻结已记录阻断。" + note}
    counts = {name: 0 for name in SOURCE_STATUSES}
    for row in cast(list[dict[str, object]], derived["sources"]):
        counts[cast(str, row["status"])] += 1
    pairs = cast(list[object], derived["sharedFootage"])
    return {
        "provided": True,
        "reportSha256": derived["reportSha256"],
        "sourceStatusCounts": counts,
        "sharedFootagePairs": len(pairs),
        "note": ("共用画面证据为 0 对（无证据）。" if not pairs else "已列出共用画面证据。") + note,
    }
