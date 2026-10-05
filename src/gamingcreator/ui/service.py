"""One read of a project run: source-time events plus an optional shipped search."""

import json
import mimetypes
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from gamingcreator.application.detail_query import loads_constraint, query_options
from gamingcreator.application.detail_refinement import (
    RefinementIdentity,
    RefinementSettings,
    refinement_settings_hash,
)
from gamingcreator.application.detail_refinement_budget import canonical_detail_json, payload_hash
from gamingcreator.application.inspection import InspectionView, inspection_view
from gamingcreator.application.observation_text import FACTS_PROJECTION_VERSION, display_facts
from gamingcreator.application.retrieval import RETRIEVAL_VERSION, CandidateClip, RetrievalMode
from gamingcreator.application.storage import RunStatus, StoredInvocation, StoredTimeline
from gamingcreator.cli.main import execute_search
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.detail_cost_history import refinement_cost_history
from gamingcreator.infrastructure.detail_query_sidecar import (
    match_refinement,
    refinement_identity_for_profile,
)
from gamingcreator.infrastructure.detail_refinement_sidecar import reuse_or_refuse
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.media import MediaResource

DETAIL_INSPECTION_VERSION = "actor-detail-inspection-v1"


def _refinement_payload(
    project: Path,
    timeline: StoredTimeline,
    event_id: str | None,
    settings: RefinementSettings,
    identity: RefinementIdentity,
) -> dict[str, object]:
    """Read a frozen key. Availability does not establish a compound query match."""
    payload: dict[str, object] = {
        "status": "unverified",
        "availability": "run_incomplete",
        "requestHash": None,
        "detail": None,
    }
    if timeline.run.status != RunStatus.COMPLETED:
        return payload
    if event_id is None:
        payload["availability"] = "unsupported"
        return payload
    outcome = reuse_or_refuse(project, timeline, event_id, settings=settings, identity=identity)
    payload["requestHash"] = outcome.request_hash
    payload["availability"] = (
        "reused" if outcome.reused else "missing" if outcome.request is not None else "unsupported"
    )
    if outcome.detail is not None:
        payload["payloadHash"] = payload_hash(outcome.detail)
        detail = json.loads(canonical_detail_json(outcome.detail))
        detail["unassignedEvidenceIds"] = list(outcome.detail.unassigned_evidence_ids)
        payload["detail"] = detail
    return payload


def _timecode(microseconds: int) -> str:
    milliseconds = microseconds // 1000
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _analysis_profile(prompt_version: str) -> str:
    if prompt_version in ("phase0-vision-v5", "phase0-vision-v6"):
        return "detailed"
    if prompt_version in ("phase0-vision-v3", "phase0-vision-v4"):
        return "temporal"
    return "frame_observations"


def view_payload(view: InspectionView) -> dict[str, object]:
    return {
        "artifact": view.artifact,
        "runId": view.run_id,
        "runStatus": view.run_status,
        "factsProjectionVersion": FACTS_PROJECTION_VERSION,
        "timeline": [
            {
                "eventId": row.event_id,
                "startUs": row.start_us,
                "endUs": row.end_us,
                "startTimecode": _timecode(row.start_us),
                "endTimecode": _timecode(row.end_us),
                "observableFacts": list(row.facts),
                "displayFacts": list(display_facts(row.facts)),
                "uncertainty": None,
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
                "displayFacts": list(display_facts(row.facts)),
                "uncertainty": None,
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
            profile = _analysis_profile(run.configuration.analysis.vision_prompt_version)
            rows.append(
                {
                    "id": run_id,
                    "status": status,
                    "sourceName": run.asset.source_path.name,
                    "durationUs": run.asset.duration_us,
                    "errorCode": run.error_code,
                    "analysisKind": "temporal"
                    if profile in ("temporal", "detailed")
                    else "frame_observations",
                    "analysisProfile": profile,
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
    project_reference: str | None = None,
    detail_profile: str = "v1",
) -> dict[str, object]:
    """Read events from SQLite, then search only when that run is already completed."""
    refinement_identity = refinement_identity_for_profile(detail_profile)
    artifact = str((project / "timeline.sqlite3").resolve())
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        run = await store.load_run(run_id)
        timeline = await store.load_timeline(
            run_id, require_completed=run.status == RunStatus.COMPLETED
        )
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
    identity = {"project": project_reference or str(project.resolve()), "run": run_id}
    asset = timeline.run.asset
    profile = _analysis_profile(timeline.run.configuration.analysis.vision_prompt_version)
    event_tags = {event.event_id: event.mechanic_tags for event in timeline.events}
    event_uncertainty = {event.event_id: event.uncertainty for event in timeline.events}
    settings = RefinementSettings()
    refinements = {
        event.event_id: _refinement_payload(
            project, timeline, event.event_id, settings, refinement_identity
        )
        for event in timeline.events
    }
    rows = payload["timeline"]
    assert isinstance(rows, list)
    for row in rows:
        row["mechanicTags"] = list(event_tags[row["eventId"]])
        row["uncertainty"] = event_uncertainty[row["eventId"]]
        row["detailRefinement"] = refinements[row["eventId"]]
    candidate_rows = payload["candidates"]
    assert isinstance(candidate_rows, list)
    for row in candidate_rows:
        row["uncertainty"] = event_uncertainty.get(row["eventId"])
        row["detailRefinement"] = (
            refinements[row["eventId"]]
            if row["eventId"] is not None
            else _refinement_payload(project, timeline, None, settings, refinement_identity)
        )
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
            "detailQueryOptions": query_options(),
            "retrievalVersion": RETRIEVAL_VERSION,
            "detailRefinementProfile": {
                "profile": detail_profile,
                "version": DETAIL_INSPECTION_VERSION,
                "settingsHash": refinement_settings_hash(settings),
                "schemaVersion": refinement_identity.schema_version,
                "promptVersion": refinement_identity.prompt_version,
                "promptHash": refinement_identity.prompt_hash,
                "provider": refinement_identity.provider,
                "requestedModel": refinement_identity.requested_model,
            },
            "configHash": timeline.run.config_hash,
            "analysisKind": "temporal"
            if profile in ("temporal", "detailed")
            else "frame_observations",
            "analysisProfile": profile,
            "query": query,
            "mode": mode,
        }
    )
    return payload


async def match_details(
    project: Path, run_id: str, event_id: str, manifest: str, *, profile: str
) -> dict[str, object]:
    """Match explicit positive conditions against an exact saved key, without writes."""
    try:
        constraint = loads_constraint(manifest)
    except ValueError:
        raise AppError("input.detail_query", "复合条件格式或词表无效。", ExitCode.INPUT) from None
    refinement_identity_for_profile(profile)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timeline = await store.load_timeline(run_id, require_completed=True)
    finally:
        await store.close()
    if not any(event.event_id == event_id for event in timeline.events):
        raise AppError("input.detail_event", "当前运行没有这个片段。", ExitCode.INPUT, run_id)
    return match_refinement(project, timeline, event_id, constraint, profile=profile, save=False)


async def detail_costs(project: Path, run_id: str) -> dict[str, object]:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        await store.load_run(run_id)
    finally:
        await store.close()
    return refinement_cost_history(project, run_id)
