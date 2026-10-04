"""Versioned SQLite schema; migrations are atomic and never repair unknown databases."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime

from gamingcreator.domain.errors import AppError, ExitCode

SCHEMA_VERSION = 3

_TABLES = (
    """CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY CHECK(version > 0),
        applied_at TEXT NOT NULL
    ) STRICT""",
    """CREATE TABLE media_assets (
        media_id TEXT PRIMARY KEY NOT NULL,
        content_hash TEXT UNIQUE NOT NULL,
        source_path TEXT NOT NULL,
        duration_us INTEGER NOT NULL CHECK(duration_us > 0),
        payload_json TEXT NOT NULL CHECK(json_valid(payload_json))
    ) STRICT""",
    """CREATE TABLE analysis_runs (
        run_id TEXT PRIMARY KEY NOT NULL,
        media_id TEXT NOT NULL REFERENCES media_assets(media_id),
        config_json TEXT NOT NULL CHECK(json_valid(config_json)),
        config_hash TEXT NOT NULL,
        pipeline_version TEXT NOT NULL,
        pipeline_hash TEXT NOT NULL,
        required_stages_json TEXT NOT NULL CHECK(json_valid(required_stages_json)),
        status TEXT NOT NULL CHECK(status IN
            ('pending','running','completed','failed','cancelled','interrupted')),
        error_code TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        manifest_path TEXT,
        manifest_hash TEXT,
        UNIQUE(run_id, media_id),
        CHECK((manifest_path IS NULL) = (manifest_hash IS NULL))
    ) STRICT""",
    """CREATE TABLE stage_checkpoints (
        run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
        stage_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN
            ('running','completed','failed','cancelled','interrupted')),
        input_hash TEXT NOT NULL,
        output_hash TEXT,
        attempt INTEGER NOT NULL CHECK(attempt > 0),
        error_code TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(run_id, stage_id)
    ) STRICT""",
    """CREATE TABLE evidence (
        evidence_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        stage_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('image','audio')),
        start_us INTEGER NOT NULL CHECK(start_us >= 0),
        end_us INTEGER,
        artifact_path TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        transform_version TEXT NOT NULL,
        metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
        UNIQUE(evidence_id, run_id, media_id),
        FOREIGN KEY(run_id, media_id) REFERENCES analysis_runs(run_id, media_id),
        FOREIGN KEY(run_id, stage_id) REFERENCES stage_checkpoints(run_id, stage_id),
        CHECK((kind = 'image' AND end_us IS NULL)
            OR (kind = 'audio' AND end_us IS NOT NULL AND end_us > start_us))
    ) STRICT""",
    """CREATE TABLE transcript_segments (
        segment_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        stage_id TEXT NOT NULL,
        start_us INTEGER NOT NULL CHECK(start_us >= 0),
        end_us INTEGER NOT NULL CHECK(end_us > start_us),
        text TEXT NOT NULL,
        FOREIGN KEY(run_id, media_id) REFERENCES analysis_runs(run_id, media_id),
        FOREIGN KEY(run_id, stage_id) REFERENCES stage_checkpoints(run_id, stage_id)
    ) STRICT""",
    """CREATE TABLE semantic_events (
        event_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        stage_id TEXT NOT NULL,
        start_us INTEGER NOT NULL CHECK(start_us >= 0),
        end_us INTEGER NOT NULL CHECK(end_us > start_us),
        observable_facts_json TEXT NOT NULL CHECK(json_valid(observable_facts_json)),
        mechanic_tags_json TEXT NOT NULL CHECK(json_valid(mechanic_tags_json)),
        modality TEXT NOT NULL CHECK(modality IN ('visual','audio','combined')),
        uncertainty TEXT,
        UNIQUE(event_id, run_id, media_id),
        FOREIGN KEY(run_id, media_id) REFERENCES analysis_runs(run_id, media_id),
        FOREIGN KEY(run_id, stage_id) REFERENCES stage_checkpoints(run_id, stage_id)
    ) STRICT""",
    """CREATE TABLE event_evidence (
        event_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        PRIMARY KEY(event_id, evidence_id),
        FOREIGN KEY(event_id, run_id, media_id)
            REFERENCES semantic_events(event_id, run_id, media_id),
        FOREIGN KEY(evidence_id, run_id, media_id)
            REFERENCES evidence(evidence_id, run_id, media_id)
    ) STRICT""",
    """CREATE TABLE provider_invocations (
        invocation_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        stage_id TEXT NOT NULL,
        logical_request_id TEXT NOT NULL,
        attempt INTEGER NOT NULL CHECK(attempt > 0),
        status TEXT NOT NULL CHECK(status IN
            ('running','completed','no_audio','no_speech','failed','cancelled','interrupted')),
        metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
        input_tokens INTEGER CHECK(input_tokens >= 0),
        output_tokens INTEGER CHECK(output_tokens >= 0),
        cached_input_tokens INTEGER CHECK(cached_input_tokens >= 0),
        original_cost TEXT,
        currency TEXT,
        cost_cny TEXT,
        cost_status TEXT NOT NULL CHECK(cost_status IN ('unverified','estimated','confirmed')),
        error_code TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        FOREIGN KEY(run_id, stage_id) REFERENCES stage_checkpoints(run_id, stage_id),
        UNIQUE(run_id, stage_id, logical_request_id, attempt),
        CHECK(cached_input_tokens IS NULL OR input_tokens IS NULL
            OR cached_input_tokens <= input_tokens),
        CHECK(original_cost IS NULL OR currency IS NOT NULL),
        CHECK(original_cost IS NULL OR CASE WHEN json_valid(original_cost)
            THEN json_type(original_cost) IN ('integer','real')
                AND CAST(original_cost AS REAL) >= 0 ELSE 0 END),
        CHECK(cost_cny IS NULL OR CASE WHEN json_valid(cost_cny)
            THEN json_type(cost_cny) IN ('integer','real')
                AND CAST(cost_cny AS REAL) >= 0 ELSE 0 END)
    ) STRICT""",
)

_INDEXES = (
    "CREATE INDEX evidence_by_run ON evidence(run_id, stage_id, start_us)",
    "CREATE INDEX transcripts_by_run ON transcript_segments(run_id, start_us)",
    "CREATE INDEX events_by_run ON semantic_events(run_id, start_us)",
    "CREATE INDEX invocations_by_run ON provider_invocations(run_id, status)",
)


def _range_triggers(table: str, point: bool = False) -> tuple[str, ...]:
    boundary = (
        "NEW.start_us >= (SELECT duration_us FROM media_assets WHERE media_id = NEW.media_id) "
        "OR NEW.end_us > (SELECT duration_us FROM media_assets WHERE media_id = NEW.media_id)"
        if point
        else "NEW.end_us > (SELECT duration_us FROM media_assets WHERE media_id = NEW.media_id)"
    )
    return tuple(
        f"""CREATE TRIGGER {table}_duration_{operation.lower()}
        BEFORE {operation} ON {table} WHEN {boundary}
        BEGIN SELECT RAISE(ABORT, 'source range outside media'); END"""
        for operation in ("INSERT", "UPDATE")
    )


_TRIGGERS = (
    *_range_triggers("evidence", point=True),
    *_range_triggers("transcript_segments"),
    *_range_triggers("semantic_events"),
    """CREATE TRIGGER media_assets_duration_update BEFORE UPDATE OF duration_us ON media_assets
    WHEN EXISTS(SELECT 1 FROM evidence WHERE media_id = NEW.media_id
        AND (start_us >= NEW.duration_us OR end_us > NEW.duration_us))
        OR EXISTS(SELECT 1 FROM transcript_segments WHERE media_id = NEW.media_id
            AND end_us > NEW.duration_us)
        OR EXISTS(SELECT 1 FROM semantic_events WHERE media_id = NEW.media_id
            AND end_us > NEW.duration_us)
    BEGIN SELECT RAISE(ABORT, 'media duration excludes existing records'); END""",
)

_DDL = (*_TABLES, *_INDEXES, *_TRIGGERS)

# Keep v1 immutable: existing databases must validate before this ALTER runs.
_MIGRATION_2 = ("ALTER TABLE transcript_segments ADD COLUMN uncertainty TEXT",)

# Keep both earlier versions immutable. Retrieval never rewrites an analysis run.
_MIGRATION_3 = (
    """CREATE TABLE embeddings (
        embedding_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        subject_kind TEXT NOT NULL CHECK(subject_kind IN ('event','evidence')),
        event_id TEXT,
        evidence_id TEXT,
        provider TEXT NOT NULL CHECK(length(trim(provider)) > 0),
        model TEXT NOT NULL CHECK(length(trim(model)) > 0),
        revision_scope TEXT NOT NULL CHECK(length(trim(revision_scope)) > 0),
        dimension INTEGER NOT NULL CHECK(dimension > 0),
        normalization TEXT NOT NULL CHECK(normalization IN ('none','l2')),
        text_hash TEXT NOT NULL CHECK(length(text_hash) = 64
            AND text_hash NOT GLOB '*[^0-9a-f]*'),
        vector_json TEXT CHECK(vector_json IS NULL OR CASE WHEN json_valid(vector_json)
            THEN json_type(vector_json) = 'array' AND json_array_length(vector_json) = dimension
            ELSE 0 END),
        created_at TEXT NOT NULL,
        UNIQUE(run_id, subject_kind, subject_id, provider, model, revision_scope,
            dimension, normalization, text_hash),
        FOREIGN KEY(run_id, media_id) REFERENCES analysis_runs(run_id, media_id),
        FOREIGN KEY(event_id, run_id, media_id)
            REFERENCES semantic_events(event_id, run_id, media_id),
        FOREIGN KEY(evidence_id, run_id, media_id)
            REFERENCES evidence(evidence_id, run_id, media_id),
        CHECK((subject_kind = 'event' AND event_id IS NOT NULL AND subject_id = event_id
                AND evidence_id IS NULL)
            OR (subject_kind = 'evidence' AND evidence_id IS NOT NULL
                AND subject_id = evidence_id AND event_id IS NULL))
    ) STRICT""",
    """CREATE TABLE retrieval_runs (
        retrieval_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        query TEXT NOT NULL CHECK(length(trim(query)) > 0),
        query_hash TEXT NOT NULL CHECK(length(query_hash) = 64
            AND query_hash NOT GLOB '*[^0-9a-f]*'),
        retrieval_version TEXT NOT NULL CHECK(length(trim(retrieval_version)) > 0),
        parameters_json TEXT NOT NULL CHECK(json_valid(parameters_json)
            AND json_type(parameters_json) = 'object'),
        embedding_space_json TEXT CHECK(embedding_space_json IS NULL
            OR (json_valid(embedding_space_json) AND json_type(embedding_space_json) = 'object')),
        elapsed_ms REAL NOT NULL CHECK(elapsed_ms >= 0 AND elapsed_ms <= 1.7976931348623157e308),
        result_json TEXT NOT NULL CHECK(json_valid(result_json) AND json_type(result_json) = 'object'),
        created_at TEXT NOT NULL,
        UNIQUE(retrieval_id, run_id, media_id),
        FOREIGN KEY(run_id, media_id) REFERENCES analysis_runs(run_id, media_id)
    ) STRICT""",
    """CREATE TABLE retrieval_hits (
        retrieval_id TEXT NOT NULL,
        rank INTEGER NOT NULL CHECK(rank > 0),
        candidate_id TEXT NOT NULL CHECK(length(trim(candidate_id)) > 0),
        event_id TEXT,
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        start_us INTEGER NOT NULL CHECK(start_us >= 0),
        end_us INTEGER NOT NULL CHECK(end_us > start_us),
        score REAL NOT NULL CHECK(abs(score) <= 1.7976931348623157e308),
        score_kind TEXT NOT NULL CHECK(length(trim(score_kind)) > 0),
        PRIMARY KEY(retrieval_id, rank),
        UNIQUE(retrieval_id, candidate_id),
        UNIQUE(retrieval_id, rank, event_id, run_id, media_id),
        UNIQUE(retrieval_id, rank, run_id, media_id),
        FOREIGN KEY(retrieval_id, run_id, media_id)
            REFERENCES retrieval_runs(retrieval_id, run_id, media_id),
        FOREIGN KEY(event_id, run_id, media_id)
            REFERENCES semantic_events(event_id, run_id, media_id)
    ) STRICT""",
    """CREATE TABLE retrieval_hit_evidence (
        retrieval_id TEXT NOT NULL,
        rank INTEGER NOT NULL,
        event_id TEXT,
        evidence_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        PRIMARY KEY(retrieval_id, rank, evidence_id),
        FOREIGN KEY(retrieval_id, rank, event_id, run_id, media_id)
            REFERENCES retrieval_hits(retrieval_id, rank, event_id, run_id, media_id),
        FOREIGN KEY(retrieval_id, rank, run_id, media_id)
            REFERENCES retrieval_hits(retrieval_id, rank, run_id, media_id),
        FOREIGN KEY(event_id, run_id, media_id)
            REFERENCES semantic_events(event_id, run_id, media_id),
        FOREIGN KEY(evidence_id, run_id, media_id)
            REFERENCES evidence(evidence_id, run_id, media_id),
        FOREIGN KEY(event_id, evidence_id) REFERENCES event_evidence(event_id, evidence_id)
    ) STRICT""",
    "CREATE INDEX embeddings_by_run_space ON embeddings(run_id, provider, model, revision_scope)",
    "CREATE INDEX retrieval_runs_by_source ON retrieval_runs(run_id, created_at)",
    *_range_triggers("retrieval_hits"),
    """CREATE TRIGGER retrieval_media_duration_update BEFORE UPDATE OF duration_us ON media_assets
        WHEN EXISTS(SELECT 1 FROM retrieval_hits WHERE media_id = NEW.media_id
            AND end_us > NEW.duration_us)
        BEGIN SELECT RAISE(ABORT, 'media duration excludes retrieval hits'); END""",
    *(
        f"""CREATE TRIGGER {table}_completed_{operation.lower()} BEFORE {operation} ON {table}
            WHEN COALESCE((SELECT status FROM analysis_runs WHERE run_id = NEW.run_id), '')
                <> 'completed'
            BEGIN SELECT RAISE(ABORT, 'retrieval requires completed analysis'); END"""
        for table in ("embeddings", "retrieval_runs")
        for operation in ("INSERT", "UPDATE")
    ),
    *(
        f"""CREATE TRIGGER embeddings_vector_{operation.lower()} BEFORE {operation} ON embeddings
            WHEN NEW.vector_json IS NOT NULL AND json_valid(NEW.vector_json)
                AND EXISTS(SELECT 1 FROM json_each(NEW.vector_json)
                    WHERE type NOT IN ('integer','real') OR abs(value) > 1.7976931348623157e308)
            BEGIN SELECT RAISE(ABORT, 'embedding vector must contain finite numbers'); END"""
        for operation in ("INSERT", "UPDATE")
    ),
    *(
        f"""CREATE TRIGGER retrieval_evidence_event_{operation.lower()}
            BEFORE {operation} ON retrieval_hit_evidence
            WHEN NEW.event_id IS NOT (SELECT event_id FROM retrieval_hits
                WHERE retrieval_id = NEW.retrieval_id AND rank = NEW.rank)
            BEGIN SELECT RAISE(ABORT, 'retrieval evidence event mismatch'); END"""
        for operation in ("INSERT", "UPDATE")
    ),
    """CREATE TRIGGER retrieval_hit_event_update BEFORE UPDATE OF event_id ON retrieval_hits
        WHEN EXISTS(SELECT 1 FROM retrieval_hit_evidence
            WHERE retrieval_id = OLD.retrieval_id AND rank = OLD.rank
                AND event_id IS NOT NEW.event_id)
        BEGIN SELECT RAISE(ABORT, 'retrieval hit event has attached evidence'); END""",
)


def _ddl_for_version(version: int) -> tuple[str, ...]:
    if version == 1:
        return _DDL
    # SQLite places an added column before the first table-level constraint.
    # This reflects the SQL observed after the actual v1 -> v2 ALTER statement.
    version_2 = tuple(
        statement.replace("text TEXT NOT NULL,", "text TEXT NOT NULL, uncertainty TEXT,", 1)
        if statement.startswith("CREATE TABLE transcript_segments ")
        else statement
        for statement in _DDL
    )
    return version_2 if version == 2 else (*version_2, *_MIGRATION_3)


def _invalid_schema() -> AppError:
    return AppError("storage.schema_invalid", "数据库结构或迁移记录不匹配。", ExitCode.STORAGE)


def _normalize_sql(sql: str) -> str:
    # Only collapse whitespace outside SQL string literals. Our definitions use no
    # quoted identifiers; harmless SQLite whitespace changes remain equivalent.
    parts = re.split(r"('(?:[^']|'')*')", sql.strip().rstrip(";"))
    return "".join(
        part if index % 2 else re.sub(r"\s+", "", part).casefold()
        for index, part in enumerate(parts)
    )


def _validate_schema(connection: sqlite3.Connection, version: int) -> None:
    for statement in _ddl_for_version(version):
        name = statement.split()[2]
        row = connection.execute("SELECT sql FROM sqlite_schema WHERE name = ?", (name,)).fetchone()
        if row is None or _normalize_sql(row[0]) != _normalize_sql(statement):
            raise _invalid_schema()
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise _invalid_schema()


def _recorded_version(connection: sqlite3.Connection) -> int:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise AppError(
            "storage.schema_unsupported", "数据库版本高于当前程序支持版本。", ExitCode.STORAGE
        )
    versions = [
        row[0]
        for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")
    ]
    if any(item > SCHEMA_VERSION for item in versions):
        raise AppError(
            "storage.schema_unsupported", "数据库版本高于当前程序支持版本。", ExitCode.STORAGE
        )
    if version < 1 or versions != list(range(1, version + 1)):
        raise _invalid_schema()
    return int(version)


def validate_schema(connection: sqlite3.Connection) -> None:
    """Validate the current schema without writes, including for read-only WAL readers."""
    owns_transaction = not connection.in_transaction
    try:
        if owns_transaction:
            connection.execute("BEGIN")
        version = _recorded_version(connection)
        _validate_schema(connection, version)
        if version < SCHEMA_VERSION:
            raise AppError(
                "storage.migration_required", "数据库需要先由写入进程升级。", ExitCode.STORAGE
            )
        if owns_transaction:
            connection.execute("COMMIT")
    except (AppError, sqlite3.Error) as error:
        if owns_transaction and connection.in_transaction:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                raise _invalid_schema() from None
        if isinstance(error, AppError):
            raise
        raise _invalid_schema() from None


def _record_migration(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (version, datetime.now(UTC).isoformat()),
    )
    connection.execute(f"PRAGMA user_version = {version}")


def migrate(connection: sqlite3.Connection) -> None:
    """Create or upgrade a validated database to the current version atomically.

    The caller must use autocommit=True and enable foreign_keys before calling.
    No executescript(): it would implicitly commit a caller's transaction.
    """
    if connection.autocommit is not True or connection.in_transaction:
        raise _invalid_schema()
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise _invalid_schema()
    try:
        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise AppError(
                "storage.schema_unsupported", "数据库版本高于当前程序支持版本。", ExitCode.STORAGE
            )
        recorded = connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE name = 'schema_migrations' AND type = 'table'"
        ).fetchone()
        if recorded is None:
            existing = connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
            ).fetchone()
            if version != 0 or existing is not None:
                raise _invalid_schema()
            for statement in _DDL:
                connection.execute(statement)
            _record_migration(connection, 1)
            version = 1
        else:
            version = _recorded_version(connection)
        _validate_schema(connection, version)
        if version == 1:
            for statement in _MIGRATION_2:
                connection.execute(statement)
            _record_migration(connection, 2)
            version = 2
        if version == 2:
            for statement in _MIGRATION_3:
                connection.execute(statement)
            _record_migration(connection, 3)
        validate_schema(connection)
        connection.execute("COMMIT")
    except (AppError, sqlite3.Error) as error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        if isinstance(error, AppError):
            raise
        raise AppError(
            "storage.migration", "数据库迁移失败，现有数据未修改。", ExitCode.STORAGE
        ) from None
