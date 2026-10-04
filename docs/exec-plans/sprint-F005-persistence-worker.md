# F005 SQLite persistence worker — 2026-10-04

Owner: Codex benchmark worker, follow-up persistence task. Worktree `.worktrees/demo-benchmark`, branch `codex/demo-benchmark`. This worker owns only `infrastructure/sqlite_schema.py`, `infrastructure/retrieval_persistence.py`, `tests/test_retrieval_persistence.py` and this checkpoint. Root owns store wrappers, CLI, existing test expectation updates, shared specifications and feature acceptance.

## Implemented

Schema version 3 adds four STRICT tables: `embeddings`, `retrieval_runs`, `retrieval_hits`, and `retrieval_hit_evidence` (13 tables total). Historical v1 DDL and v2 ALTER stay immutable. Existing v1/v2 databases are validated before atomic upgrade; read-only older databases require a writer migration. Migration 3 failure rolls back tables, indexes, triggers, history and prior data.

Embedding uniqueness includes run, subject kind/ID, provider, model, revision scope, dimension, normalization and text hash. Event/evidence subjects have composite run/media FKs. Identity-only rows retain `vector_json: NULL`; real vectors can fill them later, without silently replacing an existing vector. Dimensions, numeric/finite values and declared L2 normalization are validated; loading checks identity hashes and exact spaces. Unresolved model revisions remain run-isolated.

Retrieval records preserve query/hash, version, parameters, embedding-space identity, elapsed milliseconds, result JSON and final ranks/candidates/source intervals/scores. Visual hits link to semantic events in the same analysis run/media; evidence must both belong to the hit's event and remain in its run/media. Unbound transcript candidates retain `event_id: None` and their real audio evidence; the helper requires same-run/media audio overlapping the returned half-open source interval. It does not fabricate semantic events. A separate nonnullable hit/run/media FK and NULL-safe event checks prevent nullable event IDs bypassing evidence ownership. Source-duration triggers apply to hit insert/update and media shrink. Retrieval and embedding writes require a Completed analysis. Payloads store no media BLOBs.

## Owner-thread integration

All functions receive the store's existing `sqlite3.Connection`. Write functions require an active owner transaction and enabled FKs, use a savepoint for compound writes, and never open a connection or commit the outer transaction. Store wrappers should call `_writer()` and `_transaction()` inside `_call()`. Do not call `_mutable(run_id)`, because Completed analysis content remains immutable while separate retrieval audit rows may be appended.

```python
retrieval_id = persist_retrieval(
    connection,
    run_id,
    query=query,
    retrieval_version=version,
    parameters=parameters,
    elapsed_ms=elapsed_ms,
    hits=tuple_of_PersistedRetrievalHit,
    result_json=actual_result_json,
    embedding_space=provider.space,  # None for lexical-only search
)
```

`PersistedRetrievalHit(rank, candidate_id, event_id, start_us, end_us, score, score_kind, evidence_ids)` requires contiguous final ranks and nonempty unique evidence IDs. `event_id` is `str | None`; a transcript-only hit can use None with actual overlapping audio evidence. Empty overall results remain valid. Normalized hit rows are authoritative; the original result JSON is retained for diagnostics.

`persist_embedding_identity(connection, run_id, *, subject_id, space, text_hash, subject_kind='event')` records actual identity without inventing vector values. `persist_embedding(connection, run_id, embedding, *, subject_kind='event')` writes available vectors. `load_embeddings(connection, run_id, space, *, subject_kind='event')` excludes identity-only rows and other spaces. `load_retrieval(connection, retrieval_id)` returns provenance, original JSON and normalized hits.

The wrapper must validate actual source/file integrity using `load_completed_timeline` before search and persistence; these helpers additionally enforce Completed status and relational/source-range invariants.

## Verification and handoff

Root `.venv`, worktree-only process `PYTHONPATH`, project caches/tmp, no installation or paid request. Ruff format/check and strict mypy of schema/helper/tests pass. `pytest -W error tests/test_retrieval_persistence.py tests/test_sqlite_store.py tests/test_architecture.py`: **71 passed, zero skips, 3.44s**; 47 are new persistence regressions. Covered actual separate-connection reads, v1/v2 migration, read-only refusal, atomic rollback, all space uniqueness fields, unknown vector values, vector identity/integrity, event/evidence FKs, caller transaction ownership and failed-second-hit rollback. Nullable transcript cases preserve real audio and reject images, cross-run audio, nonoverlap and exact boundary touches.

Root must update older tests' hardcoded latest version/history/table count: version 3, migrations 1/2/3, 13 STRICT tables; the next unsupported version is 4. This worker did not modify those tests. Full integrated verification and process tests remain root work. F005/F006 acceptance flags remain root decisions; these tests do not establish real retrieval quality.

Files are frozen and ready for root integration; no worker Git commit was made. Root saves the integrated checkpoint.
