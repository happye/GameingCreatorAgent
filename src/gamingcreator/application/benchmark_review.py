"""Bind manual candidate judgments to ten persisted positions; no I/O or scoring."""

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from typing import cast

from gamingcreator.application.benchmark import parse_manifest
from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.application.storage import StoredTimeline

REVIEW_VERSION = "benchmark-candidate-review-v1"
MAX_REVIEW_BYTES = 4_194_304
EDITABLE = {"grade", "humanEventId", "reason"}


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("验收资料必须是JSON对象。")
    return cast(dict[str, object], value)


def _rows(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise ValueError("验收条目必须为数组。")
    return [_object(item) for item in value]


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("验收记录含重复JSON字段。")
        result[key] = value
    return result


def _nonfinite(value: str) -> object:
    raise ValueError("验收记录不接受非有限数字。")


def decode_object(data: bytes) -> dict[str, object]:
    if len(data) > MAX_REVIEW_BYTES:
        raise ValueError("验收记录不能超过4MiB。")
    return _object(
        json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    )


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _text(value: object, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError("填写人／理由必须是有界非空文字。")
    return value


def build_review_context(
    manifest_document: dict[str, object],
    report: dict[str, object],
    *,
    report_sha256: str,
    binding_sha256: str,
    timelines: Mapping[str, StoredTimeline],
    retrievals: Mapping[str, dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    manifest = parse_manifest(manifest_document)
    if (
        type(report.get("schemaVersion")) is not int
        or report["schemaVersion"] != 1
        or report.get("mediaVerified") is not True
        or report.get("mediaFailures") != []
    ):
        raise ValueError("报告缺已验证来源，不能准备判分。")
    identity = {
        **manifest_document,
        **{key: report[key] for key in ("datasetId", "labelVersion", "humanLabels", "media")},
    }
    parse_manifest(identity)
    identity["humanLabels"] = {
        **_object(identity["humanLabels"]),
        "reviewed": _object(manifest_document["humanLabels"])["reviewed"],
    }
    if identity != manifest_document:
        raise ValueError("报告与冻结的素材／人工参考声明不同。")
    metadata = _object(report["runnerMetadata"])
    provenance = _rows(metadata["runs"])
    if len(provenance) != len(manifest.media) or len({row["runId"] for row in provenance}) != len(
        provenance
    ):
        raise ValueError("报告运行来源不完整。")
    expected_runs = []
    for source in manifest.media:
        timeline = timelines[source.run_id]
        asset, run = timeline.run.asset, timeline.run
        if run.status != "completed" or (asset.media_id, asset.sha256, asset.duration_us) != (
            source.media_id,
            source.sha256,
            source.duration_us,
        ):
            raise ValueError("已保存来源与冻结身份不同。")
        expected_runs.append(
            {
                "runId": run.run_id,
                "pipelineVersion": run.configuration.pipeline_version,
                "configHash": run.config_hash,
            }
        )
    if sorted(provenance, key=lambda row: str(row["runId"])) != sorted(
        expected_runs, key=lambda row: str(row["runId"])
    ):
        raise ValueError("报告原模型配置已改变。")
    raw_queries = _rows(report["queries"])
    if len(raw_queries) != len(manifest.queries):
        raise ValueError("报告查询不完整。")
    queries, record_queries = [], []
    for query, row in zip(manifest.queries, raw_queries, strict=True):
        if (row["queryId"], row["text"], row["kind"], row["mediaId"], row["runId"]) != (
            query.query_id,
            query.text,
            query.kind,
            query.media_id,
            query.run_id,
        ):
            raise ValueError("报告查询或顺序与冻结不同。")
        status, retrieval_id = row["status"], row.get("retrievalId")
        if status not in ("scored", "unverified_labels", "failed"):
            raise ValueError("未知报告查询状态。")
        slots = _rows(row["slots"])
        if len(slots) != 10 or any(
            type(slot.get("slot")) is not int or slot["slot"] != i
            for i, slot in enumerate(slots, 1)
        ):
            raise ValueError("报告必须保持十个固定位置。")
        hits, documents = [], []
        if status != "failed":
            if type(retrieval_id) is not str or retrieval_id not in retrievals:
                raise ValueError("报告缺实际保存的检索身份，请显式生成新报告。")
            retrieval = retrievals[retrieval_id]
            if (
                retrieval["runId"],
                retrieval["mediaId"],
                retrieval["query"],
                retrieval["retrievalVersion"],
            ) != (query.run_id, query.media_id, query.text, metadata["retrievalVersion"]):
                raise ValueError("报告与保存检索身份不同。")
            parameters = _object(retrieval["parameters"])
            if parameters["mode"] != metadata["retrievalMode"] or parameters["topK"] != 10:
                raise ValueError("原检索参数不同。")
            hits = _rows(retrieval["hits"])
            result = _object(retrieval["result"])
            documents = _rows(result["candidates"])
            if (
                len(hits) != len(documents)
                or type(row["totalReturned"]) is not int
                or type(row["returnedTop10"]) is not int
                or row["totalReturned"] != len(hits)
                or row["returnedTop10"] != min(10, len(hits))
            ):
                raise ValueError("报告返回数量与保存排名不同。")
        elif any(slot.get("status") != "missing" for slot in slots):
            raise ValueError("失败查询不能伪装为可判分候选。")
        source_slots, seen = [], set()
        for position, slot in enumerate(slots, 1):
            if position > len(hits):
                if slot.get("status") != "missing":
                    raise ValueError("报告缺位不能补成候选。")
                saved = {
                    "slot": position,
                    "state": "missing",
                    "reportedRank": None,
                    "candidateId": None,
                    "eventId": None,
                    "startUs": None,
                    "endUs": None,
                    "facts": [],
                    "evidenceIds": [],
                }
            else:
                hit, document = hits[position - 1], documents[position - 1]
                identifier = hit["event_id"] or hit["candidate_id"]
                start, end = hit["start_us"], hit["end_us"]
                if (
                    any(type(value) is not int for value in (start, end, hit["rank"]))
                    or not 0
                    <= cast(int, start)
                    < cast(int, end)
                    <= timelines[query.run_id].run.asset.duration_us
                ):
                    raise ValueError("保存候选区间无效。")
                if _sha(
                    [slot["eventId"], slot["startUs"], slot["endUs"], slot["reportedRank"]]
                ) != _sha([identifier, start, end, hit["rank"]]) or _sha(
                    [
                        document["candidateId"],
                        document["eventId"],
                        document["startUs"],
                        document["endUs"],
                        document["rank"],
                        document["mediaId"],
                    ]
                ) != _sha(
                    [hit["candidate_id"], hit["event_id"], start, end, hit["rank"], query.media_id]
                ):
                    raise ValueError("报告候选顺序或区间已改变。")
                if set(cast(list[str], document["evidenceIds"])) != set(
                    cast(list[str], hit["evidence_ids"])
                ):
                    raise ValueError("保存的候选证据不同。")
                saved = {
                    "slot": position,
                    "state": "known_duplicate" if identifier in seen else "candidate",
                    "reportedRank": hit["rank"],
                    "candidateId": hit["candidate_id"],
                    "eventId": identifier,
                    "startUs": start,
                    "endUs": end,
                    "facts": document.get("displayFacts", document["observableFacts"]),
                    "evidenceIds": document["evidenceIds"],
                }
                seen.add(identifier)
            source_slots.append(saved)
        references = next(
            item["referenceEvents"]
            for item in _rows(manifest_document["queries"])
            if item["id"] == query.query_id
        )
        queries.append(
            {
                "queryId": query.query_id,
                "text": query.text,
                "kind": query.kind,
                "runId": query.run_id,
                "mediaId": query.media_id,
                "status": status,
                "retrievalId": retrieval_id,
                "references": references,
                "slots": source_slots,
            }
        )
        record_queries.append(
            {
                "queryId": query.query_id,
                "slots": [
                    {
                        **{
                            key: value
                            for key, value in slot.items()
                            if key not in ("facts", "evidenceIds")
                        },
                        "grade": None,
                        "humanEventId": None,
                        "reason": None,
                    }
                    for slot in source_slots
                ],
            }
        )
    basis = {
        "manifest": manifest_document,
        "queries": queries,
        "reportSha256": report_sha256,
        "bindingSha256": binding_sha256,
        "runs": expected_runs,
    }
    template: dict[str, object] = {
        "schemaVersion": REVIEW_VERSION,
        "basisSha256": _sha(basis),
        "reportSha256": report_sha256,
        "bindingSha256": binding_sha256,
        "recordedOn": None,
        "reviewer": None,
        "reviewed": False,
        "queries": record_queries,
    }
    context: dict[str, object] = {
        **basis,
        "template": template,
        "media": [
            {
                "runId": key,
                "name": value.run.asset.source_path.name,
                "path": str(value.run.asset.source_path),
                "durationUs": value.run.asset.duration_us,
                "originSeconds": str(value.run.asset.origin_seconds),
                "automaticPlaybackSupported": value.run.asset.origin_seconds == 0,
            }
            for key, value in timelines.items()
        ],
        "qualityGate": None,
    }
    return context, template


def validate_review(
    data: bytes, template: dict[str, object], context: dict[str, object]
) -> dict[str, object]:
    record = decode_object(data)
    root_editable = {"recordedOn", "reviewer", "reviewed", "queries"}
    if set(record) != set(template) or {
        key: value for key, value in record.items() if key not in root_editable
    } != {key: value for key, value in template.items() if key not in root_editable}:
        raise ValueError("人工记录来源不同。")
    if type(record["reviewed"]) is not bool:
        raise ValueError("复核状态必须为布尔值。")
    has_metadata = record["recordedOn"] is not None
    if has_metadata != (record["reviewer"] is not None):
        raise ValueError("日期和填写人须同时填写或同时留空。")
    if has_metadata:
        recorded = _text(record["recordedOn"], 10)
        if date.fromisoformat(recorded).isoformat() != recorded:
            raise ValueError("日期须为存在的YYYY-MM-DD。")
        _text(record["reviewer"], 120)
    rows, expected = _rows(record["queries"]), _rows(template["queries"])
    if len(rows) != len(expected):
        raise ValueError("须保留全部冻结查询。")
    for row, original, query in zip(rows, expected, _rows(context["queries"]), strict=True):
        if set(row) != {"queryId", "slots"} or row["queryId"] != original["queryId"]:
            raise ValueError("查询身份或顺序不同。")
        slots, originals = _rows(row["slots"]), _rows(original["slots"])
        if len(slots) != 10:
            raise ValueError("须保留十个固定位置。")
        reference_ids = {item["humanEventId"] for item in _rows(query["references"])}
        for slot, source in zip(slots, originals, strict=True):
            if set(slot) != set(source) or _sha(
                {key: value for key, value in slot.items() if key not in EDITABLE}
            ) != _sha({key: value for key, value in source.items() if key not in EDITABLE}):
                raise ValueError("候选身份／区间／位置不同。")
            grade, human_id, reason = slot["grade"], slot["humanEventId"], slot["reason"]
            if source["state"] != "candidate" and any(
                value is not None for value in (grade, human_id, reason)
            ):
                raise ValueError("缺位／已知重复不能判分或补位。")
            if grade is not None and (type(grade) is not int or not 0 <= grade <= 3):
                raise ValueError("评分须为整数0–3或未判定。")
            if human_id is not None and (
                type(human_id) is not str or human_id not in reference_ids
            ):
                raise ValueError("独立事件须属于该查询的冻结参考。")
            if grade is None and human_id is not None:
                raise ValueError("未判分不能指定独立事件。")
            if reason is not None:
                _text(reason, 4096)
            if grade is not None and (reason is None or (grade >= 2 and human_id is None)):
                raise ValueError("评分需要理由，可用评分需要独立事件。")
            if (grade is not None or reason is not None or record["reviewed"]) and not has_metadata:
                raise ValueError("记录判断前请填写日期和填写人。")
    return record


def judged_manifest(context: dict[str, object], record: dict[str, object]) -> dict[str, object]:
    record = validate_review(canonical_json(record), _object(context["template"]), context)
    document = decode_object(canonical_json(context["manifest"]))
    for query, row in zip(_rows(document["queries"]), _rows(record["queries"]), strict=True):
        query["candidateLabels"] = [
            {
                "eventId": slot["eventId"],
                "humanEventId": slot["humanEventId"],
                "startUs": slot["startUs"],
                "endUs": slot["endUs"],
                "grade": slot["grade"],
                "reason": slot["reason"],
            }
            for slot in _rows(row["slots"])
            if slot["grade"] is not None
        ]
    _object(document["humanLabels"])["reviewed"] = record["reviewed"]
    parse_manifest(document)
    return document
