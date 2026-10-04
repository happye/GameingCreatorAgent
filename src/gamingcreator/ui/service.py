"""One read of a project run: source-time events plus an optional shipped search."""

import mimetypes
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from gamingcreator.application.inspection import InspectionView, inspection_view
from gamingcreator.application.retrieval import RETRIEVAL_VERSION, CandidateClip, RetrievalMode
from gamingcreator.application.storage import RunStatus, StoredInvocation
from gamingcreator.cli.main import execute_search
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.media import MediaResource


def _timecode(microseconds: int) -> str:
    milliseconds = microseconds // 1000
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def view_payload(view: InspectionView) -> dict[str, object]:
    return {
        "artifact": view.artifact,
        "runId": view.run_id,
        "runStatus": view.run_status,
        "timeline": [
            {
                "eventId": row.event_id,
                "startUs": row.start_us,
                "endUs": row.end_us,
                "startTimecode": _timecode(row.start_us),
                "endTimecode": _timecode(row.end_us),
                "observableFacts": list(row.facts),
                "evidenceIds": list(row.evidence_ids),
            }
            for row in view.timeline
        ],
        "candidates": [
            {
                "rank": row.rank,
                "eventId": row.event_id,
                "candidateId": row.candidate_id,
                "startUs": row.start_us,
                "endUs": row.end_us,
                "startTimecode": _timecode(row.start_us),
                "endTimecode": _timecode(row.end_us),
                "observableFacts": list(row.facts),
                "evidenceIds": list(row.evidence_ids),
                "score": row.score,
                "scoreKind": row.score_kind,
            }
            for row in view.candidates
        ],
        "abstentionReason": view.abstention_reason,
        "ordering": {
            "timeline": "source-start-time",
            "candidates": "score-then-start-time-then-id",
        },
    }


def _int(value: object) -> int:
    if type(value) is not int:
        raise AppError("retrieval.timeline_invalid", "检索候选字段无效。", ExitCode.STORAGE)
    return value


def _float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AppError("retrieval.timeline_invalid", "检索候选字段无效。", ExitCode.STORAGE)
    return float(value)


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AppError("retrieval.timeline_invalid", "检索候选字段无效。", ExitCode.STORAGE)
    return tuple(str(item) for item in value)


def _candidates(document: dict[str, object], duration_us: int) -> tuple[CandidateClip, ...]:
    raw = document["candidates"]
    if not isinstance(raw, list):
        raise AppError("retrieval.timeline_invalid", "检索候选字段无效。", ExitCode.STORAGE)
    clips = []
    for item in raw:
        if not isinstance(item, dict):
            raise AppError("retrieval.timeline_invalid", "检索候选字段无效。", ExitCode.STORAGE)
        event_id = item["eventId"]
        clips.append(
            CandidateClip(
                str(item["candidateId"]),
                None if event_id is None else str(event_id),
                str(item["mediaId"]),
                SourceRange(_int(item["startUs"]), _int(item["endUs"]), duration_us),
                _float(item["score"]),
                str(item["scoreKind"]),
                _text_tuple(item["evidenceIds"]),
                _text_tuple(item["observableFacts"]),
                str(item["why"]),
            )
        )
    return tuple(clips)


async def list_project_runs(project: Path) -> tuple[tuple[str, str], ...]:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        return await store.list_runs()
    finally:
        await store.close()


async def project_runs_payload(project: Path) -> dict[str, object]:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        rows: list[dict[str, object]] = []
        for run_id, status in await store.list_runs():
            run = await store.load_run(run_id)
            rows.append(
                {
                    "id": run_id,
                    "status": status,
                    "sourceName": run.asset.source_path.name,
                    "durationUs": run.asset.duration_us,
                    "errorCode": run.error_code,
                }
            )
        return {"runs": rows}
    finally:
        await store.close()


