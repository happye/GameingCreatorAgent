from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import sqlite_schema
from gamingcreator.infrastructure.sqlite_schema import SCHEMA_VERSION, migrate, validate_schema


def _open(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    connection = (
        sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, autocommit=True)
        if readonly
        else sqlite3.connect(path, autocommit=True)
    )
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@pytest.fixture
def v1_database(tmp_path: Path) -> Iterator[tuple[Path, sqlite3.Connection]]:
    """Build the historical v1 DDL directly, without changing the migration runner."""
    path = tmp_path / "timeline.sqlite3"
    connection = _open(path)
    try:
        for statement in sqlite_schema._DDL:
            connection.execute(statement)
        connection.execute("INSERT INTO schema_migrations VALUES (1, 'v1-created')")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("INSERT INTO media_assets VALUES ('m', 'hash', 'video.mp4', 100, '{}')")
        connection.execute(
            "INSERT INTO analysis_runs VALUES "
            "('r', 'm', '{}', 'config-hash', 'v1', 'pipeline-hash', '[\"asr\"]', "
            "'running', NULL, 'created', 'updated', NULL, NULL)"
        )
        connection.execute(
            "INSERT INTO stage_checkpoints VALUES "
            "('r', 'asr', 'completed', 'input-hash', 'output-hash', 1, NULL, 'updated')"
        )
        connection.execute(
            "INSERT INTO transcript_segments VALUES ('s', 'r', 'm', 'asr', 10, 100, '历史转录')"
        )
        yield path, connection
    finally:
        connection.close()


def test_v1_transcripts_upgrade_without_rewriting_existing_data(
    v1_database: tuple[Path, sqlite3.Connection],
) -> None:
    path, connection = v1_database
    before = connection.execute("SELECT * FROM transcript_segments").fetchone()
    migrate(connection)
    assert connection.execute("SELECT * FROM transcript_segments").fetchone() == (*before, None)
    assert connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall() == [(version,) for version in range(1, SCHEMA_VERSION + 1)]
    assert (
        connection.execute("SELECT applied_at FROM schema_migrations WHERE version = 1").fetchone()[
            0
        ]
        == "v1-created"
    )
    with closing(_open(path, readonly=True)) as reader:
        validate_schema(reader)
        assert reader.execute("SELECT uncertainty FROM transcript_segments").fetchone() == (None,)


def test_uncertainty_is_persisted_and_readable_after_reopen(
    v1_database: tuple[Path, sqlite3.Connection],
) -> None:
    path, connection = v1_database
    migrate(connection)
    connection.execute(
        "INSERT INTO transcript_segments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("new", "r", "m", "asr", 1, 20, "边界内容", "audio_source_discontinuity"),
    )
    with closing(_open(path, readonly=True)) as reader:
        validate_schema(reader)
        assert reader.execute(
            "SELECT text, uncertainty FROM transcript_segments WHERE segment_id = 'new'"
        ).fetchone() == ("边界内容", "audio_source_discontinuity")
    migrate(connection)
    validate_schema(connection)


def test_migration_2_failure_rolls_back_alter_data_and_version(
    v1_database: tuple[Path, sqlite3.Connection], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, connection = v1_database
    before = connection.serialize()
    monkeypatch.setattr(sqlite_schema, "_MIGRATION_2", (*sqlite_schema._MIGRATION_2, "INVALID SQL"))
    with pytest.raises(AppError) as caught:
        migrate(connection)
    assert caught.value.code == "storage.migration"
    assert connection.serialize() == before
    assert connection.execute("PRAGMA user_version").fetchone() == (1,)
    assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]
    assert "uncertainty" not in [
        row[1] for row in connection.execute("PRAGMA table_info(transcript_segments)")
    ]
    assert connection.execute("SELECT text FROM transcript_segments").fetchone() == ("历史转录",)
    assert not connection.in_transaction


def test_readonly_v1_requires_migration_and_does_not_change_database(
    v1_database: tuple[Path, sqlite3.Connection],
) -> None:
    path, connection = v1_database
    before = connection.serialize()
    with closing(_open(path, readonly=True)) as reader:
        with pytest.raises(AppError) as caught:
            validate_schema(reader)
        assert caught.value.code == "storage.migration_required"
    assert connection.serialize() == before


