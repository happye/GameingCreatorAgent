"""Independent project-local SQLite store for immutable imported static collections."""

import hashlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from gamingcreator.application.static_observations import (
    PublishStatus,
    StaticCollectionArtifact,
    StaticObservationRecord,
    StoredStaticCollection,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.static_observations import (
    STATIC_STORE_SCHEMA_VERSION,
    UnsupportedStaticSchema,
    canonical_observation_json,
    canonical_package_json,
    canonical_provenance_json,
    observation_id,
    package_sha256,
)
from gamingcreator.infrastructure.static_observation_codec import loads_static_package

STORE_FILE_NAME = "static-observations.sqlite3"
_STORE_USER_VERSION = 1
_HASH = re.compile(r"[0-9a-f]{64}\Z")

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE static_meta (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE static_collections (
        run_id TEXT NOT NULL,
        collection_id TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        media_id TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        config_hash TEXT NOT NULL,
        pipeline_version TEXT NOT NULL,
        pipeline_hash TEXT,
        provenance_json TEXT NOT NULL,
        canonical_payload TEXT NOT NULL,
        package_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (run_id, collection_id)
    )
    """,
    """
    CREATE TABLE static_observations (
        run_id TEXT NOT NULL,
        collection_id TEXT NOT NULL,
        observation_id TEXT NOT NULL,
        local_observation_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        source_time_us INTEGER NOT NULL,
        image_sha256 TEXT NOT NULL,
        artifact_path TEXT NOT NULL,
        source_path TEXT NOT NULL,
        observation_json TEXT NOT NULL,
        PRIMARY KEY (run_id, collection_id, observation_id),
        UNIQUE (run_id, collection_id, local_observation_id),
        FOREIGN KEY (run_id, collection_id)
            REFERENCES static_collections (run_id, collection_id)
            ON DELETE RESTRICT
    )
    """,
)
_REQUIRED_COLUMNS = {
    "static_meta": frozenset({"key", "value"}),
    "static_collections": frozenset(
        {
            "run_id",
            "collection_id",
            "schema_version",
            "media_id",
            "source_sha256",
            "config_hash",
            "pipeline_version",
            "pipeline_hash",
            "provenance_json",
            "canonical_payload",
            "package_sha256",
            "created_at",
        }
    ),
    "static_observations": frozenset(
        {
            "run_id",
            "collection_id",
            "observation_id",
            "local_observation_id",
            "evidence_id",
            "source_time_us",
            "image_sha256",
            "artifact_path",
            "source_path",
            "observation_json",
        }
    ),
}


def _error(code: str, message: str) -> AppError:
    return AppError(code, message, ExitCode.STORAGE)


def _path_error() -> AppError:
    return _error(
        "static.path",
        "静态观察库必须是项目内固定的普通文件，不能是符号链接、硬链接或逃逸路径。",
    )


def _schema_error() -> AppError:
    return _error("static.store_schema", "静态观察库的版本或结构不受支持。")


def _integrity_error() -> AppError:
    return _error("static.integrity", "静态观察库的声明、哈希或存储投影不一致。")


def _text(value: object) -> str:
    if type(value) is not str:
        raise _integrity_error()
    return value


def _hash(value: object) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise _integrity_error()
    return value


def _time_us(value: object) -> int:
    if type(value) is not int or value < 0:
        raise _integrity_error()
    return value


def _path_text(value: object) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        raise _integrity_error()
    return value


def _resolve_project(project: Path, *, create: bool) -> Path:
    try:
        if project.is_symlink() or project.is_junction():
            raise _path_error()
        resolved = project.resolve()
        if create:
            resolved.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise _path_error() from error
    if not resolved.is_dir():
        raise _path_error()
    return resolved


def _store_path(project: Path) -> Path:
    database = project / STORE_FILE_NAME
    try:
        for candidate in (
            database,
            database.with_name(database.name + "-wal"),
            database.with_name(database.name + "-shm"),
            database.with_name(database.name + "-journal"),
        ):
            if candidate.is_symlink() or candidate.is_junction():
                raise _path_error()
            if candidate.exists():
                stat = candidate.lstat()
                if stat.st_nlink != 1 or not candidate.is_file():
                    raise _path_error()
        if database.exists() and database.resolve().parent != project:
            raise _path_error()
    except OSError as error:
        raise _path_error() from error
    return database


class SqliteStaticObservationStore:
    """One explicit (runId, collectionId) lookup at a time; no cross-collection fallback."""

    def __init__(self, project: Path, *, read_only: bool) -> None:
        self.project = _resolve_project(project, create=not read_only)
        self.read_only = read_only
        self.database = _store_path(self.project)
        self._connection: sqlite3.Connection | None = None

    @classmethod
    def open(cls, project: Path, *, read_only: bool) -> "SqliteStaticObservationStore":
        store = cls(project, read_only=read_only)
        try:
            store._open()
        except BaseException:
            store.close()
            raise
        return store

    @property
    def _db(self) -> sqlite3.Connection:
        if self._connection is None:
            raise _error("static.closed", "静态观察库已关闭。")
        return self._connection

    def _open(self) -> None:
        if self.read_only and not self.database.is_file():
            raise _error("static.store_missing", "找不到静态观察库。")
        existed = self.database.exists()
        try:
            initialized = existed and self.database.stat().st_size > 0
        except OSError:
            initialized = False
        try:
            connection = sqlite3.connect(
                self.database.as_uri() + "?mode=ro" if self.read_only else str(self.database),
                uri=self.read_only,
                timeout=5.0,
                autocommit=True,
            )
        except sqlite3.Error as error:
            raise _error("static.database", "无法打开静态观察库。") from error
        self._connection = connection
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            if self.read_only:
                connection.execute("PRAGMA query_only=ON")
                self._validate_schema()
            else:
                connection.execute("PRAGMA synchronous=FULL")
                if initialized:
                    with self._transaction():
                        self._validate_schema()
                else:
                    self._create_schema()
            if self.database.resolve().parent != self.project:
                raise _path_error()
        except AppError:
            raise
        except sqlite3.Error as error:
            raise _error("static.database", "无法校验静态观察库。") from error

    def _create_schema(self) -> None:
        with self._transaction():
            row = self._db.execute("PRAGMA user_version").fetchone()
            version = 0 if row is None else row[0]
            if version == _STORE_USER_VERSION:
                self._validate_schema()
                return
            if version != 0:
                raise _schema_error()
            tables = self._db.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
            if tables is not None and tables[0]:
                raise _schema_error()
            self._db.execute(f"PRAGMA user_version={_STORE_USER_VERSION}")
            for statement in _SCHEMA_STATEMENTS:
                self._db.execute(statement)
            self._db.execute(
                "INSERT INTO static_meta (key,value) VALUES ('schema_version',?)",
                (STATIC_STORE_SCHEMA_VERSION,),
            )
            self._validate_schema()

    def _validate_schema(self) -> None:
        try:
            row = self._db.execute("PRAGMA user_version").fetchone()
            version = 0 if row is None else row[0]
            if version != _STORE_USER_VERSION:
                raise _schema_error()
            meta = self._db.execute(
                "SELECT value FROM static_meta WHERE key='schema_version'"
            ).fetchone()
            if meta is None or meta[0] != STATIC_STORE_SCHEMA_VERSION:
                raise _schema_error()
            for table, required in _REQUIRED_COLUMNS.items():
                columns = {
                    cast(str, item[1]) for item in self._db.execute(f"PRAGMA table_info({table})")
                }
                if not required <= columns:
                    raise _schema_error()
            integrity = self._db.execute("PRAGMA integrity_check").fetchall()
            if len(integrity) != 1 or integrity[0][0] != "ok":
                raise _integrity_error()
        except AppError:
            raise
        except sqlite3.Error as error:
            raise _schema_error() from error

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.read_only:
            raise _error("static.read_only", "静态观察库以只读方式打开。")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def _collection_row(self, run_id: str, collection_id: str) -> sqlite3.Row | None:
        row = self._db.execute(
            "SELECT * FROM static_collections WHERE run_id=? AND collection_id=?",
            (run_id, collection_id),
        ).fetchone()
        return None if row is None else cast(sqlite3.Row, row)

    def _insert_collection(self, artifact: StaticCollectionArtifact) -> None:
        package = artifact.package
        self._db.execute(
            """
            INSERT INTO static_collections (
                run_id, collection_id, schema_version, media_id, source_sha256,
                config_hash, pipeline_version, pipeline_hash, provenance_json,
                canonical_payload, package_sha256, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                package.run_id,
                package.collection_id,
                package.schema_version,
                package.media_id,
                package.source_sha256,
                package.config_hash,
                package.pipeline_version,
                package.pipeline_hash,
                canonical_provenance_json(package.provenance),
                artifact.canonical_payload,
                artifact.package_sha256,
                datetime.now(UTC).isoformat(),
            ),
        )

    def _insert_records(self, artifact: StaticCollectionArtifact) -> None:
        self._db.executemany(
            """
            INSERT INTO static_observations (
                run_id, collection_id, observation_id, local_observation_id,
                evidence_id, source_time_us, image_sha256, artifact_path,
                source_path, observation_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                (
                    artifact.package.run_id,
                    artifact.package.collection_id,
                    record.observation_id,
                    record.local_observation_id,
                    record.evidence_id,
                    record.source_time_us,
                    record.image_sha256,
                    record.artifact_path,
                    record.source_path,
                    record.observation_json,
                )
                for record in artifact.records
            ),
        )

    def publish(self, artifact: StaticCollectionArtifact) -> PublishStatus:
        if self.read_only:
            raise _error("static.read_only", "静态观察库以只读方式打开。")
        try:
            with self._transaction():
                existing = self._collection_row(
                    artifact.package.run_id, artifact.package.collection_id
                )
                if existing is not None:
                    self._load_collection(artifact.package.run_id, artifact.package.collection_id)
                    if _text(existing["package_sha256"]) != artifact.package_sha256:
                        raise _error(
                            "static.collection_conflict",
                            "该集合已保存不同内容；请使用新的 collectionId。",
                        )
                    return "unchanged"
                self._insert_collection(artifact)
                self._insert_records(artifact)
                self._load_collection(artifact.package.run_id, artifact.package.collection_id)
                return "created"
        except AppError:
            raise
        except sqlite3.IntegrityError as error:
            raise _error("static.constraint", "静态观察库约束拒绝该集合。") from error
        except sqlite3.Error as error:
            raise _error("static.database", "静态观察库写入失败。") from error

    def load_collection(self, run_id: str, collection_id: str) -> StoredStaticCollection:
        try:
            return self._load_collection(run_id, collection_id)
        except AppError:
            raise
        except sqlite3.Error as error:
            raise _error("static.database", "静态观察库读取失败。") from error

    def _load_collection(self, run_id: str, collection_id: str) -> StoredStaticCollection:
        row = self._collection_row(run_id, collection_id)
        if row is None:
            raise _error("static.collection_missing", "找不到指定的静态观察集合。")
        payload = _text(row["canonical_payload"])
        stored_pipeline_hash = None if row["pipeline_hash"] is None else _text(row["pipeline_hash"])
        try:
            package = loads_static_package(payload.encode("utf-8"))
        except UnsupportedStaticSchema as error:
            raise _error("static.schema_unsupported", "静态观察库包含不支持的声明版本。") from error
        except (ValueError, UnicodeError) as error:
            raise _integrity_error() from error
        if (
            package.run_id != run_id
            or package.collection_id != collection_id
            or package.schema_version != _text(row["schema_version"])
            or package.media_id != _text(row["media_id"])
            or package.source_sha256 != _text(row["source_sha256"])
            or package.config_hash != _text(row["config_hash"])
            or package.pipeline_version != _text(row["pipeline_version"])
            or package.pipeline_hash != stored_pipeline_hash
            or canonical_provenance_json(package.provenance) != _text(row["provenance_json"])
            or canonical_package_json(package) != payload
            or package_sha256(package) != _text(row["package_sha256"])
            or hashlib.sha256(payload.encode("utf-8")).hexdigest() != _text(row["package_sha256"])
        ):
            raise _integrity_error()
        rows = cast(
            list[sqlite3.Row],
            self._db.execute(
                "SELECT * FROM static_observations WHERE run_id=? AND collection_id=? "
                "ORDER BY observation_id",
                (run_id, collection_id),
            ).fetchall(),
        )
        if len(rows) != len(package.observations):
            raise _integrity_error()
        records_by_id: dict[str, StaticObservationRecord] = {}
        for item in rows:
            record = StaticObservationRecord(
                _text(item["observation_id"]),
                _text(item["local_observation_id"]),
                _text(item["evidence_id"]),
                _time_us(item["source_time_us"]),
                _hash(item["image_sha256"]),
                _path_text(item["artifact_path"]),
                _path_text(item["source_path"]),
                _text(item["observation_json"]),
            )
            if record.observation_id in records_by_id:
                raise _integrity_error()
            records_by_id[record.observation_id] = record
        records: list[StaticObservationRecord] = []
        for observation in package.observations:
            expected_id = observation_id(package, observation)
            if expected_id not in records_by_id:
                raise _integrity_error()
            record = records_by_id.pop(expected_id)
            if (
                record.local_observation_id != observation.local_observation_id
                or record.evidence_id != observation.evidence_id
                or record.observation_json != canonical_observation_json(observation)
            ):
                raise _integrity_error()
            records.append(record)
        if records_by_id:
            raise _integrity_error()
        return StoredStaticCollection(
            run_id,
            collection_id,
            _text(row["package_sha256"]),
            payload,
            package,
            tuple(sorted(records, key=lambda item: item.observation_id)),
        )

    def close(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass
