"""Explicit AND conditions across complete recordings, using only exact saved details."""

import hashlib
import json
from collections.abc import Callable, Sequence
from typing import cast

from gamingcreator.application.observation_text import display_facts
from gamingcreator.application.storage import StoredTimeline, TimelineStore
from gamingcreator.domain.actor_details import QueryConstraint, canonical_constraint_json
from gamingcreator.domain.errors import AppError, ExitCode

VERSION = "project-detail-query-v1"
STATUSES = ("full", "partial", "no_match", "unverified")
MAX_EVENTS = 20_000
SavedMatcher = Callable[[StoredTimeline, str, QueryConstraint], dict[str, object]]


async def match_project_details(
    store: TimelineStore,
    run_ids: Sequence[str],
    constraint: QueryConstraint,
    profile: str,
    matcher: SavedMatcher,
    *,
    limit: int = 20,
    offset: int = 0,
    status: str = "all",
    expected_snapshot: str | None = None,
) -> dict[str, object]:
    """Scan all events before filtering/paging; no coarse retrieval cutoff or rank changes."""
    if (
        not 1 <= len(run_ids) <= 100
        or any(
            type(identifier) is not str or not identifier.strip() or len(identifier) > 256
            for identifier in run_ids
        )
        or len(set(run_ids)) != len(run_ids)
        or profile not in {"v1", "v2", "v3", "v4"}
        or type(limit) is not int
        or not 1 <= limit <= 50
        or type(offset) is not int
        or not 0 <= offset <= MAX_EVENTS
        or status not in (*STATUSES, "all")
        or (
            expected_snapshot is not None
            and (
                type(expected_snapshot) is not str
                or len(expected_snapshot) != 64
                or any(char not in "0123456789abcdef" for char in expected_snapshot)
            )
        )
    ):
        raise AppError(
            "input.project_detail_query",
            "请选择不同录像、明确条件版本和有效分页参数。",
            ExitCode.INPUT,
        )
    timelines = [await store.load_completed_timeline(identifier) for identifier in sorted(run_ids)]
    if len({row.run.asset.sha256 for row in timelines}) != len(timelines) or len(
        {row.run.asset.media_id for row in timelines}
    ) != len(timelines):
        raise AppError("retrieval.scope", "同一原录像请只选择一个分析版本。", ExitCode.INPUT)
    total = sum(len(row.events) for row in timelines)
    if total > MAX_EVENTS:
        raise AppError(
            "input.project_detail_query",
            "所选素材超过20,000个事件，请缩小范围；没有截断核对。",
            ExitCode.INPUT,
        )
    sources = [
        {
            "runId": row.run.run_id,
            "mediaId": row.run.asset.media_id,
            "sourceName": row.run.asset.source_path.name,
            "sourceSha256": row.run.asset.sha256,
            "configHash": row.run.config_hash,
            "pipelineVersion": row.run.configuration.pipeline_version,
            "durationUs": row.run.asset.duration_us,
            "eventCount": len(row.events),
        }
        for row in timelines
    ]
    constraint_json = canonical_constraint_json(constraint)
    scope = json.dumps(
        {"sources": sources, "constraint": constraint_json, "profile": profile, "version": VERSION},
        ensure_ascii=False,
        sort_keys=True,
    )
    scope_id = hashlib.sha256(scope.encode()).hexdigest()
    snapshot = hashlib.sha256(scope.encode())
    counts = dict.fromkeys(STATUSES, 0)
    rows: list[dict[str, object]] = []
    selected = 0
    for timeline in timelines:
        for event in sorted(
            timeline.events,
            key=lambda row: (row.source_range.start_us, row.source_range.end_us, row.event_id),
        ):
            report = matcher(timeline, event.event_id, constraint)
            result = cast(dict[str, object], report["result"])
            verdict = cast(str, result["status"])
            if (
                report["runId"] != timeline.run.run_id
                or report["eventId"] != event.event_id
                or report["constraintJson"] != constraint_json
                or report["refinementProfile"] != profile
                or verdict not in counts
            ):
                raise AppError(
                    "refinement.source_mismatch",
                    "核对结果与所选素材、条件或版本不一致。",
                    ExitCode.STORAGE,
                )
            snapshot.update(
                json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
            )
            counts[verdict] += 1
            if status != "all" and verdict != status:
                continue
            if offset <= selected < offset + limit:
                rows.append(
                    {
                        "position": selected + 1,
                        "runId": timeline.run.run_id,
                        "mediaId": timeline.run.asset.media_id,
                        "sourceName": timeline.run.asset.source_path.name,
                        "sourceSha256": timeline.run.asset.sha256,
                        "eventId": event.event_id,
                        "startUs": event.source_range.start_us,
                        "endUs": event.source_range.end_us,
                        "evidenceIds": list(event.evidence_ids),
                        "displayFacts": list(display_facts(event.observable_facts)),
                        "match": report,
                    }
                )
            selected += 1
    snapshot_id = snapshot.hexdigest()
    if expected_snapshot is not None and expected_snapshot != snapshot_id:
        raise AppError(
            "input.project_detail_snapshot",
            "已保存的精分析结果发生变化，请重新核对，不沿用旧分页。",
            ExitCode.INPUT,
        )
    document: dict[str, object] = {
        "schemaVersion": VERSION,
        "scopeId": scope_id,
        "snapshotId": snapshot_id,
        "constraintJson": constraint_json,
        "refinementProfile": profile,
        "order": "source-run-time",
        "sources": sources,
        "totalEvents": total,
        "counts": counts,
        "status": status,
        "offset": offset,
        "limit": limit,
        "totalSelected": selected,
        "hasNext": offset + len(rows) < selected,
        "results": rows,
        "humanLabels": None,
        "qualityGate": None,
        "ordinarySearches": 0,
        "modelAnalysisCalls": 0,
        "paidRequestsSent": 0,
        "newReservations": 0,
    }
    if len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode()) > 8_388_608:
        raise AppError(
            "refinement.too_large",
            "本页结果超过8MiB，请缩小每页条数，原结果没有改动。",
            ExitCode.STORAGE,
        )
    return document
