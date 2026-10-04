import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import wave
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import CostStatus, InvocationMetadata, ProviderUsage
from gamingcreator.application.storage import (
    InvocationStatus,
    RunConfiguration,
    RunStatus,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import (
    AudioEvidence,
    AudioFrameMapping,
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
    VisualEvidence,
)
from gamingcreator.domain.models import SemanticEvent, TranscriptSegment
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

HASH = "a" * 64
CONFIG = RunConfiguration(AnalysisConfig("test", "fixture", 20, 100), Decimal("1.0"), "v1", HASH)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle_fixture(root: Path, run_id: str = "run-1", *, audio: bool = False):
    source = root / "source.fixture"
    source.write_bytes(b"not a real video: storage fixture")
    streams = (MediaStream(0, "video", Fraction(1, 1000), 1000, 2000),)
    asset = MediaAsset(
        sha(source), source.resolve(), sha(source), streams, Fraction(1), 2_000_000, "fixture"
    )
    directory = root / "project" / "runs" / run_id / "media"
    directory.mkdir(parents=True)
    image_path = directory / "frame.png"
    image_path.write_bytes(b"not a real image: storage fixture")
    image = VisualEvidence(
        f"{run_id}:image",
        image_path,
        sha(image_path),
        1100,
        Fraction(1, 1000),
        SourceInstant(100_000, asset.duration_us),
    )
    audio_evidence = None
    if audio:
        audio_path = directory / "audio.wav"
        with wave.open(str(audio_path), "wb") as destination:
            destination.setnchannels(1)
            destination.setsampwidth(2)
            destination.setframerate(16000)
            destination.writeframes(b"\x00" * 64000)
        # A gap between contiguous WAV pieces remains explicit in source time.
        frames = (
            AudioFrameMapping(0, 16000, 16000, Fraction(1, 16000)),
            AudioFrameMapping(16000, 16000, 32001, Fraction(1, 16000)),
        )
        audio_evidence = AudioEvidence(
            f"{run_id}:audio", audio_path, sha(audio_path), 16000, 32000, frames, 48000, 32001
        )
    bundle = MediaPreprocessingResult(
        asset,
        (image,),
        audio_evidence,
        directory / "media-manifest.json",
        "fixture-v1",
        "fixture-processor",
    )
    write_manifest(bundle, SamplingParameters())
    return bundle


def event_fixture(bundle, run_id="run-1", event_id="event-1", evidence_id=None):
    return SemanticEvent(
        event_id,
        bundle.asset.media_id,
        run_id,
        SourceRange(100_000, 800_000, bundle.asset.duration_us),
        ("Observed fixture action",),
        ("fixture-mechanic",),
        (evidence_id or bundle.images[0].evidence_id,),
        "visual",
        None,
    )


def metadata(attempt=1, usage=None):
    return InvocationMetadata(
        "test", "fixture", None, None, "prompt-v1", "schema-v1", attempt, usage or ProviderUsage()
    )


async def media_ready(store, bundle, run_id="run-1"):
    await store.create_run(run_id, bundle.asset, CONFIG)
    await store.begin_stage(run_id, "media", HASH)
    await store.persist_media_bundle(run_id, bundle)


def test_completed_timeline_and_immutable_configuration(tmp_path):
    bundle = bundle_fixture(tmp_path)

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, bundle)
            with pytest.raises(AppError, match="项目存储") as incomplete:
                await store.load_completed_timeline("run-1")
            assert incomplete.value.code == "storage.run_incomplete"
            await store.begin_stage("run-1", "vision", HASH)
            await store.begin_invocation("attempt-1", "run-1", "vision", "window-1", metadata())
            usage = ProviderUsage(0, 0, 0, Decimal("0"), "CNY", Decimal("0"), CostStatus.CONFIRMED)
            await store.finish_invocation(
                "attempt-1", InvocationStatus.COMPLETED, metadata(usage=usage)
            )
            event = event_fixture(bundle)
            segment = TranscriptSegment(
                bundle.asset.media_id,
                event.source_range,
                "fixture transcript",
                '{"reason":"piecewise_audio_clock","discontinuitySampleOffsets":[16000]}',
            )
            await store.persist_timeline("run-1", "vision", (event,), (segment,), HASH)
            await store.complete_run("run-1")
            timeline = await store.load_completed_timeline("run-1")
            assert timeline.events == (event,)
            assert timeline.transcripts == (segment,)
            assert timeline.run.configuration == CONFIG
            assert timeline.invocations[0].metadata.usage.original_cost == Decimal("0")
            for operation in (
                store.begin_stage("run-1", "new", HASH),
                store.stop_run("run-1", RunStatus.FAILED, "fixture.failed"),
                store.complete_run("run-1"),
            ):
                with pytest.raises(AppError) as immutable:
                    await operation
                assert immutable.value.code == "storage.run_immutable"
            reader = await SqliteTimelineStore.open(tmp_path / "project", read_only=True)
            try:
                reloaded = await reader.load_completed_timeline("run-1")
                assert reloaded.events == (event,)
                assert reloaded.transcripts == (segment,)
                with pytest.raises(AppError) as read_only:
                    await reader.recover()
                assert read_only.value.code == "storage.read_only"
            finally:
                await reader.close()
        finally:
            await store.close()

    asyncio.run(scenario())


