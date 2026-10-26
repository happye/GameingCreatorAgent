"""Incomplete pre-inference registration drafts; no source I/O or human labels."""

from copy import deepcopy
from pathlib import PureWindowsPath
from typing import cast

from gamingcreator.application.benchmark_inventory_binding import parse_inventory
from gamingcreator.application.benchmark_preparation import (
    MAX_PLAN_BYTES,
    BenchmarkPlan,
    canonical_json,
    loads_plan,
)
from gamingcreator.application.benchmark_review import decode_object

DRAFT_VERSION = "benchmark-plan-draft-v1"
EVIDENCE_VERSION = "benchmark-plan-evidence-v1"


def empty_draft() -> dict[str, object]:
    return {"schemaVersion": DRAFT_VERSION, "datasetId": "", "sources": [], "queries": []}


def _text(value: object) -> None:
    if type(value) is not str or len(value) > 16_384:
        raise ValueError("登记文字必须为有界字符串。")


def validate_draft(document: dict[str, object]) -> dict[str, object]:
    if (
        set(document) != {"schemaVersion", "datasetId", "sources", "queries"}
        or document["schemaVersion"] != DRAFT_VERSION
        or len(canonical_json(document)) > MAX_PLAN_BYTES
    ):
        raise ValueError("登记草稿版本、字段或尺寸无效。")
    _text(document["datasetId"])
    for name, maximum in (("sources", 200), ("queries", 1000)):
        rows = document[name]
        if type(rows) is not list or len(rows) > maximum:
            raise ValueError("登记清单超出允许范围。")
        for row in rows:
            fields = (
                {"id", "path", "recordingGroup", "partition", "modelResultsViewed"}
                if name == "sources"
                else {"id", "text", "kind", "sourceId", "family"}
            )
            if type(row) is not dict or set(row) != fields:
                raise ValueError("登记条目字段无效。")
            for key in fields - {"recordingGroup", "modelResultsViewed"}:
                _text(row[key])
            if name == "sources":
                if row["partition"] not in ("", "development", "test") or (
                    row["modelResultsViewed"] is not None
                    and type(row["modelResultsViewed"]) is not bool
                ):
                    raise ValueError("分区或已看结果声明无效。")
                if row["recordingGroup"] is not None:
                    _text(row["recordingGroup"])
            elif row["kind"] not in ("", "main", "sparse", "negative"):
                raise ValueError("查询类别无效。")
    return deepcopy(document)


def decode_draft(data: bytes) -> dict[str, object]:
    if len(data) > MAX_PLAN_BYTES:
        raise ValueError("登记草稿不能超过1MiB。")
    return validate_draft(decode_object(data))


def plan_to_draft(plan: BenchmarkPlan) -> dict[str, object]:
    document = plan.document
    if (
        document["labelVersion"] is not None
        or document["humanReferences"] != {"confirmed": False, "annotators": [], "reviewed": False}
        or any(row["referenceEvents"] for row in cast(list[dict[str, object]], document["queries"]))
    ):
        raise ValueError("已含人工参考的计划请用原片标注继续，不在登记页修改。")
    return validate_draft(
        {
            "schemaVersion": DRAFT_VERSION,
            "datasetId": document["datasetId"],
            "sources": document["sources"],
            "queries": [
                {key: value for key, value in row.items() if key != "referenceEvents"}
                for row in cast(list[dict[str, object]], document["queries"])
            ],
        }
    )


def draft_to_plan(document: dict[str, object]) -> BenchmarkPlan:
    draft = validate_draft(document)
    for row in cast(list[dict[str, object]], draft["sources"]):
        if not PureWindowsPath(cast(str, row["path"])).is_absolute():
            raise ValueError("导出前请填写录像完整本地路径。")
        if row["recordingGroup"] is not None:
            row["recordingGroup"] = cast(str, row["recordingGroup"]).strip() or None
    return loads_plan(
        canonical_json(
            {
                "schemaVersion": "benchmark-plan-v1",
                "datasetId": draft["datasetId"],
                "labelVersion": None,
                "humanReferences": {"confirmed": False, "annotators": [], "reviewed": False},
                "sources": draft["sources"],
                "queries": [
                    {**row, "referenceEvents": []}
                    for row in cast(list[dict[str, object]], draft["queries"])
                ],
            }
        ).decode()
    )


