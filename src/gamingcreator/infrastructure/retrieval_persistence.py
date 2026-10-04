"""Retrieval writes for the existing owner's connection and transaction only."""

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import Embedding, EmbeddingSpace

SubjectKind = Literal["event", "evidence"]
MAX_SOURCE_US = (1 << 63) - 1


def _text(value: object) -> str:
    if type(value) is not str or not value.strip() or len(value) > 1_048_576:
        raise ValueError("Retrieval text must be a nonempty bounded string.")
    return value


def _integer(value: object, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_SOURCE_US:
        raise ValueError("Retrieval time/rank must be an uncoerced Int64 integer.")
    return value


def _number(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("Retrieval score/timing must be finite numeric values.")
    number = float(cast(int | float, value))
    if not math.isfinite(number):
        raise ValueError("Retrieval score/timing must be finite numeric values.")
    return number


def _hash(value: object) -> str:
    result = _text(value)
    if re.fullmatch(r"[0-9a-f]{64}", result) is None:
        raise ValueError("Embedding text hash must be lowercase SHA256.")
    return result


def _space(space: EmbeddingSpace) -> None:
    if not isinstance(space, EmbeddingSpace):
        raise ValueError("Embedding space must be a typed identity.")
    _text(space.provider)
    _text(space.model)
    _text(space.revision_scope)
    _integer(space.dimension, 1)
    if space.normalization not in ("none", "l2"):
        raise ValueError("Unknown vector normalization.")


def _vector_values(
    subject_id: str, space: EmbeddingSpace, vector: tuple[float, ...], text_hash: str
) -> tuple[float, ...]:
    checked = Embedding(subject_id, space, vector, text_hash)
    normalized = tuple(_number(value) for value in checked.vector)
    if space.normalization == "l2":
        norm = math.hypot(*normalized)
        if norm != 0 and not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
            raise ValueError("L2 embedding values must match their declared normalization.")
    return normalized


def _json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise ValueError("Retrieval metadata must be a JSON object.")
    return cast(dict[str, object], value)


def _completed(connection: sqlite3.Connection, run_id: str) -> tuple[str, int]:
    row = connection.execute(
        "SELECT r.media_id, r.status, m.duration_us FROM analysis_runs r "
        "JOIN media_assets m ON r.media_id = m.media_id WHERE r.run_id = ?",
        (_text(run_id),),
    ).fetchone()
    if row is None:
        raise AppError("storage.run_missing", "检索分析运行不存在。", ExitCode.STORAGE, run_id)
    if row[1] != "completed":
        raise AppError(
            "storage.run_incomplete", "检索只能使用已完成的分析运行。", ExitCode.STORAGE, run_id
        )
    return str(row[0]), _integer(row[2], 1)


@contextmanager
def _write(connection: sqlite3.Connection) -> Iterator[None]:
    if (
        not connection.in_transaction
        or connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1
    ):
        raise ValueError(
            "Retrieval writes require the owner's active transaction and foreign keys."
        )
    # A savepoint protects against partial writes even if an owner catches an error.
    # It neither commits nor rolls back the owner's outer transaction.
    connection.execute("SAVEPOINT gca_retrieval_write")
    try:
        yield
        connection.execute("RELEASE gca_retrieval_write")
    except BaseException:
        connection.execute("ROLLBACK TO gca_retrieval_write")
        connection.execute("RELEASE gca_retrieval_write")
        raise


@dataclass(frozen=True, slots=True)
class PersistedRetrievalHit:
    rank: int
    candidate_id: str
    event_id: str | None
    start_us: int
    end_us: int
    score: float
    score_kind: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _integer(self.rank, 1)
        _text(self.candidate_id)
        if self.event_id is not None:
            _text(self.event_id)
        _integer(self.start_us)
        _integer(self.end_us, 1)
        if self.start_us >= self.end_us:
            raise ValueError("Retrieval interval must be nonempty.")
        _number(self.score)
        _text(self.score_kind)
        if (
            not isinstance(self.evidence_ids, tuple)
            or not self.evidence_ids
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
        ):
            raise ValueError("Retrieval evidence IDs must be a nonempty unique tuple.")
        for evidence_id in self.evidence_ids:
            _text(evidence_id)


def persist_retrieval(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    query: str,
    retrieval_version: str,
    parameters: Mapping[str, object],
    elapsed_ms: float,
    hits: tuple[PersistedRetrievalHit, ...],
    result_json: Mapping[str, object],
    embedding_space: EmbeddingSpace | None = None,
    retrieval_id: str | None = None,
) -> str:
    """Append an audited search and normalized hits inside the owner's transaction.

    The caller first validates Completed timeline/file integrity through its store;
    this function additionally enforces status, relational scope and source bounds.
    Empty results are valid. Ranked rows, rather than opaque JSON, are authoritative.
    """
    query = _text(query)
    retrieval_version = _text(retrieval_version)
    elapsed = _number(elapsed_ms)
    if elapsed < 0:
        raise ValueError("Retrieval elapsed time cannot be negative.")
    parameters_text = _json(_object(dict(parameters)))
    result_text = _json(_object(dict(result_json)))
    if embedding_space is not None and not isinstance(embedding_space, EmbeddingSpace):
        raise ValueError("Retrieval embedding space must be a typed identity.")
    if embedding_space is not None:
        _space(embedding_space)
    space_text = _json(asdict(embedding_space)) if embedding_space is not None else None
    identifier = uuid4().hex if retrieval_id is None else _text(retrieval_id)
    if not isinstance(hits, tuple) or any(
        not isinstance(hit, PersistedRetrievalHit) for hit in hits
    ):
        raise ValueError("Retrieval hits must be a typed tuple.")
    if [hit.rank for hit in hits] != list(range(1, len(hits) + 1)):
        raise ValueError("Persisted ranks must match the final contiguous returned order.")
    if len({hit.candidate_id for hit in hits}) != len(hits):
        raise ValueError("Retrieval candidate IDs must be unique.")
    media_id, duration = _completed(connection, run_id)
    if any(hit.end_us > duration for hit in hits):
        raise ValueError("Retrieval hit is outside its source duration.")
    for hit in hits:
        if hit.event_id is not None:
            continue
        for evidence_id in hit.evidence_ids:
            evidence = connection.execute(
                "SELECT run_id, media_id, kind, start_us, end_us FROM evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
            if (
                evidence is None
                or evidence[0] != run_id
                or evidence[1] != media_id
                or evidence[2] != "audio"
                or evidence[4] is None
                or evidence[3] >= hit.end_us
                or evidence[4] <= hit.start_us
            ):
                raise ValueError("Transcript hits need overlapping audio evidence from their run.")
    with _write(connection):
        connection.execute(
            "INSERT INTO retrieval_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identifier,
                run_id,
                media_id,
                query,
                hashlib.sha256(query.encode("utf-8")).hexdigest(),
                retrieval_version,
                parameters_text,
                space_text,
                elapsed,
                result_text,
                datetime.now(UTC).isoformat(),
            ),
        )
        for hit in hits:
            connection.execute(
                "INSERT INTO retrieval_hits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    hit.rank,
                    hit.candidate_id,
                    hit.event_id,
                    run_id,
                    media_id,
                    hit.start_us,
                    hit.end_us,
                    hit.score,
                    hit.score_kind,
                ),
            )
            for evidence_id in hit.evidence_ids:
                connection.execute(
                    "INSERT INTO retrieval_hit_evidence VALUES (?, ?, ?, ?, ?, ?)",
                    (identifier, hit.rank, hit.event_id, evidence_id, run_id, media_id),
                )
    return identifier


def _persist_embedding(
    connection: sqlite3.Connection,
    run_id: str,
    subject_id: str,
    space: EmbeddingSpace,
    text_hash: str,
    subject_kind: SubjectKind,
    vector: tuple[float, ...] | None,
) -> str:
    subject_id = _text(subject_id)
    text_hash = _hash(text_hash)
    if subject_kind not in ("event", "evidence") or not isinstance(space, EmbeddingSpace):
        raise ValueError("Embedding must identify an event/evidence subject and typed space.")
    _space(space)
    space_values = (
        run_id,
        subject_kind,
        subject_id,
        space.provider,
        space.model,
        space.revision_scope,
        space.dimension,
        space.normalization,
        text_hash,
    )
    identifier = hashlib.sha256(_json(space_values).encode("utf-8")).hexdigest()
    vector_text = None
    if vector is not None:
        vector_text = _json(_vector_values(subject_id, space, vector, text_hash))
    media_id, _ = _completed(connection, run_id)
    with _write(connection):
        existing = connection.execute(
            "SELECT vector_json, run_id, subject_kind, subject_id, provider, model, revision_scope, "
            "dimension, normalization, text_hash FROM embeddings WHERE embedding_id = ?",
            (identifier,),
        ).fetchone()
        if existing is not None:
            if tuple(existing)[1:] != space_values:
                raise ValueError("Stored embedding identity does not match its key.")
            if vector_text is not None and existing[0] is not None and existing[0] != vector_text:
                raise ValueError(
                    "An immutable embedding identity cannot be replaced with new values."
                )
            if vector_text is not None and existing[0] is None:
                connection.execute(
                    "UPDATE embeddings SET vector_json = ? WHERE embedding_id = ?",
                    (vector_text, identifier),
                )
        else:
            connection.execute(
                "INSERT INTO embeddings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    run_id,
                    media_id,
                    subject_id,
                    subject_kind,
                    subject_id if subject_kind == "event" else None,
                    subject_id if subject_kind == "evidence" else None,
                    space.provider,
                    space.model,
                    space.revision_scope,
                    space.dimension,
                    space.normalization,
                    text_hash,
                    vector_text,
                    datetime.now(UTC).isoformat(),
                ),
            )
    return identifier