def test_batch_rollback_on_dangling_evidence_and_connection_remains_usable(tmp_path):
    bundle = bundle_fixture(tmp_path)

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, bundle)
            await store.begin_stage("run-1", "vision", HASH)
            valid = event_fixture(bundle)
            invalid = event_fixture(bundle, event_id="event-2", evidence_id="missing")
            with pytest.raises(AppError) as error:
                await store.persist_timeline("run-1", "vision", (valid, invalid), (), HASH)
            assert error.value.code == "storage.constraint"
            with closing(sqlite3.connect(tmp_path / "project" / "timeline.sqlite3")) as connection:
                assert connection.execute("SELECT count(*) FROM semantic_events").fetchone()[0] == 0
                assert (
                    connection.execute(
                        "SELECT status FROM stage_checkpoints WHERE stage_id='vision'"
                    ).fetchone()[0]
                    == "running"
                )
            await store.persist_timeline("run-1", "vision", (valid,), (), HASH)
            await store.complete_run("run-1")
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["delete", "rewrite", "source", "manifest"])
def test_completed_query_refuses_damage_and_recovery_invalidates_run(tmp_path, change):
    bundle = bundle_fixture(tmp_path)

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, bundle)
            await store.begin_stage("run-1", "vision", HASH)
            await store.persist_timeline("run-1", "vision", (event_fixture(bundle),), (), HASH)
            await store.complete_run("run-1")
            if change == "delete":
                bundle.images[0].path.unlink()
            elif change == "source":
                bundle.asset.source_path.write_bytes(b"changed source")
            elif change == "manifest":
                bundle.manifest_path.write_text("{}")
            else:
                bundle.images[0].path.write_bytes(b"changed evidence")
            with pytest.raises(AppError) as error:
                await store.load_completed_timeline("run-1")
            assert error.value.code == "storage.integrity"
            report = await store.recover()
            assert report.integrity_issues
            run = await store.load_run("run-1")
            assert run.status == RunStatus.FAILED and run.error_code == "storage.integrity"
            with pytest.raises(AppError):
                await store.load_completed_timeline("run-1")
        finally:
            await store.close()

    asyncio.run(scenario())


