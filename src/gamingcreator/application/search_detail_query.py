"""Read-only detail evidence attached to an exact saved ranking, without reranking."""

import hashlib
import json
import math
import re
from typing import cast

from gamingcreator.application.project_detail_query import STATUSES, SavedMatcher
from gamingcreator.application.retrieval import candidate_sources
from gamingcreator.application.storage import TimelineStore
from gamingcreator.domain.actor_details import QueryConstraint, canonical_constraint_json
from gamingcreator.domain.errors import AppError, ExitCode

VERSION = "search-detail-query-v1"
MAX_BYTES = 8 * 1024 * 1024


def search_snapshot_sha256(document: dict[str, object]) -> str:
    """Hash the original search content, excluding response-only UI metadata."""
    try:
        data = json.dumps(document, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
        if len(data) > MAX_BYTES:
            raise ValueError("Oversized search snapshot.")
        return hashlib.sha256(data).hexdigest()
    except (ValueError, TypeError):
        raise AppError(
            "retrieval.search_snapshot", "保存的搜索资料无效。", ExitCode.STORAGE
        ) from None


def search_run_ids(document: dict[str, object]) -> tuple[str, ...]:
    try:
        sources = document["sources"]
        candidates = document["candidates"]
        if (
            document["schemaVersion"] != "project-search-v1"
            or type(document["searchId"]) is not str
            or not re.fullmatch(r"[a-f0-9]{32}", document["searchId"])
            or type(document["scopeId"]) is not str
            or not re.fullmatch(r"project-[a-f0-9]{32}", document["scopeId"])
            or type(sources) is not list
            or not 1 <= len(sources) <= 100
            or type(candidates) is not list
            or type(document["topK"]) is not int
            or not 1 <= document["topK"] <= 100
            or len(candidates) > document["topK"]
        ):
            raise ValueError("Invalid saved search identity.")
        ids = tuple(row["runId"] for row in sources if type(row) is dict)
        if (
            len(ids) != len(sources)
            or any(
                type(identifier) is not str or not identifier.strip() or len(identifier) > 256
                for identifier in ids
            )
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Invalid saved source identities.")
        return ids
    except (KeyError, TypeError, ValueError):
        raise AppError(
            "retrieval.search_snapshot", "保存的搜索身份或范围无效。", ExitCode.STORAGE
        ) from None


async def match_search_details(
    store: TimelineStore,
    document: dict[str, object],
    expected_search_sha256: str,
    constraint: QueryConstraint,
    profile: str,
    matcher: SavedMatcher,
) -> dict[str, object]:
    if (
        profile not in {"v1", "v2", "v3", "v4"}
        or type(expected_search_sha256) is not str
        or not re.fullmatch(r"[a-f0-9]{64}", expected_search_sha256)
    ):
        raise AppError(
            "input.search_detail_query", "请选择明确的条件版本与原搜索摘要。", ExitCode.INPUT
        )
    digest = search_snapshot_sha256(document)
    if digest != expected_search_sha256:
        raise AppError(
            "retrieval.search_snapshot",
            "保存排名已变化，请重新读取，不沿用旧候选。",
            ExitCode.STORAGE,
        )
    ids = search_run_ids(document)
    timelines = {identifier: await store.load_completed_timeline(identifier) for identifier in ids}
    sources = cast(list[dict[str, object]], document["sources"])
    if len({row.run.asset.sha256 for row in timelines.values()}) != len(ids) or len(
        {row.run.asset.media_id for row in timelines.values()}
    ) != len(ids):
        raise AppError("retrieval.scope", "同一原录像不能作为不同搜索来源。", ExitCode.INPUT)
    candidates = cast(list[dict[str, object]], document["candidates"])
    try:
        for source in sources:
            run = timelines[cast(str, source["runId"])].run
            if (
                source["mediaId"] != run.asset.media_id
                or source["sourceSha256"] != run.asset.sha256
                or source["configHash"] != run.config_hash
                or source["pipelineHash"] != run.configuration.pipeline_hash
                or source["pipelineVersion"] != run.configuration.pipeline_version
                or type(source["durationUs"]) is not int
                or source["durationUs"] != run.asset.duration_us
                or source["sourceName"] != run.asset.source_path.name
            ):
                raise ValueError("Saved source changed.")
        origin = {
            (identifier, item.candidate_id): item
            for identifier, timeline in timelines.items()
            for item in candidate_sources(timeline)
        }
        seen = set()
        for position, row in enumerate(candidates, 1):
            if type(row) is not dict:
                raise ValueError("Invalid candidate.")
            if any(type(row[field]) is not str for field in ("runId", "candidateId")):
                raise ValueError("Invalid candidate source identity.")
            key = (cast(str, row["runId"]), cast(str, row["candidateId"]))
            actual = origin[key]
            run = timelines[cast(str, row["runId"])].run
            if (
                key in seen
                or type(row["rank"]) is not int
                or row["rank"] != position
                or row["eventId"] != actual.event_id
                or row["mediaId"] != actual.media_id
                or row["sourceSha256"] != run.asset.sha256
                or row["sourceName"] != run.asset.source_path.name
                or type(row["startUs"]) is not int
                or type(row["endUs"]) is not int
                or row["startUs"] != actual.source_range.start_us
                or row["endUs"] != actual.source_range.end_us
                or row["evidenceIds"] != list(actual.evidence_ids)
                or row["observableFacts"] != list(actual.observable_facts)
                or type(row["score"]) not in (int, float)
                or not math.isfinite(cast(float, row["score"]))
                or type(row["scoreKind"]) is not str
            ):
                raise ValueError("Saved candidate no longer belongs to this source.")
            seen.add(key)
    except (KeyError, TypeError, ValueError):
        raise AppError(
            "retrieval.search_source", "保存候选与实际素材、排名或证据不一致。", ExitCode.STORAGE
        ) from None
    query_json = canonical_constraint_json(constraint)
    matches: list[dict[str, object]] = []
    counts = dict.fromkeys(STATUSES, 0)
    for row in candidates:
        event_id = cast(str | None, row["eventId"])
        report = None
        status = "unverified"
        if event_id is not None:
            report = matcher(timelines[cast(str, row["runId"])], event_id, constraint)
            status = cast(str, cast(dict[str, object], report["result"])["status"])
            if (
                report["runId"] != row["runId"]
                or report["eventId"] != event_id
                or report["constraintJson"] != query_json
                or report["refinementProfile"] != profile
                or status not in counts
            ):
                raise AppError(
                    "refinement.source_mismatch", "条件结果与原候选身份不一致。", ExitCode.STORAGE
                )
        counts[status] += 1
        matches.append(
            {
                "rank": row["rank"],
                "runId": row["runId"],
                "candidateId": row["candidateId"],
                "eventId": event_id,
                "status": status,
                "availability": "visual_event" if event_id is not None else "transcript_only",
                "match": report,
            }
        )
    response: dict[str, object] = {
        "schemaVersion": VERSION,
        "searchSha256": digest,
        "search": document,
        "constraintJson": query_json,
        "refinementProfile": profile,
        "matches": matches,
        "counts": counts,
        "humanLabels": None,
        "qualityGate": None,
        "ordinarySearches": 0,
        "modelAnalysisCalls": 0,
        "paidRequestsSent": 0,
        "newReservations": 0,
    }
    response["snapshotId"] = hashlib.sha256(
        json.dumps(response, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    if len(json.dumps(response, ensure_ascii=False, allow_nan=False).encode()) > MAX_BYTES:
        raise AppError(
            "refinement.too_large", "本次候选依据超过8MiB，请缩小候选范围。", ExitCode.STORAGE
        )
    return response