def persist_embedding_identity(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    subject_id: str,
    space: EmbeddingSpace,
    text_hash: str,
    subject_kind: SubjectKind = "event",
) -> str:
    """Record identity without inventing or requiring unavailable vector values."""
    return _persist_embedding(connection, run_id, subject_id, space, text_hash, subject_kind, None)


def persist_embedding(
    connection: sqlite3.Connection,
    run_id: str,
    embedding: Embedding,
    *,
    subject_kind: SubjectKind = "event",
) -> str:
    """Fill identity-only rows or append real vectors; never mix spaces/revisions."""
    return _persist_embedding(
        connection,
        run_id,
        embedding.subject_id,
        embedding.space,
        embedding.text_hash,
        subject_kind,
        embedding.vector,
    )


def load_embeddings(
    connection: sqlite3.Connection,
    run_id: str,
    space: EmbeddingSpace,
    *,
    subject_kind: SubjectKind = "event",
) -> tuple[Embedding, ...]:
    """Load only full vectors in one exact space; identity-only rows are omitted."""
    _completed(connection, run_id)
    _space(space)
    if subject_kind not in ("event", "evidence"):
        raise ValueError("Unknown embedding subject kind.")
    rows = connection.execute(
        "SELECT subject_id, text_hash, vector_json, embedding_id FROM embeddings WHERE run_id = ? "
        "AND subject_kind = ? "
        "AND provider = ? AND model = ? AND revision_scope = ? AND dimension = ? "
        "AND normalization = ? AND vector_json IS NOT NULL ORDER BY subject_id, text_hash",
        (
            run_id,
            subject_kind,
            space.provider,
            space.model,
            space.revision_scope,
            space.dimension,
            space.normalization,
        ),
    )
    result: list[Embedding] = []
    for row in rows:
        values = (
            run_id,
            subject_kind,
            row[0],
            space.provider,
            space.model,
            space.revision_scope,
            space.dimension,
            space.normalization,
            row[1],
        )
        if hashlib.sha256(_json(values).encode("utf-8")).hexdigest() != row[3]:
            raise ValueError("Stored embedding identity does not match its key.")
        text_hash = _hash(row[1])
        vector = _vector_values(row[0], space, tuple(json.loads(row[2])), text_hash)
        result.append(Embedding(row[0], space, vector, text_hash))
    return tuple(result)


