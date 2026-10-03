from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import sqlite_schema
from gamingcreator.infrastructure.sqlite_schema import SCHEMA_VERSION, migrate


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    connection.execute("PRAGMA foreign_keys = ON")
    migrate(connection)
    try:
        yield connection
    finally:
        connection.close()


def _seed(connection: sqlite3.Connection, suffix: str = "1") -> None:
    connection.execute(
        "INSERT INTO media_assets VALUES (?, ?, ?, ?, ?)",
        (f"media{suffix}", f"hash{suffix}", "local.mp4", 100, "{}"),
    )
    connection.execute(
        "INSERT INTO analysis_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"run{suffix}",
            f"media{suffix}",
            "{}",
            "hash",
            "v1",
            "hash",
            "[]",
            "running",
            None,
            "now",
            "now",
            None,
            None,
        ),
    )
    connection.execute(
        "INSERT INTO stage_checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f"run{suffix}", "vision", "running", "hash", None, 1, None, "now"),
    )


def _evidence(connection: sqlite3.Connection, suffix: str = "1") -> None:
    connection.execute(
        "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"evidence{suffix}",
            f"run{suffix}",
            f"media{suffix}",
            "vision",
            "image",
            50,
            None,
            "frame.jpg",
            "hash",
            "v1",
            "{}",
        ),
    )


def _event(connection: sqlite3.Connection, suffix: str = "1") -> None:
    connection.execute(
        "INSERT INTO semantic_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"event{suffix}",
            f"run{suffix}",
            f"media{suffix}",
            "vision",
            10,
            100,
            "[]",
            "[]",
            "visual",
            None,
        ),
    )


def _invocation(connection: sqlite3.Connection, request: str = "window1") -> None:
    connection.execute(
        "INSERT INTO provider_invocations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            request,
            "run1",
            "vision",
            request,
            1,
            "running",
            "{}",
            None,
            None,
            None,
            None,
            None,
            None,
            "unverified",
            None,
            "now",
            None,
        ),
    )


def test_migrate_is_idempotent_and_creates_strict_schema(db: sqlite3.Connection) -> None:
    migrate(db)
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert db.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [
        (1,),
        (2,),
    ]
    tables = [row for row in db.execute("PRAGMA table_list") if not row[1].startswith("sqlite_")]
    assert len(tables) == 9
    assert all(row[5] == 1 for row in tables)
    assert not db.in_transaction


def test_failed_new_migration_rolls_back_all_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = sqlite3.connect(":memory:", autocommit=True)
    connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(sqlite_schema, "_DDL", (*sqlite_schema._DDL, "INVALID SQL"))
    try:
        with pytest.raises(AppError, match="数据库迁移") as caught:
            migrate(connection)
        assert caught.value.code == "storage.migration"
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert not connection.in_transaction
    finally:
        connection.close()


@pytest.mark.parametrize("change", ["pragma", "record"])
def test_future_version_is_rejected_without_modification(
    db: sqlite3.Connection, change: str
) -> None:
    if change == "pragma":
        db.execute("PRAGMA user_version = 3")
    else:
        db.execute("INSERT INTO schema_migrations VALUES (3, 'now')")
    before = db.serialize()
    with pytest.raises(AppError) as caught:
        migrate(db)
    assert caught.value.code == "storage.schema_unsupported"
    assert db.serialize() == before


@pytest.mark.parametrize(
    "change",
    [
        "DELETE FROM schema_migrations",
        "DELETE FROM schema_migrations WHERE version = 1",
        "PRAGMA user_version = 0",
        "DROP TRIGGER evidence_duration_insert",
    ],
)
def test_inconsistent_versions_or_definitions_are_rejected(
    db: sqlite3.Connection, change: str
) -> None:
    db.execute(change)
    before = db.serialize()
    with pytest.raises(AppError) as caught:
        migrate(db)
    assert caught.value.code == "storage.schema_invalid"
    assert db.serialize() == before