def _minutes(duration_us: int) -> str:
    seconds = duration_us // 1_000_000
    return f"{seconds // 60}分{seconds % 60:02d}秒"


def inventory_to_draft(data: bytes) -> tuple[dict[str, object], dict[str, object]]:
    """Start a registration draft from a source-inventory report.

    Only identity fields (source ID and path) are filled. Recording group, purpose and the
    model-results declaration stay unknown: the inventory is evidence for the person who
    decides, never a default. Evidence notes are returned separately, keyed by source ID,
    and are not part of the draft or of any exported plan.
    """
    report = parse_inventory(data)
    sources = cast(list[dict[str, object]], report["sources"])
    failed = cast(list[dict[str, object]], report["failedSources"])
    # Notes follow a file by path on the page, so one path listed twice would mix them up.
    paths = [cast(str, row["path"]).casefold() for row in [*sources, *failed]]
    if len(set(paths)) != len(paths):
        raise ValueError("The inventory lists one path more than once.")
    notes: dict[str, list[str]] = {}
    overlapping: set[str] = set()
    durations: dict[str, int] = {}
    for row in sources:
        identifier = cast(str, row["sourceId"])
        video = cast(dict[str, object], row["video"])
        durations[identifier] = cast(int, row["durationUs"])
        notes[identifier] = [
            f"时长 {_minutes(cast(int, row['durationUs']))}，{video['width']}×{video['height']}，"
            f"{video['codec']}"
        ]
    for row in failed:
        notes[cast(str, row["sourceId"])] = [f"盘点失败（{row['code']}）：{row['message']}"]
    for row in cast(list[dict[str, object]], report["notComparable"]):
        notes[cast(str, row["sourceId"])].append(
            f"有效画面 {row['informativeFrames']}/{row['sampledFrames']} 帧，"
            "没能与其他录像比较（例如全黑或几乎不动）"
        )
    for row in cast(list[dict[str, object]], report["duplicateGroups"]):
        members = cast(list[str], row["sourceIds"])
        overlapping.update(members)
        for member in members:
            others = "、".join(item for item in members if item != member)
            notes[member].append(f"与 {others} 字节完全相同（同一文件登记两次会在冻结时被拦下）")
    for row in cast(list[dict[str, object]], report["sharedFootageCandidates"]):
        first, second = cast(str, row["sourceA"]), cast(str, row["sourceB"])
        # One wording for both members: the offset is stated for the pair (A relative to B).
        detail = (
            f"{first} 与 {second} 共用画面（{'左右镜像，' if row.get('mirrored') is True else ''}"
            f"{first} 相对 {second} 偏移 {cast(float, row['offsetSeconds']):+.1f} 秒，"
            f"{row['matchedVotes']}/{row['comparedVotes']} 票）。"
            "分到不同录制组或跨开发／测试会在冻结时被拦下"
        )
        notes[first].append(detail)
        notes[second].append(detail)
        overlapping.update((first, second))
    draft = validate_draft(
        {
            "schemaVersion": DRAFT_VERSION,
            "datasetId": "",
            "sources": [
                {
                    "id": row["sourceId"],
                    "path": row["path"],
                    "recordingGroup": None,
                    "partition": "",
                    "modelResultsViewed": None,
                }
                for row in [*sources, *failed]
            ],
            "queries": [],
        }
    )
    evidence: dict[str, object] = {
        "schemaVersion": EVIDENCE_VERSION,
        "inventorySchemaVersion": report["schemaVersion"],
        "sources": {
            identifier: {
                "durationUs": durations.get(identifier),
                "sharedOrDuplicate": identifier in overlapping,
                "notes": lines,
            }
            for identifier, lines in notes.items()
        },
    }
    return draft, evidence
