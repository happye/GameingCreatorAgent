"""Incomplete pre-inference registration drafts; no source I/O or human labels."""

from copy import deepcopy
from pathlib import PureWindowsPath
from typing import cast

from gamingcreator.application.benchmark_preparation import (
    MAX_PLAN_BYTES,
    BenchmarkPlan,
    canonical_json,
    loads_plan,
)
from gamingcreator.application.benchmark_review import decode_object

DRAFT_VERSION = "benchmark-plan-draft-v1"


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