def load_retrieval(connection: sqlite3.Connection, retrieval_id: str) -> dict[str, object]:
    """Read provenance plus normalized ranked rows, using the owner's connection."""
    row = connection.execute(
        "SELECT run_id, media_id, query, query_hash, retrieval_version, parameters_json, "
        "embedding_space_json, elapsed_ms, result_json, created_at FROM retrieval_runs "
        "WHERE retrieval_id = ?",
        (_text(retrieval_id),),
    ).fetchone()
    if row is None:
        raise AppError("storage.retrieval_missing", "检索记录不存在。", ExitCode.STORAGE)
    _completed(connection, row[0])
    hits: list[dict[str, object]] = []
    for hit in connection.execute(
        "SELECT rank, candidate_id, event_id, start_us, end_us, score, score_kind "
        "FROM retrieval_hits WHERE retrieval_id = ? ORDER BY rank",
        (retrieval_id,),
    ):
        evidence = tuple(
            link[0]
            for link in connection.execute(
                "SELECT evidence_id FROM retrieval_hit_evidence WHERE retrieval_id = ? "
                "AND rank = ? ORDER BY evidence_id",
                (retrieval_id, hit[0]),
            )
        )
        typed = PersistedRetrievalHit(
            hit[0], hit[1], hit[2], hit[3], hit[4], hit[5], hit[6], evidence
        )
        hits.append(asdict(typed))
    if hashlib.sha256(row[2].encode("utf-8")).hexdigest() != row[3]:
        raise ValueError("Stored retrieval query hash does not match.")
    return {
        "retrievalId": retrieval_id,
        "runId": row[0],
        "mediaId": row[1],
        "query": row[2],
        "queryHash": row[3],
        "retrievalVersion": row[4],
        "parameters": _object(json.loads(row[5])),
        "embeddingSpace": None if row[6] is None else _object(json.loads(row[6])),
        "elapsedMs": _number(row[7]),
        "result": _object(json.loads(row[8])),
        "createdAt": row[9],
        "hits": hits,
    }