def test_recover_preserves_media_mapping_ledger_precision_and_reports_orphans(tmp_path):
    bundle = bundle_fixture(tmp_path, audio=True)

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, bundle)
            await store.begin_stage("run-1", "vision", HASH)
            await store.begin_invocation("known", "run-1", "vision", "window-1", metadata())
            amount = Decimal("0.00000000000000000000000012345")
            await store.finish_invocation(
                "known",
                InvocationStatus.FAILED,
                metadata(
                    usage=ProviderUsage(
                        original_cost=amount,
                        currency="CNY",
                        cost_cny=amount,
                        cost_status=CostStatus.ESTIMATED,
                    )
                ),
                "provider.network",
            )
            await store.begin_invocation("unknown", "run-1", "vision", "window-2", metadata())
            orphan = bundle.manifest_path.parent / "orphan.png"
            orphan.write_bytes(b"published but never registered")
            temporary = bundle.manifest_path.parent / "partial.tmp"
            temporary.write_bytes(b"unfinished")
            report = await store.recover()
            assert report.interrupted_runs == ("run-1",)
            assert report.interrupted_stages == (("run-1", "vision"),)
            assert report.interrupted_invocations == ("unknown",)
            assert report.orphan_files == (orphan,)
            assert report.temporary_files == (temporary,)
            assert orphan.exists() and temporary.exists()
            assert await store.load_media_bundle("run-1") == bundle
            ledger = {item.invocation_id: item for item in await store.load_invocations("run-1")}
            assert ledger["known"].metadata.usage.original_cost == amount
            assert ledger["unknown"].status == InvocationStatus.INTERRUPTED
            assert ledger["unknown"].metadata.usage.original_cost is None
            with closing(sqlite3.connect(tmp_path / "project" / "timeline.sqlite3")) as connection:
                assert (
                    connection.execute(
                        "SELECT typeof(original_cost) FROM provider_invocations WHERE invocation_id='known'"
                    ).fetchone()[0]
                    == "text"
                )
                assert connection.execute(
                    "SELECT original_cost,input_tokens FROM provider_invocations WHERE invocation_id='unknown'"
                ).fetchone() == (None, None)
                for table in (
                    "media_assets",
                    "analysis_runs",
                    "evidence",
                    "semantic_events",
                    "provider_invocations",
                ):
                    assert all(
                        column[2] != "BLOB"
                        for column in connection.execute(f"PRAGMA table_info({table})")
                    )
            with pytest.raises(AppError) as mismatch:
                await store.begin_stage("run-1", "vision", "b" * 64)
            assert mismatch.value.code == "storage.resume_mismatch"
            await store.begin_stage("run-1", "vision", HASH)
            # Recovery itself never replays or removes the unknown attempt.
            assert len(await store.load_invocations("run-1")) == 2
            await store.persist_timeline("run-1", "vision", (), (), HASH)
            await store.complete_run("run-1")
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field",
    [
        "discontinuityOffsets",
        "boundaryToleranceSamples",
        "samplesBeyondDeclaredEndRemoved",
        "clampedStartSeconds",
    ],
)
def test_media_bundle_rejects_false_audio_mapping_proof(tmp_path, field):
    bundle = bundle_fixture(tmp_path, audio=True)
    data = json.loads(bundle.manifest_path.read_text())
    if field == "clampedStartSeconds":
        data["audio"]["coverage"][field] = {"numerator": 1, "denominator": 10}
    else:
        data["audio"][field] = [] if field == "discontinuityOffsets" else 999
    bundle.manifest_path.write_text(json.dumps(data))

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await store.create_run("run-1", bundle.asset, CONFIG)
            await store.begin_stage("run-1", "media", HASH)
            with pytest.raises(AppError) as error:
                await store.persist_media_bundle("run-1", bundle)
            assert error.value.code == "storage.manifest"
            with closing(sqlite3.connect(tmp_path / "project" / "timeline.sqlite3")) as connection:
                assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0
        finally:
            await store.close()

    asyncio.run(scenario())


