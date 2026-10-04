"""Project-local SQLite persistence on one connection-owning worker thread."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.providers import CostStatus, InvocationMetadata, ProviderUsage
from gamingcreator.application.retrieval import SearchResult
from gamingcreator.application.storage import (
    IntegrityIssue,
    InvocationStatus,
    RecoveryReport,
    RunConfiguration,
    RunStatus,
    StageCheckpoint,
    StageStatus,
    StoredInvocation,
    StoredRun,
    StoredTimeline,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import (
    AudioEvidence,
    AudioFrameMapping,
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
    VisualEvidence,
)
from gamingcreator.domain.models import (
    EmbeddingSpace,
    EvidenceReference,
    SemanticEvent,
    TranscriptSegment,
)
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.retrieval_persistence import (
    PersistedRetrievalHit,
    persist_embedding,
    persist_retrieval,
)
from gamingcreator.infrastructure.retrieval_persistence import (
    load_retrieval as read_retrieval,
)
from gamingcreator.infrastructure.sqlite_schema import migrate, validate_schema
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock


def _error(code: str) -> AppError:
    return AppError(
        code, "项目存储校验失败，请按交接记录检查运行状态与本地文件。", ExitCode.STORAGE
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _object(value: str) -> dict[str, Any]:
    result = json.loads(value)
    if not isinstance(result, dict):
        raise _error("storage.invalid")
    return cast(dict[str, Any], result)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise _error("storage.invalid_hash")
    return value


def _id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise _error("storage.invalid_id")
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _asset_json(asset: MediaAsset) -> str:
    return _json(
        {
            "mediaId": asset.media_id,
            "sourcePath": str(asset.source_path.resolve()),
            "sha256": asset.sha256,
            "durationUs": asset.duration_us,
            "originSeconds": {
                "numerator": asset.origin_seconds.numerator,
                "denominator": asset.origin_seconds.denominator,
            },
            "probeVersion": asset.probe_version,
            "streams": [
                {
                    "index": stream.index,
                    "kind": stream.kind,
                    "timeBase": {
                        "numerator": stream.time_base.numerator,
                        "denominator": stream.time_base.denominator,
                    },
                    "startPts": stream.start_pts,
                    "durationTs": stream.duration_ts,
                }
                for stream in asset.streams
            ],
        }
    )


def _fraction(value: dict[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def _asset(value: str) -> MediaAsset:
    data = _object(value)
    return MediaAsset(
        data["mediaId"],
        Path(data["sourcePath"]),
        data["sha256"],
        tuple(
            MediaStream(
                stream["index"],
                stream["kind"],
                _fraction(stream["timeBase"]),
                stream["startPts"],
                stream["durationTs"],
            )
            for stream in data["streams"]
        ),
        _fraction(data["originSeconds"]),
        data["durationUs"],
        data["probeVersion"],
    )


def _config_json(config: RunConfiguration) -> str:
    analysis = config.analysis
    temporal = analysis.vision_prompt_version == "phase0-vision-v3"
    if (
        not analysis.provider.strip()
        or not analysis.model.strip()
        or type(analysis.max_requests) is not int
        or analysis.max_requests <= 0
        or type(analysis.max_input_frames) is not int
        or analysis.max_input_frames <= 0
        or not isinstance(config.max_cost_cny, Decimal)
        or not config.max_cost_cny.is_finite()
        or config.max_cost_cny <= 0
        or not config.pipeline_version.strip()
        or not config.required_stages
        or len(set(config.required_stages)) != len(config.required_stages)
    ):
        raise _error("storage.invalid_config")
    _digest(config.pipeline_hash)
    for stage in config.required_stages:
        _id(stage)
    analysis_data = asdict(analysis)
    if analysis.vision_prompt_hash is None and analysis.vision_prompt_version == "phase0-vision-v1":
        # The first v2 snapshots predate explicit prompt pinning; preserve their bytes.
        analysis_data.pop("vision_prompt_version")
        analysis_data.pop("vision_prompt_hash")
    if analysis.schema_version == 1:
        # Keep canonical v1 snapshots byte-for-byte compatible with existing databases.
        analysis_data = {
            key: analysis_data[key]
            for key in ("provider", "model", "max_requests", "max_input_frames")
        }
    elif analysis.schema_version != 2 or (
        not analysis.price_version
        or type(analysis.sampling_interval_ms) is not int
        or not 100 <= analysis.sampling_interval_ms <= 60000
        or type(analysis.window_frames) is not int
        or not (2 if temporal else 1) <= analysis.window_frames <= (9 if temporal else 5)
        or type(analysis.window_overlap) is not int
        or not 0 <= analysis.window_overlap < analysis.window_frames
        or type(analysis.max_output_tokens) is not int
        or not 1 <= analysis.max_output_tokens <= 4096
        or analysis.asr_language not in ("zh", "en", "auto")
        or analysis.vision_prompt_version
        not in ("phase0-vision-v1", "phase0-vision-v2", "phase0-vision-v3")
        or (
            analysis.vision_prompt_hash is None
            and analysis.vision_prompt_version != "phase0-vision-v1"
        )
    ):
        raise _error("storage.invalid_config")
    if analysis.vision_prompt_hash is not None:
        _digest(analysis.vision_prompt_hash)
    # Accept a typed allowlist, never arbitrary configuration dictionaries or credentials.
    return _json(
        {
            "analysis": analysis_data,
            "max_cost_cny": str(config.max_cost_cny),
            "pipeline_version": config.pipeline_version,
            "pipeline_hash": config.pipeline_hash,
            "required_stages": config.required_stages,
        }
    )


def _metadata_json(metadata: InvocationMetadata) -> str:
    if (
        not metadata.provider.strip()
        or not metadata.requested_model.strip()
        or not metadata.prompt_version.strip()
        or not metadata.schema_version.strip()
        or type(metadata.attempt) is not int
        or metadata.attempt <= 0
        or (
            metadata.elapsed_ms is not None
            and (type(metadata.elapsed_ms) is not int or metadata.elapsed_ms < 0)
        )
    ):
        raise _error("storage.invalid_invocation")
    # Reconstruct to validate even a metadata object supplied by another adapter.
    ProviderUsage(**asdict(metadata.usage))
    data = asdict(metadata)
    data.pop("usage")
    return _json(data)


def _usage_values(usage: ProviderUsage) -> tuple[object, ...]:
    return (
        usage.input_tokens,
        usage.output_tokens,
        usage.cached_input_tokens,
        None if usage.original_cost is None else str(usage.original_cost),
        usage.currency,
        None if usage.cost_cny is None else str(usage.cost_cny),
        str(usage.cost_status),
    )


class SqliteTimelineStore:
    """Use open()/close(); queued operations are atomic even if their awaiter cancels.

    No transaction spans hashing, model calls or awaits. close drains previously
    queued operations and closes the connection before releasing the writer lock.
    Read-only instances do not take that lock and never run migrations.
    """

    def __init__(self, project: Path, *, read_only: bool) -> None:
        self.project = project.resolve()
        self.read_only = read_only
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="timeline-store")
        self._connection: sqlite3.Connection | None = None
        self._lock: ProjectWriterLock | None = None
        self._closing = False
        self._closed = False
        self._close_future: asyncio.Future[None] | None = None

    @classmethod
    async def open(cls, project: Path, *, read_only: bool = False) -> SqliteTimelineStore:
        store = cls(project, read_only=read_only)
        try:
            await store._call(store._open)
        except BaseException:
            await store.close()
            raise
        return store

    async def _call[T](self, operation: Callable[[], T]) -> T:
        if self._closing or self._closed:
            raise _error("storage.closed")
        future = asyncio.wrap_future(self._executor.submit(self._safe, operation))
        # Cancellation stops the caller, not a half-committed SQLite transaction.
        future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        return await asyncio.shield(future)

    @staticmethod
    def _safe[T](operation: Callable[[], T]) -> T:
        try:
            return operation()
        except sqlite3.IntegrityError as error:
            raise _error("storage.constraint") from error
        except sqlite3.Error as error:
            raise _error("storage.database") from error
        except OSError as error:
            raise _error("storage.io") from error
        except (ValueError, KeyError, TypeError, ArithmeticError, AttributeError) as error:
            raise _error("storage.invalid") from error

    def _open(self) -> None:
        database = self.project / "timeline.sqlite3"
        if not self.read_only:
            self.project.mkdir(parents=True, exist_ok=True)
            self._lock = ProjectWriterLock(self.project)
            self._lock.acquire()
        connection = sqlite3.connect(
            database.as_uri() + "?mode=ro" if self.read_only else str(database),
            uri=self.read_only,
            timeout=1.0,
            autocommit=True,
        )
        self._connection = connection
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=1000")
        if self.read_only:
            connection.execute("PRAGMA query_only=ON")
            validate_schema(connection)
        else:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            migrate(connection)

    @property
    def _db(self) -> sqlite3.Connection:
        if self._connection is None:
            raise _error("storage.closed")
        return self._connection

    def _writer(self) -> None:
        if self.read_only:
            raise _error("storage.read_only")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._writer()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def _run_row(self, run_id: str) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM analysis_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise _error("storage.run_missing")
        return cast(sqlite3.Row, row)

    def _load_run(self, run_id: str) -> StoredRun:
        try:
            return self._decode_run(run_id)
        except (ValueError, KeyError, TypeError, ArithmeticError, AttributeError) as error:
            raise _error("storage.integrity") from error

    def _decode_run(self, run_id: str) -> StoredRun:
        row = self._run_row(run_id)
        media = self._db.execute(
            "SELECT * FROM media_assets WHERE media_id=?", (row["media_id"],)
        ).fetchone()
        data = _object(row["config_json"])
        config = RunConfiguration(
            AnalysisConfig(**data["analysis"]),
            Decimal(data["max_cost_cny"]),
            row["pipeline_version"],
            row["pipeline_hash"],
            tuple(json.loads(row["required_stages_json"])),
        )
        if (
            hashlib.sha256(row["config_json"].encode()).hexdigest() != row["config_hash"]
            or _config_json(config) != row["config_json"]
        ):
            raise _error("storage.integrity")
        asset = _asset(media["payload_json"])
        if (
            asset.media_id != media["media_id"]
            or asset.sha256 != media["content_hash"]
            or str(asset.source_path) != media["source_path"]
            or asset.duration_us != media["duration_us"]
        ):
            raise _error("storage.integrity")
        return StoredRun(
            run_id,
            asset,
            config,
            row["config_hash"],
            RunStatus(row["status"]),
            row["error_code"],
        )

    async def load_run(self, run_id: str) -> StoredRun:
        return await self._call(lambda: self._load_run(run_id))

    async def list_runs(self) -> tuple[tuple[str, str], ...]:
        def load() -> tuple[tuple[str, str], ...]:
            return tuple(
                (row["run_id"], row["status"])
                for row in self._db.execute(
                    "SELECT run_id, status FROM analysis_runs ORDER BY run_id"
                )
            )

        return await self._call(load)

    async def load_evidence_reference(
        self, run_id: str, evidence_id: str
    ) -> EvidenceReference | None:
        """Read one registered reference; the media reader must verify its bytes.

        This avoids scanning the entire video for each thumbnail. It does not
        replace load_timeline's complete integrity validation.
        """

        def load() -> EvidenceReference | None:
            run = self._load_run(run_id)
            if not evidence_id or len(evidence_id) > 512:
                return None
            row = self._db.execute(
                "SELECT * FROM evidence WHERE run_id=? AND evidence_id=?",
                (run_id, evidence_id),
            ).fetchone()
            if row is None:
                return None
            if row["media_id"] != run.asset.media_id:
                raise _error("storage.integrity")
            return EvidenceReference(
                row["evidence_id"],
                run.asset.media_id,
                row["kind"],
                SourceInstant(row["start_us"], run.asset.duration_us)
                if row["kind"] == "image"
                else SourceRange(row["start_us"], row["end_us"], run.asset.duration_us),
                self._stored_artifact(run_id, row["artifact_path"]),
                row["content_hash"],
                row["transform_version"],
            )

        return await self._call(load)

    async def persist_search(
        self,
        result: SearchResult,
        document: dict[str, object],
        *,
        elapsed_ms: int,
        top_k: int,
        embedding_space: EmbeddingSpace | None = None,
    ) -> str:
        """Append retrieval provenance without changing immutable analysis results."""

        def persist() -> str:
            self._writer()
            self._consistent(result.run_id)
            hits = tuple(
                PersistedRetrievalHit(
                    rank,
                    item.candidate_id,
                    item.event_id,
                    item.source_range.start_us,
                    item.source_range.end_us,
                    item.score,
                    item.score_kind,
                    item.evidence_ids,
                )
                for rank, item in enumerate(result.candidates, 1)
            )
            with self._transaction():
                for embedding in result.event_embeddings:
                    persist_embedding(self._db, result.run_id, embedding)
                return persist_retrieval(
                    self._db,
                    result.run_id,
                    query=result.query,
                    retrieval_version=result.retrieval_version,
                    parameters={
                        "mode": result.mode,
                        "topK": top_k,
                        "minSimilarity": result.min_similarity,
                        "minSemanticMargin": result.min_semantic_margin,
                        "abstentionReason": result.abstention_reason,
                    },
                    elapsed_ms=elapsed_ms,
                    hits=hits,
                    result_json=document,
                    embedding_space=embedding_space,
                )

        return await self._call(persist)

    async def load_retrieval(self, retrieval_id: str) -> dict[str, object]:
        return await self._call(lambda: read_retrieval(self._db, retrieval_id))

    async def load_checkpoints(self, run_id: str) -> tuple[StageCheckpoint, ...]:
        def load() -> tuple[StageCheckpoint, ...]:
            self._run_row(run_id)
            return self._checkpoints(run_id)

        return await self._call(load)

    def _mutable(self, run_id: str) -> sqlite3.Row:
        self._writer()
        row = self._run_row(run_id)
        if row["status"] == RunStatus.COMPLETED:
            raise _error("storage.run_immutable")
        if row["error_code"] == "storage.integrity":
            raise _error("storage.integrity")
        return row

    def _running_stage(self, run_id: str, stage_id: str) -> sqlite3.Row:
        run = self._mutable(run_id)
        row = self._db.execute(
            "SELECT * FROM stage_checkpoints WHERE run_id=? AND stage_id=?", (run_id, stage_id)
        ).fetchone()
        if (
            run["status"] != RunStatus.RUNNING
            or row is None
            or row["status"] != StageStatus.RUNNING
        ):
            raise _error("storage.stage_state")
        return cast(sqlite3.Row, row)

    async def create_run(
        self, run_id: str, asset: MediaAsset, configuration: RunConfiguration
    ) -> StoredRun:
        def create() -> StoredRun:
            self._writer()
            _id(run_id)
            _digest(asset.sha256)
            if not asset.media_id or _hash(asset.source_path) != asset.sha256:
                raise _error("storage.integrity")
            payload = _asset_json(asset)
            config = _config_json(configuration)
            with self._transaction():
                previous = self._db.execute(
                    "SELECT payload_json FROM media_assets WHERE media_id=?", (asset.media_id,)
                ).fetchone()
                if previous is not None and previous[0] != payload:
                    raise _error("storage.media_conflict")
                if previous is None:
                    self._db.execute(
                        "INSERT INTO media_assets VALUES (?,?,?,?,?)",
                        (
                            asset.media_id,
                            asset.sha256,
                            str(asset.source_path.resolve()),
                            asset.duration_us,
                            payload,
                        ),
                    )
                timestamp = _now()
                self._db.execute(
                    "INSERT INTO analysis_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        asset.media_id,
                        config,
                        hashlib.sha256(config.encode()).hexdigest(),
                        configuration.pipeline_version,
                        configuration.pipeline_hash,
                        _json(configuration.required_stages),
                        str(RunStatus.PENDING),
                        None,
                        timestamp,
                        timestamp,
                        None,
                        None,
                    ),
                )
            return self._load_run(run_id)

        return await self._call(create)

    async def begin_stage(self, run_id: str, stage_id: str, input_hash: str) -> None:
        def begin() -> None:
            self._mutable(run_id)
            _id(stage_id)
            _digest(input_hash)
            previous = self._db.execute(
                "SELECT * FROM stage_checkpoints WHERE run_id=? AND stage_id=?", (run_id, stage_id)
            ).fetchone()
            if previous is not None and previous["status"] in (
                StageStatus.RUNNING,
                StageStatus.COMPLETED,
            ):
                raise _error("storage.stage_state")
            # A resume uses the original stage inputs and version snapshot.
            if previous is not None and previous["input_hash"] != input_hash:
                raise _error("storage.resume_mismatch")
            if self._db.execute(
                "SELECT 1 FROM provider_invocations WHERE run_id=? AND stage_id=? AND status='running'",
                (run_id, stage_id),
            ).fetchone():
                raise _error("storage.stage_state")
            attempt = 1 if previous is None else previous["attempt"] + 1
            with self._transaction():
                self._db.execute(
                    "INSERT INTO stage_checkpoints VALUES (?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(run_id,stage_id) DO UPDATE SET status=excluded.status, "
                    "output_hash=NULL,attempt=excluded.attempt,error_code=NULL,updated_at=excluded.updated_at",
                    (
                        run_id,
                        stage_id,
                        str(StageStatus.RUNNING),
                        input_hash,
                        None,
                        attempt,
                        None,
                        _now(),
                    ),
                )
                self._db.execute(
                    "UPDATE analysis_runs SET status='running',error_code=NULL,updated_at=? WHERE run_id=?",
                    (_now(), run_id),
                )

        await self._call(begin)

    def _relative_artifact(self, run_id: str, path: Path) -> str:
        resolved = path.resolve(strict=True)
        run_directory = (self.project / "runs" / _id(run_id)).resolve()
        if not run_directory.is_relative_to(self.project) or not resolved.is_relative_to(
            run_directory
        ):
            raise _error("storage.artifact_path")
        if not resolved.is_file():
            raise _error("storage.artifact_path")
        return resolved.relative_to(self.project).as_posix()

    def _stored_artifact(self, run_id: str, path: str) -> Path:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            raise _error("storage.artifact_path")
        resolved = (self.project / relative).resolve()
        run_directory = (self.project / "runs" / _id(run_id)).resolve()
        if not run_directory.is_relative_to(self.project) or not resolved.is_relative_to(
            run_directory
        ):
            raise _error("storage.artifact_path")
        return resolved

    def _finish_stage(
        self,
        run_id: str,
        stage_id: str,
        status: StageStatus,
        output_hash: str | None,
        error_code: str | None,
    ) -> None:
        self._running_stage(run_id, stage_id)
        if not isinstance(status, StageStatus) or status == StageStatus.RUNNING:
            raise _error("storage.stage_state")
        if status == StageStatus.COMPLETED:
            if output_hash is None or error_code is not None:
                raise _error("storage.stage_state")
            _digest(output_hash)
        elif output_hash is not None or not error_code:
            raise _error("storage.stage_state")
        if self._db.execute(
            "SELECT 1 FROM provider_invocations WHERE run_id=? AND stage_id=? AND status='running'",
            (run_id, stage_id),
        ).fetchone():
            raise _error("storage.invocation_pending")
        self._db.execute(
            "UPDATE stage_checkpoints SET status=?,output_hash=?,error_code=?,updated_at=? "
            "WHERE run_id=? AND stage_id=?",
            (str(status), output_hash, error_code, _now(), run_id, stage_id),
        )

    async def finish_stage(
        self,
        run_id: str,
        stage_id: str,
        status: StageStatus,
        output_hash: str | None = None,
        error_code: str | None = None,
    ) -> None:
        def finish() -> None:
            with self._transaction():
                self._finish_stage(run_id, stage_id, status, output_hash, error_code)

        await self._call(finish)

    async def persist_media_bundle(
        self, run_id: str, bundle: MediaPreprocessingResult, stage_id: str = "media"
    ) -> None:
        def persist() -> None:
            self._running_stage(run_id, stage_id)
            run = self._load_run(run_id)
            if _asset_json(run.asset) != _asset_json(bundle.asset):
                raise _error("storage.media_conflict")
            manifest_path = self._relative_artifact(run_id, bundle.manifest_path)
            manifest_hash = _hash(bundle.manifest_path)
            manifest = _object(bundle.manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("schemaVersion") != 1
                or manifest.get("status") != "completed"
                or manifest.get("media") != _object(_asset_json(bundle.asset))
                or manifest.get("transformVersion") != bundle.transform_version
                or manifest.get("processorVersion") != bundle.processor_version
                or len(manifest.get("images", [])) != len(bundle.images)
            ):
                raise _error("storage.manifest")
            records: list[tuple[object, ...]] = []
            for image, metadata in zip(bundle.images, manifest["images"], strict=True):
                if (
                    metadata["evidenceId"] != image.evidence_id
                    or metadata["path"] != image.path.name
                    or metadata["sha256"] != image.sha256
                    or metadata["pts"] != image.pts
                    or _fraction(metadata["timeBase"]) != image.time_base
                    or metadata["sourceUs"] != image.source_time.time_us
                    or image.source_time.duration_us != run.asset.duration_us
                    or run.asset.instant(image.pts, image.time_base) != image.source_time
                ):
                    raise _error("storage.manifest")
                path = self._relative_artifact(run_id, image.path)
                if image.path.resolve().parent != bundle.manifest_path.resolve().parent:
                    raise _error("storage.manifest")
                if _hash(image.path) != _digest(image.sha256):
                    raise _error("storage.integrity")
                records.append(
                    (
                        image.evidence_id,
                        run_id,
                        run.asset.media_id,
                        stage_id,
                        "image",
                        image.source_time.time_us,
                        None,
                        path,
                        image.sha256,
                        bundle.transform_version,
                        _json(metadata),
                    )
                )
            audio = bundle.audio
            metadata = manifest.get("audio")
            if audio is None:
                if metadata is not None:
                    raise _error("storage.manifest")
            else:
                mapping = audio.map_interval(0, audio.sample_count, run.asset)
                coverage = mapping.source_range
                if (
                    not isinstance(metadata, dict)
                    or metadata["evidenceId"] != audio.evidence_id
                    or metadata["path"] != audio.path.name
                    or metadata["sha256"] != audio.sha256
                    or metadata["sampleRate"] != audio.sample_rate
                    or metadata["sampleCount"] != audio.sample_count
                    or metadata["trimEndPts"] != audio.trim_end_pts
                    or metadata["decodedSampleCount"] != audio.decoded_sample_count
                    or metadata["coverage"]["startUs"] != coverage.start_us
                    or metadata["coverage"]["endUs"] != coverage.end_us
                    or metadata["discontinuityOffsets"] != list(audio.discontinuity_offsets)
                    or metadata["boundaryToleranceSamples"] != 1
                    or _fraction(metadata["coverage"]["clampedStartSeconds"])
                    != mapping.clamped_start_seconds
                    or _fraction(metadata["coverage"]["clampedEndSeconds"])
                    != mapping.clamped_end_seconds
                    or metadata["samplesBeyondDeclaredEndRemoved"]
                    != (
                        None
                        if audio.decoded_sample_count is None
                        else audio.decoded_sample_count - audio.sample_count
                    )
                    or len(metadata["frames"]) != len(audio.frames)
                ):
                    raise _error("storage.manifest")
                for frame, saved in zip(audio.frames, metadata["frames"], strict=True):
                    if (
                        saved["sampleOffset"] != frame.sample_offset
                        or saved["sampleCount"] != frame.sample_count
                        or saved["pts"] != frame.pts
                        or _fraction(saved["timeBase"]) != frame.time_base
                    ):
                        raise _error("storage.manifest")
                path = self._relative_artifact(run_id, audio.path)
                if audio.path.resolve().parent != bundle.manifest_path.resolve().parent:
                    raise _error("storage.manifest")
                if _hash(audio.path) != _digest(audio.sha256):
                    raise _error("storage.integrity")
                records.append(
                    (
                        audio.evidence_id,
                        run_id,
                        run.asset.media_id,
                        stage_id,
                        "audio",
                        coverage.start_us,
                        coverage.end_us,
                        path,
                        audio.sha256,
                        bundle.transform_version,
                        _json({"manifestPath": manifest_path, "manifestHash": manifest_hash}),
                    )
                )
            if _hash(run.asset.source_path) != run.asset.sha256:
                raise _error("storage.integrity")
            with self._transaction():
                self._db.executemany("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)", records)
                self._db.execute(
                    "UPDATE analysis_runs SET manifest_path=?,manifest_hash=?,updated_at=? WHERE run_id=?",
                    (manifest_path, manifest_hash, _now(), run_id),
                )
                self._finish_stage(run_id, stage_id, StageStatus.COMPLETED, manifest_hash, None)

        await self._call(persist)

    async def load_media_bundle(
        self, run_id: str, stage_id: str = "media"
    ) -> MediaPreprocessingResult:
        def load() -> MediaPreprocessingResult:
            row = self._run_row(run_id)
            checkpoint = self._db.execute(
                "SELECT * FROM stage_checkpoints WHERE run_id=? AND stage_id=?", (run_id, stage_id)
            ).fetchone()
            if (
                checkpoint is None
                or checkpoint["status"] != StageStatus.COMPLETED
                or row["manifest_path"] is None
                or checkpoint["output_hash"] != row["manifest_hash"]
            ):
                raise _error("storage.stage_state")
            if row["error_code"] == "storage.integrity" or self._integrity(run_id):
                raise _error("storage.integrity")
            asset = self._load_run(run_id).asset
            path = self._stored_artifact(run_id, row["manifest_path"])
            data = _object(path.read_text(encoding="utf-8"))

            def artifact(name: str) -> Path:
                if Path(name).name != name:
                    raise _error("storage.manifest")
                return self._stored_artifact(
                    run_id, (path.parent / name).relative_to(self.project).as_posix()
                )

            images = tuple(
                VisualEvidence(
                    image["evidenceId"],
                    artifact(image["path"]),
                    image["sha256"],
                    image["pts"],
                    _fraction(image["timeBase"]),
                    SourceInstant(image["sourceUs"], asset.duration_us),
                )
                for image in data["images"]
            )
            audio_data = data["audio"]
            audio = (
                None
                if audio_data is None
                else AudioEvidence(
                    audio_data["evidenceId"],
                    artifact(audio_data["path"]),
                    audio_data["sha256"],
                    audio_data["sampleRate"],
                    audio_data["sampleCount"],
                    tuple(
                        AudioFrameMapping(
                            frame["sampleOffset"],
                            frame["sampleCount"],
                            frame["pts"],
                            _fraction(frame["timeBase"]),
                        )
                        for frame in audio_data["frames"]
                    ),
                    audio_data["trimEndPts"],
                    audio_data["decodedSampleCount"],
                )
            )
            return MediaPreprocessingResult(
                asset, images, audio, path, data["transformVersion"], data["processorVersion"]
            )

        return await self._call(load)

    async def persist_timeline(
        self,
        run_id: str,
        stage_id: str,
        events: tuple[SemanticEvent, ...],
        transcripts: tuple[TranscriptSegment, ...],
        output_hash: str,
    ) -> None:
        def persist() -> None:
            self._running_stage(run_id, stage_id)
            run = self._load_run(run_id)
            with self._transaction():
                for event in events:
                    if (
                        event.run_id != run_id
                        or event.media_id != run.asset.media_id
                        or event.source_range.duration_us != run.asset.duration_us
                        or not event.evidence_ids
                        or len(set(event.evidence_ids)) != len(event.evidence_ids)
                    ):
                        raise _error("storage.invalid_event")
                    self._db.execute(
                        "INSERT INTO semantic_events VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            event.event_id,
                            run_id,
                            event.media_id,
                            stage_id,
                            event.source_range.start_us,
                            event.source_range.end_us,
                            _json(event.observable_facts),
                            _json(event.mechanic_tags),
                            event.modality,
                            event.uncertainty,
                        ),
                    )
                    self._db.executemany(
                        "INSERT INTO event_evidence VALUES (?,?,?,?)",
                        (
                            (event.event_id, evidence_id, run_id, event.media_id)
                            for evidence_id in event.evidence_ids
                        ),
                    )
                for index, segment in enumerate(transcripts):
                    if (
                        segment.media_id != run.asset.media_id
                        or segment.source_range.duration_us != run.asset.duration_us
                    ):
                        raise _error("storage.invalid_transcript")
                    self._db.execute(
                        "INSERT INTO transcript_segments VALUES (?,?,?,?,?,?,?,?)",
                        (
                            f"{run_id}:{stage_id}:{index:08d}",
                            run_id,
                            segment.media_id,
                            stage_id,
                            segment.source_range.start_us,
                            segment.source_range.end_us,
                            segment.text,
                            segment.uncertainty,
                        ),
                    )
                self._finish_stage(run_id, stage_id, StageStatus.COMPLETED, output_hash, None)

        await self._call(persist)

    async def begin_invocation(
        self,
        invocation_id: str,
        run_id: str,
        stage_id: str,
        logical_request_id: str,
        metadata: InvocationMetadata,
    ) -> None:
        def begin() -> None:
            self._running_stage(run_id, stage_id)
            if not invocation_id.strip() or not logical_request_id.strip():
                raise _error("storage.invalid_invocation")
            if metadata.usage != ProviderUsage() or metadata.elapsed_ms is not None:
                raise _error("storage.invalid_invocation")
            payload = _metadata_json(metadata)
            with self._transaction():
                self._db.execute(
                    "INSERT INTO provider_invocations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        invocation_id,
                        run_id,
                        stage_id,
                        logical_request_id,
                        metadata.attempt,
                        "running",
                        payload,
                        *_usage_values(metadata.usage),
                        None,
                        _now(),
                        None,
                    ),
                )

        await self._call(begin)

    async def finish_invocation(
        self,
        invocation_id: str,
        status: InvocationStatus,
        metadata: InvocationMetadata,
        error_code: str | None = None,
    ) -> None:
        def finish() -> None:
            self._writer()
            row = self._db.execute(
                "SELECT * FROM provider_invocations WHERE invocation_id=?", (invocation_id,)
            ).fetchone()
            if row is None or row["status"] != InvocationStatus.RUNNING:
                raise _error("storage.invocation_state")
            self._running_stage(row["run_id"], row["stage_id"])
            before = _object(row["metadata_json"])
            payload = _metadata_json(metadata)
            after = _object(payload)
            immutable = (
                "provider",
                "requested_model",
                "prompt_version",
                "schema_version",
                "attempt",
                "model_revision",
                "price_version",
            )
            if any(before[key] != after[key] for key in immutable):
                raise _error("storage.invocation_identity")
            if before["provider"] == "deepseek":
                old_details = _object(before["execution_details"] or "{}")
                new_details = _object(after["execution_details"] or "{}")
                if any(
                    old_details.get(key) != new_details.get(key)
                    for key in ("reservationCny", "inputFrames", "evidenceIds")
                ):
                    raise _error("storage.invocation_identity")
            if not isinstance(status, InvocationStatus) or status == InvocationStatus.RUNNING:
                raise _error("storage.invocation_state")
            failed = status in (
                InvocationStatus.FAILED,
                InvocationStatus.CANCELLED,
                InvocationStatus.INTERRUPTED,
            )
            if failed != bool(error_code):
                raise _error("storage.invocation_state")
            with self._transaction():
                self._db.execute(
                    "UPDATE provider_invocations SET status=?,metadata_json=?,input_tokens=?,output_tokens=?,"
                    "cached_input_tokens=?,original_cost=?,currency=?,cost_cny=?,cost_status=?,error_code=?,finished_at=? "
                    "WHERE invocation_id=?",
                    (
                        str(status),
                        payload,
                        *_usage_values(metadata.usage),
                        error_code,
                        _now(),
                        invocation_id,
                    ),
                )

        await self._call(finish)

    def _invocations(self, run_id: str) -> tuple[StoredInvocation, ...]:
        self._run_row(run_id)
        results = []
        for row in self._db.execute(
            "SELECT * FROM provider_invocations WHERE run_id=? ORDER BY started_at,invocation_id",
            (run_id,),
        ):
            metadata = _object(row["metadata_json"])
            usage = ProviderUsage(
                row["input_tokens"],
                row["output_tokens"],
                row["cached_input_tokens"],
                None if row["original_cost"] is None else Decimal(row["original_cost"]),
                row["currency"],
                None if row["cost_cny"] is None else Decimal(row["cost_cny"]),
                CostStatus(row["cost_status"]),
            )
            results.append(
                StoredInvocation(
                    row["invocation_id"],
                    run_id,
                    row["stage_id"],
                    row["logical_request_id"],
                    InvocationStatus(row["status"]),
                    InvocationMetadata(**metadata, usage=usage),
                    row["error_code"],
                )
            )
        return tuple(results)

    async def load_invocations(self, run_id: str) -> tuple[StoredInvocation, ...]:
        return await self._call(lambda: self._invocations(run_id))

    def _checkpoints(self, run_id: str) -> tuple[StageCheckpoint, ...]:
        return tuple(
            StageCheckpoint(
                run_id,
                row["stage_id"],
                StageStatus(row["status"]),
                row["input_hash"],
                row["output_hash"],
                row["attempt"],
                row["error_code"],
            )
            for row in self._db.execute(
                "SELECT * FROM stage_checkpoints WHERE run_id=? ORDER BY stage_id", (run_id,)
            )
        )

    def _integrity(self, run_id: str) -> tuple[IntegrityIssue, ...]:
        row = self._run_row(run_id)
        try:
            asset = self._load_run(run_id).asset
        except (AppError, ValueError, KeyError, TypeError, ArithmeticError, AttributeError):
            return (IntegrityIssue(run_id, "storage.integrity", self.project / "timeline.sqlite3"),)
        issues = []
        items: list[tuple[Path, str, str]] = [
            (asset.source_path, asset.sha256, "storage.source_integrity")
        ]
        if row["manifest_path"] is not None:
            try:
                items.append(
                    (
                        self._stored_artifact(run_id, row["manifest_path"]),
                        row["manifest_hash"],
                        "storage.artifact_integrity",
                    )
                )
            except AppError:
                issues.append(
                    IntegrityIssue(
                        run_id, "storage.artifact_path", self.project / row["manifest_path"]
                    )
                )
        for evidence in self._db.execute("SELECT * FROM evidence WHERE run_id=?", (run_id,)):
            try:
                items.append(
                    (
                        self._stored_artifact(run_id, evidence["artifact_path"]),
                        evidence["content_hash"],
                        "storage.artifact_integrity",
                    )
                )
            except AppError:
                issues.append(
                    IntegrityIssue(
                        run_id, "storage.artifact_path", self.project / evidence["artifact_path"]
                    )
                )
        for path, expected, code in items:
            try:
                valid = _hash(path) == expected
            except OSError:
                valid = False
            if not valid:
                issues.append(IntegrityIssue(run_id, code, path))
        return tuple(issues)

    def _consistent(self, run_id: str) -> None:
        row = self._run_row(run_id)
        checkpoints = self._checkpoints(run_id)
        completed = {
            checkpoint.stage_id
            for checkpoint in checkpoints
            if checkpoint.status == StageStatus.COMPLETED
        }
        if (
            row["manifest_path"] is None
            or not set(json.loads(row["required_stages_json"])).issubset(completed)
            or any(checkpoint.status != StageStatus.COMPLETED for checkpoint in checkpoints)
            or self._db.execute(
                "SELECT 1 FROM provider_invocations WHERE run_id=? AND status='running'", (run_id,)
            ).fetchone()
        ):
            raise _error("storage.run_incomplete")
        if self._db.execute(
            "SELECT 1 FROM semantic_events e WHERE e.run_id=? AND NOT EXISTS "
            "(SELECT 1 FROM event_evidence l WHERE l.event_id=e.event_id) LIMIT 1",
            (run_id,),
        ).fetchone():
            raise _error("storage.invalid_event")
        if self._db.execute("PRAGMA foreign_key_check").fetchone() is not None or self._integrity(
            run_id
        ):
            raise _error("storage.integrity")

    async def complete_run(self, run_id: str) -> None:
        def complete() -> None:
            self._mutable(run_id)
            if self._run_row(run_id)["status"] != RunStatus.RUNNING:
                raise _error("storage.run_state")
            self._consistent(run_id)
            with self._transaction():
                self._db.execute(
                    "UPDATE analysis_runs SET status='completed',error_code=NULL,updated_at=? WHERE run_id=?",
                    (_now(), run_id),
                )

        await self._call(complete)

    async def stop_run(self, run_id: str, status: RunStatus, error_code: str | None) -> None:
        def stop() -> None:
            self._mutable(run_id)
            if (
                status not in (RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.INTERRUPTED)
                or not error_code
            ):
                raise _error("storage.run_state")
            with self._transaction():
                self._db.execute(
                    "UPDATE stage_checkpoints SET status=?,error_code=?,updated_at=? WHERE run_id=? AND status='running'",
                    (str(status), error_code, _now(), run_id),
                )
                self._db.execute(
                    "UPDATE provider_invocations SET status='interrupted',error_code='storage.interrupted',finished_at=? WHERE run_id=? AND status='running'",
                    (_now(), run_id),
                )
                self._db.execute(
                    "UPDATE analysis_runs SET status=?,error_code=?,updated_at=? WHERE run_id=?",
                    (str(status), error_code, _now(), run_id),
                )

        await self._call(stop)

    async def load_completed_timeline(self, run_id: str) -> StoredTimeline:
        return await self.load_timeline(run_id)

    async def prepare_resume(self, run_id: str) -> None:
        """Explicitly reopen one run after taking the project writer lock; never replay requests."""

        def prepare() -> None:
            self._mutable(run_id)
            if self._integrity(run_id):
                raise _error("storage.integrity")
            with self._transaction():
                self._db.execute(
                    "UPDATE stage_checkpoints SET status='interrupted',updated_at=? "
                    "WHERE run_id=? AND status='running'",
                    (_now(), run_id),
                )
                self._db.execute(
                    "UPDATE provider_invocations SET status='interrupted',error_code='storage.interrupted',finished_at=? "
                    "WHERE run_id=? AND status='running'",
                    (_now(), run_id),
                )
                self._db.execute(
                    "UPDATE analysis_runs SET status='running',error_code=NULL,updated_at=? WHERE run_id=?",
                    (_now(), run_id),
                )

        await self._call(prepare)

    async def load_timeline(self, run_id: str, *, require_completed: bool = True) -> StoredTimeline:
        def load() -> StoredTimeline:
            run = self._load_run(run_id)
            if require_completed and run.status != RunStatus.COMPLETED:
                raise _error("storage.run_incomplete")
            if require_completed:
                self._consistent(run_id)
            elif self._integrity(run_id):
                raise _error("storage.integrity")
            duration = run.asset.duration_us
            evidence = tuple(
                EvidenceReference(
                    row["evidence_id"],
                    run.asset.media_id,
                    row["kind"],
                    SourceInstant(row["start_us"], duration)
                    if row["kind"] == "image"
                    else SourceRange(row["start_us"], row["end_us"], duration),
                    self._stored_artifact(run_id, row["artifact_path"]),
                    row["content_hash"],
                    row["transform_version"],
                )
                for row in self._db.execute(
                    "SELECT * FROM evidence WHERE run_id=? ORDER BY start_us,evidence_id", (run_id,)
                )
            )
            transcripts = tuple(
                TranscriptSegment(
                    run.asset.media_id,
                    SourceRange(row["start_us"], row["end_us"], duration),
                    row["text"],
                    row["uncertainty"],
                )
                for row in self._db.execute(
                    "SELECT * FROM transcript_segments WHERE run_id=? ORDER BY start_us,segment_id",
                    (run_id,),
                )
            )
            events = tuple(
                SemanticEvent(
                    row["event_id"],
                    run.asset.media_id,
                    run_id,
                    SourceRange(row["start_us"], row["end_us"], duration),
                    tuple(json.loads(row["observable_facts_json"])),
                    tuple(json.loads(row["mechanic_tags_json"])),
                    tuple(
                        link[0]
                        for link in self._db.execute(
                            "SELECT evidence_id FROM event_evidence WHERE event_id=? ORDER BY evidence_id",
                            (row["event_id"],),
                        )
                    ),
                    row["modality"],
                    row["uncertainty"],
                )
                for row in self._db.execute(
                    "SELECT * FROM semantic_events WHERE run_id=? ORDER BY start_us,event_id",
                    (run_id,),
                )
            )
            return StoredTimeline(
                run,
                self._checkpoints(run_id),
                evidence,
                transcripts,
                events,
                self._invocations(run_id),
            )

        return await self._call(load)

    async def recover(self) -> RecoveryReport:
        def recover() -> RecoveryReport:
            self._writer()
            runs = tuple(
                row[0]
                for row in self._db.execute(
                    "SELECT run_id FROM analysis_runs WHERE status='running' ORDER BY run_id"
                )
            )
            stages = tuple(
                (row[0], row[1])
                for row in self._db.execute(
                    "SELECT run_id,stage_id FROM stage_checkpoints WHERE status='running' ORDER BY run_id,stage_id"
                )
            )
            invocations = tuple(
                row[0]
                for row in self._db.execute(
                    "SELECT invocation_id FROM provider_invocations WHERE status='running' ORDER BY invocation_id"
                )
            )
            all_runs = tuple(
                row[0]
                for row in self._db.execute("SELECT run_id FROM analysis_runs ORDER BY run_id")
            )
            issues = tuple(issue for run_id in all_runs for issue in self._integrity(run_id))
            referenced = set()
            for run_id in all_runs:
                row = self._run_row(run_id)
                if row["manifest_path"]:
                    try:
                        referenced.add(self._stored_artifact(run_id, row["manifest_path"]))
                    except AppError:
                        pass  # Already included in the integrity report; do not abort other runs.
                for evidence in self._db.execute(
                    "SELECT artifact_path FROM evidence WHERE run_id=?", (run_id,)
                ):
                    try:
                        referenced.add(self._stored_artifact(run_id, evidence[0]))
                    except AppError:
                        pass
            orphans, temporary = [], []
            artifact_directory = self.project / "runs"
            if artifact_directory.is_symlink() or artifact_directory.is_junction():
                issues += (IntegrityIssue("", "storage.artifact_path", artifact_directory),)
            elif artifact_directory.exists():
                # Prune directory links explicitly, including Windows junctions.
                for directory, subdirectories, filenames in artifact_directory.walk(
                    follow_symlinks=False
                ):
                    subdirectories[:] = [
                        name
                        for name in subdirectories
                        if not (directory / name).is_junction()
                        and not (directory / name).is_symlink()
                    ]
                    for name in filenames:
                        path = directory / name
                        if (
                            path.is_symlink()
                            or not path.is_file()
                            or not path.resolve().is_relative_to(self.project)
                        ):
                            continue
                        if path.suffix in (".tmp", ".partial"):
                            temporary.append(path)
                        elif path.resolve() not in referenced:
                            orphans.append(path)
            with self._transaction():
                timestamp = _now()
                self._db.execute(
                    "UPDATE stage_checkpoints SET status='interrupted',error_code='storage.interrupted',updated_at=? WHERE status='running'",
                    (timestamp,),
                )
                self._db.execute(
                    "UPDATE provider_invocations SET status='interrupted',error_code='storage.interrupted',finished_at=? WHERE status='running'",
                    (timestamp,),
                )
                self._db.execute(
                    "UPDATE analysis_runs SET status='interrupted',error_code='storage.interrupted',updated_at=? WHERE status='running'",
                    (timestamp,),
                )
                self._db.executemany(
                    "UPDATE analysis_runs SET status='failed',error_code='storage.integrity',updated_at=? WHERE run_id=?",
                    ((timestamp, run_id) for run_id in {issue.run_id for issue in issues}),
                )
            return RecoveryReport(
                runs, stages, invocations, issues, tuple(sorted(orphans)), tuple(sorted(temporary))
            )

        return await self._call(recover)

    async def close(self) -> None:
        if self._closed:
            return

        def close_connection() -> None:
            try:
                if self._connection is not None:
                    self._connection.close()
                    self._connection = None
            finally:
                if self._lock is not None:
                    self._lock.close()
                    self._lock = None

        if self._close_future is None:
            self._closing = True
            self._close_future = asyncio.wrap_future(self._executor.submit(close_connection))

            def drained(future: asyncio.Future[None]) -> None:
                self._executor.shutdown(wait=False, cancel_futures=False)
                self._closed = True
                if not future.cancelled():
                    future.exception()

            self._close_future.add_done_callback(drained)
        # Concurrent close calls share the same drain; cancellation never blocks the loop.
        await asyncio.shield(self._close_future)
