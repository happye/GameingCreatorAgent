from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from gamingcreator.domain.errors import AppError
from gamingcreator.domain.models import Embedding, EmbeddingSpace
from gamingcreator.infrastructure import sqlite_schema
from gamingcreator.infrastructure.retrieval_persistence import (
    PersistedRetrievalHit,
    load_embeddings,
    load_retrieval,
    persist_embedding,
    persist_embedding_identity,
    persist_retrieval,
)
from gamingcreator.infrastructure.sqlite_schema import migrate, validate_schema


def open_db(path: Path | str = ":memory:", *, readonly: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro" if readonly and isinstance(path, Path) else path,
        uri=readonly,
        autocommit=True,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def seed(connection: sqlite3.Connection, suffix: str = "1") -> None:
    connection.execute(
        "INSERT INTO media_assets VALUES (?, ?, ?, 1000, '{}')",
        (f"m{suffix}", f"hash{suffix}", "synthetic-fixture.mp4"),
    )
    connection.execute(
        "INSERT INTO analysis_runs VALUES (?, ?, '{}', 'config', 'v1', 'pipeline', '[\"vision\"]', "
        "'completed', NULL, 'created', 'updated', NULL, NULL)",
        (f"r{suffix}", f"m{suffix}"),
    )
    connection.execute(
        "INSERT INTO stage_checkpoints VALUES (?, 'vision', 'completed', 'in', 'out', 1, NULL, 'now')",
        (f"r{suffix}",),
    )
    connection.execute(
        "INSERT INTO evidence VALUES (?, ?, ?, 'vision', 'image', 10, NULL, "
        "'synthetic.jpg', 'hash', 'v1', '{}')",
        (f"frame{suffix}", f"r{suffix}", f"m{suffix}"),
    )
    connection.execute(
        "INSERT INTO semantic_events VALUES (?, ?, ?, 'vision', 10, 100, "
        "'[\"synthetic action\"]', '[\"dodge\"]', 'visual', NULL)",
        (f"event{suffix}", f"r{suffix}", f"m{suffix}"),
    )
    connection.execute(
        "INSERT INTO event_evidence VALUES (?, ?, ?, ?)",
        (f"event{suffix}", f"frame{suffix}", f"r{suffix}", f"m{suffix}"),
    )


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    with closing(open_db()) as connection:
        migrate(connection)
        seed(connection)
        yield connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise


def hit(**changes: Any) -> PersistedRetrievalHit:
    return replace(
        PersistedRetrievalHit(1, "candidate", "event1", 10, 100, 0.75, "lexical", ("frame1",)),
        **changes,
    )


def space(**changes: Any) -> EmbeddingSpace:
    return replace(EmbeddingSpace("local", "real-feature-transform", "rev1", 2, "l2"), **changes)


def save(connection: sqlite3.Connection, **changes: Any) -> str:
    values: dict[str, Any] = {
        "query": "闪避",
        "retrieval_version": "retrieval-fixture-v1",
        "parameters": {"mode": "lexical", "topK": 10},
        "elapsed_ms": 1.25,
        "hits": (hit(),),
        "result_json": {"fixture": True},
        "embedding_space": space(),
        "retrieval_id": "search1",
    }
    values.update(changes)
    return persist_retrieval(connection, "r1", **values)


def test_fresh_v3_schema_has_strict_tables_and_continuous_history(db: sqlite3.Connection) -> None:
    assert db.execute("PRAGMA user_version").fetchone() == (3,)
    assert db.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [
        (1,),
        (2,),
        (3,),
    ]
    tables = [row for row in db.execute("PRAGMA table_list") if not row[1].startswith("sqlite_")]
    assert len(tables) == 13
    assert all(row[5] == 1 for row in tables)
    migrate(db)
    validate_schema(db)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_databases_upgrade_without_rewriting_transcripts(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / f"v{version}.sqlite3"
    with closing(open_db(path)) as connection:
        for statement in sqlite_schema._ddl_for_version(version):
            connection.execute(statement)
        for old_version in range(1, version + 1):
            connection.execute(
                "INSERT INTO schema_migrations VALUES (?, 'historical')", (old_version,)
            )
        connection.execute(f"PRAGMA user_version = {version}")
        seed(connection)
        columns = "segment_id, run_id, media_id, stage_id, start_us, end_us, text"
        connection.execute(
            f"INSERT INTO transcript_segments ({columns}) VALUES "
            "('segment', 'r1', 'm1', 'vision', 10, 100, '历史转录')"
        )
        before = connection.execute("SELECT * FROM transcript_segments").fetchone()
        migrate(connection)
        after = connection.execute("SELECT * FROM transcript_segments").fetchone()
        assert after == (*before, None) if version == 1 else after == before
        assert connection.execute(
            "SELECT applied_at FROM schema_migrations WHERE version = 1"
        ).fetchone() == ("historical",)
        with closing(open_db(path, readonly=True)) as reader:
            validate_schema(reader)
            assert reader.execute("PRAGMA user_version").fetchone() == (3,)


@pytest.mark.parametrize("version", [1, 2])
def test_readonly_legacy_requires_upgrade_without_any_writes(tmp_path: Path, version: int) -> None:
    path = tmp_path / f"old{version}.sqlite3"
    with closing(open_db(path)) as connection:
        for statement in sqlite_schema._ddl_for_version(version):
            connection.execute(statement)
        for old_version in range(1, version + 1):
            connection.execute("INSERT INTO schema_migrations VALUES (?, 'old')", (old_version,))
        connection.execute(f"PRAGMA user_version = {version}")
        before = connection.serialize()
        with closing(open_db(path, readonly=True)) as reader:
            with pytest.raises(AppError) as caught:
                validate_schema(reader)
            assert caught.value.code == "storage.migration_required"
            assert not reader.in_transaction
        assert connection.serialize() == before


def test_failed_migration_3_restores_v2_bytes_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    with closing(open_db()) as connection:
        for statement in sqlite_schema._ddl_for_version(2):
            connection.execute(statement)
        connection.execute("INSERT INTO schema_migrations VALUES (1, 'old'), (2, 'old')")
        connection.execute("PRAGMA user_version = 2")
        seed(connection)
        before = connection.serialize()
        monkeypatch.setattr(
            sqlite_schema, "_MIGRATION_3", (*sqlite_schema._MIGRATION_3, "INVALID SQL")
        )
        with pytest.raises(AppError) as caught:
            migrate(connection)
        assert caught.value.code == "storage.migration"
        assert connection.serialize() == before
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert not connection.in_transaction


def test_future_version_and_new_definition_drift_are_rejected(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA user_version = 4")
    before = db.serialize()
    with pytest.raises(AppError) as future:
        validate_schema(db)
    assert future.value.code == "storage.schema_unsupported"
    assert db.serialize() == before
    db.execute("PRAGMA user_version = 3")
    db.execute("DROP TRIGGER embeddings_vector_insert")
    before = db.serialize()
    with pytest.raises(AppError) as drift:
        migrate(db)
    assert drift.value.code == "storage.schema_invalid"
    assert db.serialize() == before


def test_search_provenance_and_normalized_hits_survive_another_connection(tmp_path: Path) -> None:
    path = tmp_path / "timeline.sqlite3"
    with closing(open_db(path)) as connection:
        migrate(connection)
        seed(connection)
        with transaction(connection):
            identifier = save(connection)
            assert connection.in_transaction
        with closing(open_db(path, readonly=True)) as reader:
            validate_schema(reader)
            record = load_retrieval(reader, identifier)
            assert record["runId"] == "r1"
            assert record["query"] == "闪避"
            assert record["retrievalVersion"] == "retrieval-fixture-v1"
            assert record["parameters"] == {"mode": "lexical", "topK": 10}
            assert record["elapsedMs"] == 1.25
            assert record["result"] == {"fixture": True}
            assert record["embeddingSpace"] == {
                "provider": "local",
                "model": "real-feature-transform",
                "revision_scope": "rev1",
                "dimension": 2,
                "normalization": "l2",
            }
            loaded: Any = record["hits"]
            assert loaded[0]["candidate_id"] == "candidate"
            assert loaded[0]["evidence_ids"] == ("frame1",)
            assert not reader.in_transaction


def test_empty_search_is_a_persisted_valid_result(db: sqlite3.Connection) -> None:
    with transaction(db):
        identifier = save(db, hits=(), result_json={"hits": [], "reason": "no_match"})
    assert load_retrieval(db, identifier)["hits"] == []
    assert db.execute("SELECT count(*) FROM retrieval_runs").fetchone() == (1,)


def add_audio(
    connection: sqlite3.Connection, *, suffix: str = "1", start: int = 0, end: int = 1000
) -> None:
    connection.execute(
        "INSERT INTO evidence VALUES (?, ?, ?, 'vision', 'audio', ?, ?, "
        "'synthetic.wav', 'hash', 'v1', '{}')",
        (f"audio{suffix}", f"r{suffix}", f"m{suffix}", start, end),
    )


def test_unbound_transcript_candidate_keeps_null_event_and_real_audio_evidence(
    db: sqlite3.Connection,
) -> None:
    add_audio(db)
    audio_hit = hit(event_id=None, evidence_ids=("audio1",), score_kind="transcript_lexical")
    with transaction(db):
        identifier = save(db, hits=(audio_hit,))
    record = load_retrieval(db, identifier)
    rows: Any = record["hits"]
    assert rows[0]["event_id"] is None
    assert rows[0]["evidence_ids"] == ("audio1",)
    assert db.execute("SELECT count(*) FROM semantic_events").fetchone() == (1,)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE retrieval_hit_evidence SET run_id = 'not-a-real-run'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE retrieval_hit_evidence SET event_id = 'event1'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE retrieval_hits SET event_id = 'event1'")


@pytest.mark.parametrize("audio_case", ["image", "other_run", "no_overlap", "boundary_touch"])
def test_unbound_transcript_needs_same_run_overlapping_audio(
    db: sqlite3.Connection, audio_case: str
) -> None:
    evidence_id = "frame1"
    if audio_case == "other_run":
        seed(db, "2")
        add_audio(db, suffix="2")
        evidence_id = "audio2"
    elif audio_case == "no_overlap":
        add_audio(db, start=200, end=1000)
        evidence_id = "audio1"
    elif audio_case == "boundary_touch":
        add_audio(db, start=100, end=1000)
        evidence_id = "audio1"
    with transaction(db):
        with pytest.raises(ValueError, match="overlapping audio"):
            save(db, hits=(hit(event_id=None, evidence_ids=(evidence_id,)),))
    assert db.execute("SELECT count(*) FROM retrieval_runs").fetchone() == (0,)


def test_function_never_opens_or_commits_callers_transaction(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="active transaction"):
        save(db)
    db.execute("BEGIN IMMEDIATE")
    save(db)
    assert db.in_transaction
    db.execute("ROLLBACK")
    assert db.execute("SELECT count(*) FROM retrieval_runs").fetchone() == (0,)


def test_invalid_second_hit_rolls_back_entire_search_but_preserves_outer_transaction(
    db: sqlite3.Connection,
) -> None:
    seed(db, "2")
    with transaction(db):
        with pytest.raises(sqlite3.IntegrityError):
            save(db, hits=(hit(), hit(rank=2, candidate_id="cross", event_id="event2")))
        assert db.in_transaction
        assert db.execute("SELECT count(*) FROM retrieval_runs").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM retrieval_hits").fetchone() == (0,)
        save(db)


def test_evidence_must_belong_to_hit_event_even_inside_same_run(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO evidence VALUES ('unlinked', 'r1', 'm1', 'vision', 'image', 10, NULL, "
        "'synthetic.jpg', 'hash', 'v1', '{}')"
    )
    with transaction(db):
        with pytest.raises(sqlite3.IntegrityError):
            save(db, hits=(hit(evidence_ids=("unlinked",)),))
        assert db.execute("SELECT count(*) FROM retrieval_runs").fetchone() == (0,)


def test_hit_parent_event_update_cannot_detach_its_evidence(db: sqlite3.Connection) -> None:
    with transaction(db):
        save(db)
    db.execute(
        "INSERT INTO semantic_events VALUES ('another', 'r1', 'm1', 'vision', 10, 100, "
        "'[]', '[]', 'visual', NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE retrieval_hits SET event_id = 'another'")


def test_cross_run_evidence_and_source_range_changes_are_rejected(db: sqlite3.Connection) -> None:
    seed(db, "2")
    with transaction(db):
        with pytest.raises(sqlite3.IntegrityError):
            save(db, hits=(hit(evidence_ids=("frame2",)),))
        save(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE retrieval_hits SET end_us = 1001")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE media_assets SET duration_us = 50 WHERE media_id = 'm1'")


def test_incomplete_analysis_is_not_searchable_or_embedding_writable(
    db: sqlite3.Connection,
) -> None:
    db.execute("UPDATE analysis_runs SET status = 'failed'")
    with transaction(db):
        with pytest.raises(AppError, match="已完成"):
            save(db)
        with pytest.raises(AppError, match="已完成"):
            persist_embedding_identity(
                db, "r1", subject_id="event1", space=space(), text_hash="a" * 64
            )


@pytest.mark.parametrize(
    "changes",
    [
        {"elapsed_ms": True},
        {"elapsed_ms": float("inf")},
        {"elapsed_ms": -1},
        {"hits": (hit(rank=2),)},
        {"hits": (hit(), hit(rank=2))},
        {"hits": (hit(end_us=1001),)},
        {"parameters": {"notFinite": float("nan")}},
    ],
)
def test_invalid_search_parameters_do_not_create_rows(
    db: sqlite3.Connection, changes: dict[str, Any]
) -> None:
    with transaction(db):
        with pytest.raises(ValueError):
            save(db, **changes)
    assert db.execute("SELECT count(*) FROM retrieval_runs").fetchone() == (0,)


@pytest.mark.parametrize("field,value", [("rank", True), ("start_us", 1.0), ("score", True)])
def test_typed_hit_rejects_coerced_rank_time_and_score(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        hit(**{field: value})


def test_embedding_identity_can_be_recorded_then_filled_without_fabricated_vector(
    db: sqlite3.Connection,
) -> None:
    with transaction(db):
        identifier = persist_embedding_identity(
            db, "r1", subject_id="event1", space=space(), text_hash="a" * 64
        )
        assert db.execute("SELECT vector_json FROM embeddings").fetchone() == (None,)
        assert load_embeddings(db, "r1", space()) == ()
        actual = Embedding("event1", space(), (1.0, 0.0), "a" * 64)
        assert persist_embedding(db, "r1", actual) == identifier
        assert persist_embedding(db, "r1", actual) == identifier
        assert load_embeddings(db, "r1", space()) == (actual,)
    assert db.execute("SELECT count(*) FROM embeddings").fetchone() == (1,)


@pytest.mark.parametrize(
    "modified_space,text_hash",
    [
        (space(provider="other"), "a" * 64),
        (space(model="other"), "a" * 64),
        (space(revision_scope="run:r1:unresolved"), "a" * 64),
        (space(dimension=3), "a" * 64),
        (space(normalization="none"), "a" * 64),
        (space(), "b" * 64),
    ],
)
def test_embedding_unique_key_preserves_every_space_and_text_identity(
    db: sqlite3.Connection, modified_space: EmbeddingSpace, text_hash: str
) -> None:
    with transaction(db):
        first = persist_embedding_identity(
            db, "r1", subject_id="event1", space=space(), text_hash="a" * 64
        )
        second = persist_embedding_identity(
            db, "r1", subject_id="event1", space=modified_space, text_hash=text_hash
        )
    assert first != second
    assert db.execute("SELECT count(*) FROM embeddings").fetchone() == (2,)


def test_embedding_cannot_borrow_subject_from_another_run_or_change_existing_values(
    db: sqlite3.Connection,
) -> None:
    seed(db, "2")
    with transaction(db):
        with pytest.raises(sqlite3.IntegrityError):
            persist_embedding_identity(
                db, "r1", subject_id="event2", space=space(), text_hash="a" * 64
            )
        persist_embedding(db, "r1", Embedding("event1", space(), (1.0, 0.0), "a" * 64))
        with pytest.raises(ValueError, match="immutable"):
            persist_embedding(db, "r1", Embedding("event1", space(), (0.0, 1.0), "a" * 64))
    assert load_embeddings(db, "r1", space())[0].vector == (1.0, 0.0)


def test_evidence_embedding_scope_and_space_filtering(db: sqlite3.Connection) -> None:
    with transaction(db):
        persist_embedding(
            db,
            "r1",
            Embedding("frame1", space(), (1.0, 0.0), "a" * 64),
            subject_kind="evidence",
        )
    assert load_embeddings(db, "r1", space(revision_scope="another")) == ()
    assert load_embeddings(db, "r1", space()) == ()
    assert load_embeddings(db, "r1", space(), subject_kind="evidence")[0].subject_id == "frame1"


def test_embedding_values_must_match_declared_dimension_and_normalization(
    db: sqlite3.Connection,
) -> None:
    with transaction(db):
        with pytest.raises(ValueError, match="normalization"):
            persist_embedding(db, "r1", Embedding("event1", space(), (2.0, 0.0), "a" * 64))
        with pytest.raises(ValueError, match="SHA256"):
            persist_embedding(db, "r1", Embedding("event1", space(), (1.0, 0.0), "not-sha"))
    assert db.execute("SELECT count(*) FROM embeddings").fetchone() == (0,)


@pytest.mark.parametrize("vector", ["[true,0]", '["1",0]', "[1e400,0]", "[1]"])
def test_database_rejects_non_numeric_nonfinite_and_wrong_dimension_vectors(
    db: sqlite3.Connection, vector: str
) -> None:
    with transaction(db):
        persist_embedding_identity(db, "r1", subject_id="event1", space=space(), text_hash="a" * 64)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE embeddings SET vector_json = ?", (vector,))


def test_stored_query_hash_corruption_is_refused(db: sqlite3.Connection) -> None:
    with transaction(db):
        save(db)
    db.execute("UPDATE retrieval_runs SET query = 'changed'")
    with pytest.raises(ValueError, match="query hash"):
        load_retrieval(db, "search1")


def test_changed_embedding_identity_or_normalization_is_refused_on_reload(
    db: sqlite3.Connection,
) -> None:
    with transaction(db):
        persist_embedding(db, "r1", Embedding("event1", space(), (1.0, 0.0), "a" * 64))
    db.execute("UPDATE embeddings SET vector_json = '[2.0,0.0]'")
    with pytest.raises(ValueError, match="normalization"):
        load_embeddings(db, "r1", space())
    db.execute("UPDATE embeddings SET vector_json = '[1.0,0.0]', text_hash = ?", ("b" * 64,))
    with pytest.raises(ValueError, match="identity"):
        load_embeddings(db, "r1", space())
    with transaction(db):
        with pytest.raises(ValueError, match="identity"):
            persist_embedding_identity(
                db, "r1", subject_id="event1", space=space(), text_hash="a" * 64
            )


def test_payload_contains_no_video_or_audio_blob(db: sqlite3.Connection) -> None:
    with transaction(db):
        save(db)
    for table in ("embeddings", "retrieval_runs", "retrieval_hits", "retrieval_hit_evidence"):
        assert "BLOB" not in [column[2] for column in db.execute(f"PRAGMA table_info({table})")]
    assert json.dumps(load_retrieval(db, "search1"), ensure_ascii=False)