def test_external_artifact_and_cross_run_evidence_rejected(tmp_path):
    first = bundle_fixture(tmp_path, "run-1")
    second = bundle_fixture(tmp_path, "run-2")

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, first)
            await store.create_run("run-2", second.asset, CONFIG)
            await store.begin_stage("run-2", "media", HASH)
            with pytest.raises(AppError) as external:
                await store.persist_media_bundle(
                    "run-2", replace(second, manifest_path=first.manifest_path)
                )
            assert external.value.code == "storage.artifact_path"
            await store.persist_media_bundle("run-2", second)
            await store.begin_stage("run-2", "vision", HASH)
            event = event_fixture(second, "run-2", evidence_id=first.images[0].evidence_id)
            with pytest.raises(AppError) as cross_run:
                await store.persist_timeline("run-2", "vision", (event,), (), HASH)
            assert cross_run.value.code == "storage.constraint"
        finally:
            await store.close()

    asyncio.run(scenario())


def test_pending_calls_block_checkpoint_and_duplicate_logical_attempt_rolls_back(tmp_path):
    bundle = bundle_fixture(tmp_path)

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, bundle)
            await store.begin_stage("run-1", "vision", HASH)
            await store.begin_invocation("one", "run-1", "vision", "window-1", metadata())
            await store.begin_invocation("two", "run-1", "vision", "window-2", metadata())
            with pytest.raises(AppError) as duplicate:
                await store.begin_invocation("duplicate", "run-1", "vision", "window-1", metadata())
            assert duplicate.value.code == "storage.constraint"
            with pytest.raises(AppError) as pending:
                await store.persist_timeline("run-1", "vision", (event_fixture(bundle),), (), HASH)
            assert pending.value.code == "storage.invocation_pending"
            await store.finish_invocation(
                "one", InvocationStatus.CANCELLED, metadata(), "provider.cancelled"
            )
            await store.finish_invocation("two", InvocationStatus.NO_SPEECH, metadata())
            await store.persist_timeline("run-1", "vision", (), (), HASH)
            await store.complete_run("run-1")
        finally:
            await store.close()

    asyncio.run(scenario())


def test_unsafe_registered_path_does_not_abort_recovery_of_other_runs(tmp_path):
    first = bundle_fixture(tmp_path, "run-1")
    second = bundle_fixture(tmp_path, "run-2")

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, first)
            await media_ready(store, second, "run-2")
            for run_id in ("run-1", "run-2"):
                await store.begin_stage(run_id, "vision", HASH)
                await store.begin_invocation(run_id, run_id, "vision", "window-1", metadata())
            # Inject a corrupt on-disk path; the normal registration API rejects this.
            with closing(sqlite3.connect(tmp_path / "project" / "timeline.sqlite3")) as connection:
                connection.execute(
                    "UPDATE evidence SET artifact_path='../outside' WHERE run_id='run-1'"
                )
                connection.commit()
            report = await store.recover()
            assert report.interrupted_runs == ("run-1", "run-2")
            assert report.interrupted_invocations == ("run-1", "run-2")
            assert report.integrity_issues[0].code == "storage.artifact_path"
            assert (await store.load_run("run-1")).status == RunStatus.FAILED
            assert (await store.load_run("run-2")).status == RunStatus.INTERRUPTED
            assert (await store.load_invocations("run-2"))[0].metadata.usage.original_cost is None
            assert await store.load_media_bundle("run-2") == second
        finally:
            await store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "damage",
    ["budget", "provider", "pipeline_snapshot", "media_zero_denominator", "media_column_conflict"],
)
def test_corrupt_snapshot_does_not_abort_other_running_attempts(tmp_path, damage):
    first = bundle_fixture(tmp_path, "run-1")
    second = bundle_fixture(tmp_path, "run-2")

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, first)
            await media_ready(store, second, "run-2")
            for run_id in ("run-1", "run-2"):
                await store.begin_stage(run_id, "vision", HASH)
                await store.begin_invocation(run_id, run_id, "vision", "window", metadata())
            with closing(sqlite3.connect(tmp_path / "project" / "timeline.sqlite3")) as connection:
                if damage.startswith("media_"):
                    if damage == "media_column_conflict":
                        connection.execute(
                            "UPDATE media_assets SET source_path='conflicting-column'"
                        )
                    else:
                        payload = json.loads(
                            connection.execute("SELECT payload_json FROM media_assets").fetchone()[
                                0
                            ]
                        )
                        payload["originSeconds"]["denominator"] = 0
                        connection.execute(
                            "UPDATE media_assets SET payload_json=?", (json.dumps(payload),)
                        )
                else:
                    config = json.loads(
                        connection.execute(
                            "SELECT config_json FROM analysis_runs WHERE run_id='run-1'"
                        ).fetchone()[0]
                    )
                    if damage == "budget":
                        config["max_cost_cny"] = "invalid_decimal"
                    elif damage == "provider":
                        config["analysis"]["provider"] = 42
                    else:
                        config["pipeline_version"] = "different_snapshot"
                    connection.execute(
                        "UPDATE analysis_runs SET config_json=? WHERE run_id='run-1'",
                        (json.dumps(config, sort_keys=True, separators=(",", ":")),),
                    )
                connection.commit()
            report = await store.recover()
            assert report.interrupted_invocations == ("run-1", "run-2")
            assert report.integrity_issues
            for run_id in ("run-1", "run-2"):
                assert (await store.load_invocations(run_id))[
                    0
                ].status == InvocationStatus.INTERRUPTED
                assert (await store.load_invocations(run_id))[
                    0
                ].metadata.usage.original_cost is None
            if not damage.startswith("media_"):
                assert (await store.load_run("run-2")).status == RunStatus.INTERRUPTED
            with pytest.raises(AppError) as error:
                await store.load_run("run-1")
            assert error.value.code == "storage.integrity"
        finally:
            await store.close()

    asyncio.run(scenario())