async def registered_media(
    project: Path, run_id: str, evidence_id: str | None = None
) -> MediaResource:
    """Resolve database identities, never a client file path."""
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        if evidence_id is None:
            run = await store.load_run(run_id)
            path, digest = run.asset.source_path, run.asset.sha256
        else:
            evidence = await store.load_evidence_reference(run_id, evidence_id)
            if evidence is None:
                raise AppError("input.evidence", "这个运行没有该证据。", ExitCode.INPUT, run_id)
            path, digest = evidence.artifact_path, evidence.sha256
            if not path.resolve().is_relative_to(project.resolve()):
                raise AppError("storage.integrity", "证据路径校验失败。", ExitCode.STORAGE)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not mime.startswith(("video/", "image/", "audio/")):
            mime = "application/octet-stream"
        return MediaResource(path, digest, mime)
    finally:
        await store.close()


def cost_payload(invocations: tuple[StoredInvocation, ...]) -> dict[str, object]:
    known, unknown = Decimal(0), 0
    for invocation in invocations:
        metadata, usage = invocation.metadata, invocation.metadata.usage
        if (
            usage.cost_cny is None
            or usage.cost_status.value == "unverified"
            or metadata.provider == "deepseek"
            and not metadata.price_version
        ):
            unknown += 1
        else:
            known += usage.cost_cny
    return {
        "knownCny": str(known),
        "unknownAttempts": unknown,
        "status": "unverified" if unknown else "estimated",
    }


async def inspect_run(
    project: Path,
    run_id: str,
    query: str,
    repository: Path,
    *,
    mode: RetrievalMode = "hybrid",
    top_k: int = 10,
) -> dict[str, object]:
    """Read events from SQLite, then search only when that run is already completed."""
    artifact = str((project / "timeline.sqlite3").resolve())
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timeline = await store.load_timeline(run_id, require_completed=False)
    finally:
        await store.close()
    candidates: tuple[CandidateClip, ...] = ()
    abstention = None
    if timeline.run.status != RunStatus.COMPLETED:
        abstention = "storage.run_incomplete"
    elif query.strip():
        document = await execute_search(project, run_id, query, repository, top_k=top_k, mode=mode)
        candidates = _candidates(document, timeline.run.asset.duration_us)
        reason = document["abstentionReason"]
        abstention = None if reason is None else str(reason)
    payload = view_payload(
        inspection_view(timeline, candidates, artifact, abstention_reason=abstention)
    )
    identity = {"project": str(project.resolve()), "run": run_id}
    asset = timeline.run.asset
    event_tags = {event.event_id: event.mechanic_tags for event in timeline.events}
    rows = payload["timeline"]
    assert isinstance(rows, list)
    for row in rows:
        row["mechanicTags"] = list(event_tags[row["eventId"]])
    payload.update(
        {
            "media": {
                "id": asset.media_id,
                "name": asset.source_path.name,
                "durationUs": asset.duration_us,
                "sha256": asset.sha256,
                "videoUrl": "/api/media?" + urlencode(identity),
            },
            "evidence": [
                {
                    "id": item.evidence_id,
                    "kind": item.kind,
                    "startUs": item.source_time.time_us
                    if isinstance(item.source_time, SourceInstant)
                    else item.source_time.start_us,
                    "endUs": item.source_time.time_us
                    if isinstance(item.source_time, SourceInstant)
                    else item.source_time.end_us,
                    "url": "/api/evidence?" + urlencode({**identity, "id": item.evidence_id}),
                }
                for item in timeline.evidence
            ],
            "transcripts": [
                {
                    "startUs": item.source_range.start_us,
                    "endUs": item.source_range.end_us,
                    "text": item.text,
                    "uncertainty": item.uncertainty,
                }
                for item in timeline.transcripts
            ],
            "stages": [
                {
                    "id": stage.stage_id,
                    "status": stage.status.value,
                    "errorCode": stage.error_code,
                }
                for stage in timeline.checkpoints
            ],
            "cost": cost_payload(timeline.invocations),
            "retrievalVersion": RETRIEVAL_VERSION,
            "configHash": timeline.run.config_hash,
            "query": query,
            "mode": mode,
        }
    )
    return payload