def test_unversioned_existing_database_is_not_claimed() -> None:
    connection = sqlite3.connect(":memory:", autocommit=True)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("CREATE TABLE important_user_data (value TEXT)")
    try:
        with pytest.raises(AppError) as caught:
            migrate(connection)
        assert caught.value.code == "storage.schema_invalid"
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == [
            ("important_user_data",)
        ]
    finally:
        connection.close()


@pytest.mark.parametrize("foreign_keys", [False, True])
def test_migration_requires_autocommit_and_foreign_keys(foreign_keys: bool) -> None:
    connection = sqlite3.connect(":memory:", autocommit=foreign_keys is False)
    connection.execute(f"PRAGMA foreign_keys = {int(foreign_keys)}")
    try:
        with pytest.raises(AppError) as caught:
            migrate(connection)
        assert caught.value.code == "storage.schema_invalid"
    finally:
        connection.close()


def test_cross_run_media_and_evidence_references_are_rejected(db: sqlite3.Connection) -> None:
    _seed(db)
    _seed(db, "2")
    _evidence(db)
    _evidence(db, "2")
    _event(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE evidence SET media_id = 'media2' WHERE evidence_id = 'evidence1'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO event_evidence VALUES ('event1', 'evidence2', 'run1', 'media1')")
    db.execute("INSERT INTO event_evidence VALUES ('event1', 'evidence1', 'run1', 'media1')")
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_stage_reference_must_belong_to_run(db: sqlite3.Connection) -> None:
    _seed(db)
    _evidence(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE evidence SET stage_id = 'unknown'")


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE evidence SET start_us = 100",
        "UPDATE evidence SET end_us = 51",
        "UPDATE evidence SET kind = 'audio', end_us = 101",
        "UPDATE semantic_events SET end_us = 101",
        "UPDATE semantic_events SET start_us = end_us",
        "UPDATE media_assets SET duration_us = 99",
    ],
)
def test_source_ranges_remain_inside_media(db: sqlite3.Connection, change: str) -> None:
    _seed(db)
    _evidence(db)
    _event(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(change)


def test_transcript_insert_and_update_check_duration(db: sqlite3.Connection) -> None:
    _seed(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO transcript_segments VALUES "
            "('s', 'run1', 'media1', 'vision', 1, 101, 'text', NULL)"
        )
    db.execute(
        "INSERT INTO transcript_segments VALUES "
        "('s', 'run1', 'media1', 'vision', 1, 100, 'text', NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE transcript_segments SET end_us = 101")


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE media_assets SET duration_us = 0",
        "UPDATE media_assets SET duration_us = 'invalid'",
        "UPDATE analysis_runs SET config_json = 'not JSON'",
        "UPDATE analysis_runs SET manifest_path = 'manifest.json'",
        "UPDATE stage_checkpoints SET attempt = 0",
        "UPDATE provider_invocations SET input_tokens = -1",
        "UPDATE provider_invocations SET input_tokens = 1, cached_input_tokens = 2",
        "UPDATE provider_invocations SET original_cost = 'NaN', currency = 'CNY'",
        "UPDATE provider_invocations SET original_cost = '-0.01', currency = 'CNY'",
        "UPDATE provider_invocations SET cost_cny = 'garbage'",
    ],
)
def test_invalid_types_json_and_ledger_values_are_rejected(
    db: sqlite3.Connection, change: str
) -> None:
    _seed(db)
    _invocation(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(change)


def test_unknown_ledger_is_null_and_windows_have_separate_requests(db: sqlite3.Connection) -> None:
    _seed(db)
    _invocation(db)
    _invocation(db, "window2")
    assert db.execute(
        "SELECT input_tokens, original_cost, cost_cny FROM provider_invocations ORDER BY invocation_id"
    ).fetchall() == [(None, None, None), (None, None, None)]
    db.execute(
        "UPDATE provider_invocations SET original_cost = '0.0000000000000000001', currency = 'CNY' "
        "WHERE invocation_id = 'window1'"
    )
    assert (
        db.execute(
            "SELECT original_cost FROM provider_invocations WHERE invocation_id = 'window1'"
        ).fetchone()[0]
        == "0.0000000000000000001"
    )
