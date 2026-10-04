"""One read of a project run: source-time events plus an optional shipped search."""

from pathlib import Path

from gamingcreator.application.inspection import InspectionView, inspection_view
from gamingcreator.application.retrieval import CandidateClip, RetrievalMode
from gamingcreator.application.storage import RunStatus
from gamingcreator.cli.main import execute_search
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


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
    return view_payload(
        inspection_view(timeline, candidates, artifact, abstention_reason=abstention)
    )