@pytest.mark.parametrize(
    "change",
    [
        "DROP TRIGGER transcript_segments_duration_update",
        "DROP INDEX transcripts_by_run",
        "DELETE FROM schema_migrations",
    ],
)
def test_drifted_v1_is_rejected_before_alter(
    v1_database: tuple[Path, sqlite3.Connection], change: str
) -> None:
    path, connection = v1_database
    connection.execute(change)
    before = connection.serialize()
    with pytest.raises(AppError) as caught:
        migrate(connection)
    assert caught.value.code == "storage.schema_invalid"
    assert connection.serialize() == before
    with closing(_open(path, readonly=True)) as reader:
        with pytest.raises(AppError) as readonly_error:
            validate_schema(reader)
        assert readonly_error.value.code == "storage.schema_invalid"


def test_v1_foreign_key_violation_is_rejected_before_alter(
    v1_database: tuple[Path, sqlite3.Connection],
) -> None:
    _, connection = v1_database
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("UPDATE transcript_segments SET media_id = 'missing'")
    connection.execute("PRAGMA foreign_keys = ON")
    before = connection.serialize()
    with pytest.raises(AppError) as caught:
        migrate(connection)
    assert caught.value.code == "storage.schema_invalid"
    assert connection.serialize() == before


def test_current_column_drift_and_future_version_are_rejected_for_readers(
    v1_database: tuple[Path, sqlite3.Connection],
) -> None:
    _, connection = v1_database
    migrate(connection)
    connection.execute("ALTER TABLE transcript_segments ADD COLUMN unexpected TEXT")
    with pytest.raises(AppError) as drift:
        validate_schema(connection)
    assert drift.value.code == "storage.schema_invalid"
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    before = connection.serialize()
    with pytest.raises(AppError) as future:
        validate_schema(connection)
    assert future.value.code == "storage.schema_unsupported"
    assert connection.serialize() == before


def test_fresh_database_has_all_migrations_and_nullable_text_column(tmp_path: Path) -> None:
    connection = _open(tmp_path / "fresh.sqlite3")
    try:
        migrate(connection)
        validate_schema(connection)
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(version,) for version in range(1, SCHEMA_VERSION + 1)]
        columns = connection.execute("PRAGMA table_info(transcript_segments)").fetchall()
        assert columns[-1][1:4] == ("uncertainty", "TEXT", 0)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.parametrize("latest", [False, True])
@pytest.mark.parametrize("outer_transaction", [False, True])
def test_read_validation_closes_only_transactions_it_owns(
    v1_database: tuple[Path, sqlite3.Connection], latest: bool, outer_transaction: bool
) -> None:
    path, connection = v1_database
    if latest:
        migrate(connection)
    before = connection.serialize()
    with closing(_open(path, readonly=True)) as reader:
        if outer_transaction:
            reader.execute("BEGIN")
        statements: list[str] = []
        reader.set_trace_callback(statements.append)
        if latest:
            validate_schema(reader)
        else:
            with pytest.raises(AppError) as caught:
                validate_schema(reader)
            assert caught.value.code == "storage.migration_required"
        assert reader.in_transaction == outer_transaction
        control_statements = [sql for sql in statements if sql in ("BEGIN", "COMMIT", "ROLLBACK")]
        assert control_statements == (
            [] if outer_transaction else ["BEGIN", "COMMIT" if latest else "ROLLBACK"]
        )
        if outer_transaction:
            reader.execute("ROLLBACK")
    assert connection.serialize() == before


def test_read_validation_uses_one_snapshot_during_concurrent_migration(
    v1_database: tuple[Path, sqlite3.Connection],
) -> None:
    path, connection = v1_database
    connection.execute("PRAGMA journal_mode = WAL")
    migrated = False
    with closing(_open(path, readonly=True)) as reader:

        def migrate_between_reads(statement: str) -> None:
            nonlocal migrated
            if not migrated and statement.startswith("SELECT version FROM schema_migrations"):
                with closing(_open(path)) as writer:
                    migrate(writer)
                migrated = True

        reader.set_trace_callback(migrate_between_reads)
        with pytest.raises(AppError) as caught:
            validate_schema(reader)
        assert caught.value.code == "storage.migration_required"
        assert migrated
        assert not reader.in_transaction
        reader.set_trace_callback(None)
        validate_schema(reader)
    assert connection.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
