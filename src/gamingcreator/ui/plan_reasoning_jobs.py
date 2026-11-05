"""Source-verified dynamic plans reuse ordinary plan jobs and reasoning receipts."""

import asyncio
from dataclasses import replace
from hashlib import sha256
from typing import Any

from gamingcreator.application.creation_proposals import canonical
from gamingcreator.application.plan_proposals import (
    PlanSnapshot,
    compile_plan_proposal,
    create_plan_snapshot,
    validate_plan_proposal,
)
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def original_snapshot(jobs: Any, job_id: str) -> tuple[PlanSnapshot, dict[str, Any]]:
    directory = jobs.directory(job_id)
    state = jobs.read(directory / "status.json")
    if state["kind"] != "plan" or state["status"] != "completed":
        raise ValueError("Planning requires a completed ordinary plan job.")
    jobs.verify(directory, state)
    stored = jobs.read(directory / "request.json")
    request = stored["request"]
    project = jobs.project(request["projectId"])

    async def load() -> tuple[Any, ...]:
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return tuple([await store.load_completed_timeline(run) for run in request["runIds"]])
        finally:
            await store.close()

    timelines = asyncio.run(load())
    for timeline in timelines:
        if hash_file(timeline.run.asset.source_path) != timeline.run.asset.sha256:
            raise ValueError("Original source bytes changed.")
    snapshot = create_plan_snapshot(
        CreativeBrief.from_json(request["brief"]),
        timelines,
        request["fps"],
        tuple(request.get("eventIds", [])),
        request.get("clipRanges"),
    )
    payload = snapshot.payload
    payload["origin"] = {
        "jobId": job_id,
        "requestDigest": stored["digest"],
        "receiptSha256": hash_file(directory / "result/receipt.json"),
    }
    return replace(snapshot, payload_json=canonical(payload)), request


def service_for(jobs: Any) -> Any:
    from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
    from gamingcreator.ui.creation_reasoning_service import CreationReasoningService

    return CreationReasoningService(jobs, price_snapshot=DEEPSEEK_FLASH_20261004)


def verified_plan(jobs: Any, request: dict[str, Any], service: Any = None) -> dict[str, Any]:
    service = service or service_for(jobs)
    prepared_hash = request["reasoningPreparedHash"]
    record = service._prepared(prepared_hash)
    if record.get("purpose", "edit") != "plan":
        raise ValueError("An edit result cannot become a plan.")
    snapshot = service._current(record)
    result = service.read_result(prepared_hash)
    if result["status"] != "completed" or result["proposal"] is None:
        raise ValueError("No successful plan proposal available.")
    _, original = original_snapshot(jobs, record["jobId"])
    expected = adoption_request(original, prepared_hash)
    if request != expected:
        raise ValueError("Adopted brief or basket identity changed.")
    proposal = validate_plan_proposal(snapshot, result["proposal"]["response"])
    report = compile_plan_proposal(snapshot, proposal)
    report["reasoningProvenance"] = {
        "preparedHash": prepared_hash,
        "resultHash": sha256(canonical(result).encode()).hexdigest(),
        "requestHash": record["requestHash"],
        "providerMetadata": result["metadata"],
        "promptVersion": record["request"]["prompt_version"],
        "schemaVersion": record["request"]["schema_version"],
    }
    return report


def adoption_request(original: dict[str, Any], prepared_hash: str) -> dict[str, Any]:
    request = {
        key: value
        for key, value in original.items()
        if key not in {"requestId", "reasoningPreparedHash"}
    }
    request.update(
        requestId=sha256(("adopt-plan:" + prepared_hash).encode()).hexdigest()[:32],
        reasoningPreparedHash=prepared_hash,
    )
    return request


def adopt(service: Any, prepared_hash: str) -> dict[str, Any]:
    record = service._prepared(prepared_hash)
    if record.get("purpose", "edit") != "plan":
        raise ValueError("An edit result cannot become a plan.")
    _, original = original_snapshot(service.jobs, record["jobId"])
    request = adoption_request(original, prepared_hash)
    verified_plan(service.jobs, request, service)
    return dict(service.jobs.submit("plan", request))


def save_plan(jobs: Any, directory: Any, request: dict[str, Any]) -> None:
    report = verified_plan(jobs, request)
    write_creation(
        directory / "result", {"plans.json": report}, (jobs.project(request["projectId"]),)
    )
