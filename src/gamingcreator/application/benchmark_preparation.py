"""Freeze source/query plans and bind them to benchmark v1; no inference or labels."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from gamingcreator.application.benchmark import MAX_SOURCE_US, BenchmarkManifest, parse_manifest
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.media import MediaAsset

PLAN_VERSION = "benchmark-plan-v1"
FREEZE_VERSION = "benchmark-freeze-v1"
MAX_PLAN_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class PlannedSource:
    source_id: str
    path: str
    recording_group: str | None
    partition: str
    results_viewed: bool


@dataclass(frozen=True, slots=True)
class BenchmarkPlan:
    document: dict[str, object]
    sources: tuple[PlannedSource, ...]
    manifest: BenchmarkManifest


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("计划含重复JSON字段。")
        result[key] = value
    return result


def _nonfinite(value: str) -> object:
    raise ValueError("计划不接受非有限数字。")


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("计划字段缺失或包含未知字段。")
    return cast(dict[str, object], value)


def _rows(value: object, maximum: int) -> list[object]:
    if type(value) is not list or not 1 <= len(value) <= maximum:
        raise ValueError("素材／查询清单必须非空且有界。")
    return cast(list[object], value)


def _text(value: object) -> str:
    if type(value) is not str or not value.strip() or len(value) > 16_384:
        raise ValueError("计划文字必须非空且有界。")
    return value


def _benchmark_document(
    plan: dict[str, object], media: list[dict[str, object]], queries: list[dict[str, object]]
) -> dict[str, object]:
    human = cast(dict[str, object], plan["humanReferences"])
    return {
        "schemaVersion": 1,
        "datasetId": plan["datasetId"],
        "labelVersion": plan["labelVersion"],
        "humanLabels": {
            "confirmed": False,
            "annotators": human["annotators"],
            "reviewed": human["reviewed"],
            "frozenAt": None,
            "independentTestSet": False,
        },
        "media": media,
        "queries": queries,
    }


def _queries(
    plan: dict[str, object], bindings: Mapping[str, tuple[str, str]]
) -> list[dict[str, object]]:
    rows = cast(list[dict[str, object]], plan["queries"])
    return [
        {
            "id": row["id"],
            "text": row["text"],
            "kind": row["kind"],
            "mediaId": bindings[cast(str, row["sourceId"])][0],
            "runId": bindings[cast(str, row["sourceId"])][1],
            "referenceEvents": row["referenceEvents"],
            "candidateLabels": [],
        }
        for row in rows
        if row["sourceId"] in bindings
    ]


def loads_plan(text: str) -> BenchmarkPlan:
    if len(text.encode("utf-8")) > MAX_PLAN_BYTES:
        raise ValueError("计划不能超过1MiB。")
    raw = _object(
        json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite),
        {"schemaVersion", "datasetId", "labelVersion", "humanReferences", "sources", "queries"},
    )
    if raw["schemaVersion"] != PLAN_VERSION:
        raise ValueError("未知验收计划版本。")
    human = _object(raw["humanReferences"], {"confirmed", "annotators", "reviewed"})
    if type(human["confirmed"]) is not bool:
        raise ValueError("人工参考确认必须为布尔值。")
    sources = []
    for item in _rows(raw["sources"], 200):
        row = _object(item, {"id", "path", "recordingGroup", "partition", "modelResultsViewed"})
        if (
            row["partition"] not in ("development", "test")
            or type(row["modelResultsViewed"]) is not bool
        ):
            raise ValueError("素材分区或已看结果声明无效。")
        group = None if row["recordingGroup"] is None else _text(row["recordingGroup"])
        sources.append(
            PlannedSource(
                _text(row["id"]),
                _text(row["path"]),
                group,
                row["partition"],
                row["modelResultsViewed"],
            )
        )
    if len({row.source_id for row in sources}) != len(sources):
        raise ValueError("素材ID不得重复。")
    for item in _rows(raw["queries"], 1000):
        row = _object(item, {"id", "text", "kind", "sourceId", "family", "referenceEvents"})
        _text(row["family"])
        _text(row["sourceId"])
    # Reuse benchmark's exact reference/range/type validation without claiming human confirmation.
    media = [
        {
            "mediaId": row.source_id,
            "runId": row.source_id,
            "sha256": f"{index:064x}",
            "durationUs": MAX_SOURCE_US,
        }
        for index, row in enumerate(sources, 1)
    ]
    bindings = {row.source_id: (row.source_id, row.source_id) for row in sources}
    queries = _queries(raw, bindings)
    if len(queries) != len(cast(list[object], raw["queries"])):
        raise ValueError("查询引用未登记素材。")
    manifest = parse_manifest(_benchmark_document(raw, media, queries))
    if human["confirmed"] and (
        not manifest.human_labels.annotators or manifest.label_version is None
    ):
        raise ValueError("已确认人工参考需要填写人和标签版本。")
    return BenchmarkPlan(raw, tuple(sources), manifest)


def preparation_status(plan: BenchmarkPlan, sources: list[dict[str, object]]) -> dict[str, object]:
    blockers: set[str] = set()
    index = {row.source_id: row for row in plan.sources}
    groups: dict[str, set[str]] = {}
    content: dict[str, set[str]] = {}
    content_groups: dict[str, set[str]] = {}
    for row in sources:
        source = index[cast(str, row["id"])]
        if source.recording_group is None:
            blockers.add("recording_group_missing")
        else:
            groups.setdefault(source.recording_group, set()).add(source.partition)
            content_groups.setdefault(cast(str, row["sha256"]), set()).add(source.recording_group)
        content.setdefault(cast(str, row["sha256"]), set()).add(source.partition)
        if source.partition == "test" and source.results_viewed:
            blockers.add("test_results_already_viewed")
    if any(len(value) > 1 for value in groups.values()):
        blockers.add("recording_group_crosses_partitions")
    if any(len(value) > 1 for value in content.values()):
        blockers.add("same_content_crosses_partitions")
    if any(len(value) > 1 for value in content_groups.values()):
        blockers.add("same_content_has_different_recording_groups")
    if min(len(groups), len(content)) < 10:
        blockers.add("representative_recordings_below_ten")
    families: dict[str, set[str]] = {}
    queried = set()
    test_main = False
    for raw, query in zip(
        cast(list[dict[str, object]], plan.document["queries"]), plan.manifest.queries, strict=True
    ):
        source = index[cast(str, raw["sourceId"])]
        queried.add(source.source_id)
        families.setdefault(cast(str, raw["family"]), set()).add(source.partition)
        if source.partition == "test":
            test_main |= query.kind == "main"
            count = len(query.reference_events)
            if (query.kind == "main" and count < 10) or (
                query.kind == "sparse" and not 1 <= count <= 9
            ):
                blockers.add("test_reference_events_incomplete")
    if any(len(value) > 1 for value in families.values()):
        blockers.add("query_family_crosses_partitions")
    if not test_main:
        blockers.add("test_main_query_missing")
    if any(row.partition == "test" and row.source_id not in queried for row in plan.sources):
        blockers.add("test_source_has_no_query")
    if not cast(dict[str, object], plan.document["humanReferences"])["confirmed"]:
        blockers.add("human_references_unconfirmed")
    return {
        "readyForIndependentEvaluation": not blockers,
        "blockers": sorted(blockers),
        "sourceCount": len(sources),
        "uniqueContentCount": len(content),
        "knownRecordingGroupCount": len(groups),
        "targetRecordingCount": {"minimum": 10, "recommendedMaximum": 20},
        "humanDeclarationsAuthenticated": False,
        "qualityGate": None,
    }


def freeze_document(
    plan: BenchmarkPlan, assets: Mapping[str, MediaAsset], frozen_at: str
) -> dict[str, object]:
    timestamp = datetime.fromisoformat(frozen_at)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("冻结时间须带时区。")
    if set(assets) != {row.source_id for row in plan.sources}:
        raise ValueError("冻结素材身份不完整。")
    sources = [
        {
            "id": row.source_id,
            "path": str(assets[row.source_id].source_path),
            "sha256": assets[row.source_id].sha256,
            "durationUs": assets[row.source_id].duration_us,
            "probeVersion": assets[row.source_id].probe_version,
        }
        for row in plan.sources
    ]
    # Validate references against the actual durations, including drafts.
    media = [
        {
            "mediaId": row["id"],
            "runId": row["id"],
            "sha256": f"{index:064x}",
            "durationUs": row["durationUs"],
        }
        for index, row in enumerate(sources, 1)
    ]
    parse_manifest(
        _benchmark_document(
            plan.document,
            media,
            _queries(
                plan.document,
                {row.source_id: (row.source_id, row.source_id) for row in plan.sources},
            ),
        )
    )
    return {
        "schemaVersion": FREEZE_VERSION,
        "frozenAt": frozen_at,
        "plan": plan.document,
        "sources": sources,
        "preparation": preparation_status(plan, sources),
    }


def bind_manifest(
    frozen: dict[str, object], timelines: Mapping[str, StoredTimeline], partition: str
) -> dict[str, object]:
    plan = loads_plan(canonical_json(frozen["plan"]).decode("utf-8"))
    sources = cast(list[dict[str, object]], frozen["sources"])
    status = preparation_status(plan, sources)
    selected = {row.source_id for row in plan.sources if row.partition == partition}
    wanted = {
        row["sourceId"]
        for row in cast(list[dict[str, object]], plan.document["queries"])
        if row["sourceId"] in selected
    }
    if partition not in ("development", "test") or not wanted or set(timelines) != wanted:
        raise ValueError("运行映射必须完整且仅包含所选分区被查询的素材。")
    index = {cast(str, row["id"]): row for row in sources}
    for source_id, timeline in timelines.items():
        source, asset = index[source_id], timeline.run.asset
        if timeline.run.status != "completed" or (source["sha256"], source["durationUs"]) != (
            asset.sha256,
            asset.duration_us,
        ):
            raise ValueError("已完成运行与冻结原录像身份不符。")
    bindings = {
        key: (value.run.asset.media_id, value.run.run_id) for key, value in timelines.items()
    }
    media = [
        {
            "mediaId": value.run.asset.media_id,
            "runId": value.run.run_id,
            "sha256": value.run.asset.sha256,
            "durationUs": value.run.asset.duration_us,
        }
        for value in timelines.values()
    ]
    document = _benchmark_document(plan.document, media, _queries(plan.document, bindings))
    human = cast(dict[str, object], document["humanLabels"])
    references_complete = all(
        query.kind == "negative"
        or (query.kind == "main" and len(query.reference_events) >= 10)
        or (query.kind == "sparse" and 1 <= len(query.reference_events) <= 9)
        for query in plan.manifest.queries
        if query.media_id in wanted
    )
    human["confirmed"] = bool(
        cast(dict[str, object], plan.document["humanReferences"])["confirmed"]
        and references_complete
    )
    human["frozenAt"] = frozen["frozenAt"]
    human["independentTestSet"] = (
        partition == "test" and status["readyForIndependentEvaluation"] is True
    )
    parse_manifest(document)
    return document
