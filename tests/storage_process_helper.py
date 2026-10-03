"""Small, model-free fixtures and crash probes for persistence process tests."""

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import CostStatus, InvocationMetadata, ProviderUsage
from gamingcreator.application.storage import InvocationStatus, RunConfiguration
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import (
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
    VisualEvidence,
)
from gamingcreator.domain.models import SemanticEvent, TranscriptSegment
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

RUN_ID = "process-run"
PIPELINE_HASH = "a" * 64


def fixture_asset(project: Path) -> MediaAsset:
    """Fixture bytes exercise hashing and storage, never media-quality acceptance."""
    project.mkdir(parents=True, exist_ok=True)
    source = (project / "fixture-source.mp4").resolve()
    source.write_bytes(b"storage-only fixture; this is not a playable video")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return MediaAsset(
        digest,
        source,
        digest,
        (MediaStream(0, "video", Fraction(1), 0, 2),),
        Fraction(0),
        2_000_000,
        "storage-fixture-v1",
    )


def fixture_configuration() -> RunConfiguration:
    return RunConfiguration(
        AnalysisConfig("fixture-provider", "fixture-model", 3, 2),
        Decimal("1.2345"),
        "process-test-v1",
        PIPELINE_HASH,
    )


def fixture_metadata() -> InvocationMetadata:
    return InvocationMetadata(
        "fixture-provider",
        "fixture-model",
        None,
        None,
        "prompt-v1",
        "schema-v1",
        1,
        ProviderUsage(),
    )


def fixture_bundle(project: Path, asset: MediaAsset) -> MediaPreprocessingResult:
    directory = project / "runs" / RUN_ID
    directory.mkdir(parents=True)
    image = directory / "frame-000001.jpg"
    image.write_bytes(b"storage-only image fixture")
    evidence = VisualEvidence(
        f"{RUN_ID}:{asset.media_id}:image:000001",
        image,
        hashlib.sha256(image.read_bytes()).hexdigest(),
        1,
        Fraction(1),
        SourceInstant(1_000_000, asset.duration_us),
    )
    bundle = MediaPreprocessingResult(
        asset,
        (evidence,),
        None,
        directory / "manifest.json",
        "fixture-transform-v1",
        "fixture-processor-v1",
    )
    write_manifest(bundle, SamplingParameters())
    return bundle


async def prepare(project: Path, *, completed: bool) -> None:
    asset = fixture_asset(project)
    bundle = fixture_bundle(project, asset)
    store = await SqliteTimelineStore.open(project)
    await store.create_run(RUN_ID, asset, fixture_configuration())
    await store.begin_stage(RUN_ID, "media", asset.sha256)
    await store.persist_media_bundle(RUN_ID, bundle)
    await store.begin_stage(RUN_ID, "vision", PIPELINE_HASH)
    await store.begin_invocation("invocation-1", RUN_ID, "vision", "window-1", fixture_metadata())
    if not completed:
        # Skip all Python cleanup, including the executor and SQLite connection.
        os._exit(42)
    metadata = replace(
        fixture_metadata(),
        actual_model="fixture-resolved-model",
        model_revision="fixture-revision-1",
        usage=ProviderUsage(
            input_tokens=17,
            output_tokens=5,
            cached_input_tokens=0,
            original_cost=Decimal("0.01234567890123456789"),
            currency="CNY",
            cost_cny=Decimal("0.01234567890123456789"),
            cost_status=CostStatus.CONFIRMED,
        ),
        elapsed_ms=123,
        price_version="fixture-prices-v1",
        request_id="request-1",
    )
    await store.finish_invocation("invocation-1", InvocationStatus.COMPLETED, metadata)
    event = SemanticEvent(
        "event-1",
        asset.media_id,
        RUN_ID,
        SourceRange(500_000, 1_500_000, asset.duration_us),
        ("storage fixture action",),
        ("fixture-mechanic",),
        (bundle.images[0].evidence_id,),
        "visual",
        None,
    )
    transcript = TranscriptSegment(
        asset.media_id, SourceRange(250_000, 750_000, asset.duration_us), "fixture transcript"
    )
    await store.persist_timeline(RUN_ID, "vision", (event,), (transcript,), "b" * 64)
    await store.complete_run(RUN_ID)
    await store.close()


async def read_completed(project: Path) -> dict[str, object]:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timeline = await store.load_completed_timeline(RUN_ID)
        invocation = timeline.invocations[0]
        return {
            "status": str(timeline.run.status),
            "budget": str(timeline.run.configuration.max_cost_cny),
            "pipelineHash": timeline.run.configuration.pipeline_hash,
            "eventIds": [event.event_id for event in timeline.events],
            "eventEvidence": [list(event.evidence_ids) for event in timeline.events],
            "evidenceIds": [item.evidence_id for item in timeline.evidence],
            "evidenceHashesValid": all(
                hashlib.sha256(item.artifact_path.read_bytes()).hexdigest() == item.sha256
                for item in timeline.evidence
            ),
            "transcripts": [segment.text for segment in timeline.transcripts],
            "checkpoints": {item.stage_id: str(item.status) for item in timeline.checkpoints},
            "invocationId": invocation.invocation_id,
            "modelRevision": invocation.metadata.model_revision,
            "cost": str(invocation.metadata.usage.cost_cny),
            "costStatus": str(invocation.metadata.usage.cost_status),
            "inputTokens": invocation.metadata.usage.input_tokens,
            "requestId": invocation.metadata.request_id,
        }
    finally:
        await store.close()


async def recover(project: Path) -> dict[str, object]:
    store = await SqliteTimelineStore.open(project)
    try:
        report = await store.recover()
        run = await store.load_run(RUN_ID)
        invocations = await store.load_invocations(RUN_ID)
        bundle = await store.load_media_bundle(RUN_ID)
        timeline_error: str | None
        try:
            await store.load_completed_timeline(RUN_ID)
        except AppError as error:
            timeline_error = error.code
        else:
            timeline_error = None
        return {
            "runStatus": str(run.status),
            "interruptedRuns": list(report.interrupted_runs),
            "interruptedStages": [list(stage) for stage in report.interrupted_stages],
            "interruptedInvocations": list(report.interrupted_invocations),
            "integrityIssues": [issue.code for issue in report.integrity_issues],
            "invocationStatus": str(invocations[0].status),
            "cost": invocations[0].metadata.usage.cost_cny,
            "inputTokens": invocations[0].metadata.usage.input_tokens,
            "outputTokens": invocations[0].metadata.usage.output_tokens,
            "costStatus": str(invocations[0].metadata.usage.cost_status),
            "mediaImages": len(bundle.images),
            "timelineError": timeline_error,
        }
    finally:
        await store.close()


def crash_transaction(project: Path) -> None:
    connection = sqlite3.connect(project / "timeline.sqlite3", autocommit=True)
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("UPDATE analysis_runs SET status='failed' WHERE run_id=?", (RUN_ID,))
    connection.execute("DELETE FROM event_evidence WHERE event_id='event-1'")
    os._exit(47)


def main() -> None:
    mode, location = sys.argv[1:]
    project = Path(location)
    if mode == "create-completed":
        asyncio.run(prepare(project, completed=True))
    elif mode == "create-interrupted":
        asyncio.run(prepare(project, completed=False))
    elif mode == "read-completed":
        print(json.dumps(asyncio.run(read_completed(project)), sort_keys=True))
    elif mode == "recover":
        print(json.dumps(asyncio.run(recover(project)), sort_keys=True))
    elif mode == "crash-transaction":
        crash_transaction(project)
    else:
        raise ValueError("Unknown process test mode")


if __name__ == "__main__":
    main()