def test_readonly_open_rejects_missing_constraint_trigger(tmp_path):
    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path)
        await store.close()
        with closing(sqlite3.connect(tmp_path / "timeline.sqlite3")) as connection:
            connection.execute("DROP TRIGGER evidence_duration_insert")
            connection.commit()
        for read_only in (True, False):
            with pytest.raises(AppError) as error:
                await SqliteTimelineStore.open(tmp_path, read_only=read_only)
            assert error.value.code == "storage.schema_invalid"

    asyncio.run(scenario())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction recovery regression")
def test_recovery_does_not_traverse_external_junction(tmp_path):
    bundle = bundle_fixture(tmp_path)
    target = tmp_path / "external-artifacts"
    target.mkdir()
    (target / "evidence.png").write_bytes(bundle.images[0].path.read_bytes())
    (target / "external-orphan.png").write_bytes(b"must not be scanned")
    link = tmp_path / "project" / "runs" / "escape"
    environment = os.environ.copy()
    environment.update(F004_TEST_LINK=str(link), F004_TEST_TARGET=str(target))
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "New-Item -ItemType Junction -Path $env:F004_TEST_LINK -Target $env:F004_TEST_TARGET | Out-Null",
        ],
        env=environment,
        check=True,
        capture_output=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert link.is_junction()

    async def scenario():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, bundle)
            await store.begin_stage("run-1", "vision", HASH)
            await store.begin_invocation("running", "run-1", "vision", "window", metadata())
            with closing(sqlite3.connect(tmp_path / "project" / "timeline.sqlite3")) as connection:
                connection.execute("UPDATE evidence SET artifact_path='runs/escape/evidence.png'")
                connection.commit()
            report = await store.recover()
            assert report.interrupted_invocations == ("running",)
            assert any(issue.code == "storage.artifact_path" for issue in report.integrity_issues)
            assert all("external-orphan" not in path.name for path in report.orphan_files)
            assert (target / "external-orphan.png").exists()
        finally:
            await store.close()

    asyncio.run(scenario())
