"""Human reference editing before freezing; preserve source/query declarations."""

import hashlib
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import cast

from gamingcreator.application.benchmark_preparation import (
    MAX_PLAN_BYTES,
    BenchmarkPlan,
    canonical_json,
    freeze_document,
    loads_plan,
)
from gamingcreator.application.benchmark_review import decode_object
from gamingcreator.domain.media import MediaAsset

CONTEXT_VERSION = "benchmark-reference-context-v1"
RECORD_VERSION = "benchmark-reference-record-v1"
MAX_RECORD_BYTES = MAX_PLAN_BYTES + 1024


def context_hash(context: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(context)).hexdigest()


def build_reference_context(
    plan: BenchmarkPlan, assets: Mapping[str, MediaAsset], prepared_at: str
) -> tuple[dict[str, object], dict[str, object]]:
    if set(assets) != {row.source_id for row in plan.sources}:
        raise ValueError("原片来源不完整。")
    document = deepcopy(plan.document)
    for row in cast(list[dict[str, object]], document["sources"]):
        asset = assets[cast(str, row["id"])]
        if (
            not asset.source_path.is_absolute()
            or re.fullmatch(r"[a-f0-9]{64}", asset.sha256) is None
            or asset.duration_us > 9_007_199_254_740_991
        ):
            raise ValueError("原片身份或时长不适用于浏览器标注。")
        row["path"] = str(asset.source_path)
    normalized = loads_plan(canonical_json(document).decode())
    verified = freeze_document(normalized, assets, prepared_at)
    media = [
        {
            **row,
            "automaticTimeCapture": assets[cast(str, row["id"])].origin_seconds == 0
            and all(stream.start_seconds == 0 for stream in assets[cast(str, row["id"])].streams),
        }
        for row in cast(list[dict[str, object]], verified["sources"])
    ]
    context: dict[str, object] = {
        "schemaVersion": CONTEXT_VERSION,
        "preparedAt": prepared_at,
        "plan": document,
        "media": media,
        "preparation": verified["preparation"],
        "isFrozen": False,
        "qualityGate": None,
    }
    template: dict[str, object] = {
        "schemaVersion": RECORD_VERSION,
        "contextSha256": context_hash(context),
        "plan": deepcopy(document),
    }
    return context, template


def _fixed_fields(document: dict[str, object]) -> dict[str, object]:
    fixed = deepcopy(document)
    del fixed["labelVersion"], fixed["humanReferences"]
    for row in cast(list[dict[str, object]], fixed["queries"]):
        del row["referenceEvents"]
    return fixed


def validate_reference_record(
    data: bytes, context: dict[str, object], assets: Mapping[str, MediaAsset]
) -> dict[str, object]:
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError("原片标注记录过大。")
    record = decode_object(data)
    if (
        set(record) != {"schemaVersion", "contextSha256", "plan"}
        or record["schemaVersion"] != RECORD_VERSION
        or record["contextSha256"] != context_hash(context)
    ):
        raise ValueError("标注记录不属于这份原片资料。")
    original = loads_plan(canonical_json(context["plan"]).decode())
    rebuilt, _ = build_reference_context(original, assets, cast(str, context["preparedAt"]))
    if rebuilt != context:
        raise ValueError("原片或原准备资料已经改变。")
    edited = loads_plan(canonical_json(record["plan"]).decode())
    if _fixed_fields(edited.document) != _fixed_fields(original.document):
        raise ValueError("来源、查询或独立性声明不能随标注记录改变。")
    freeze_document(edited, assets, cast(str, context["preparedAt"]))
    return record
