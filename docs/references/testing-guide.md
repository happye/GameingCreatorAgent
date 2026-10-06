# Testing and benchmark guide

Run `./scripts/setup-env.ps1`, then `./scripts/verify.ps1`. F001 pins pytest 9.1.1, Ruff 0.16.10 and mypy 2.4.0 in `uv.lock`. Verification checks source formatting/lint, strict types for source and Provider fake implementations, import direction, behavior tests, CLI entry points and two matching offline wheel builds. All caches/output stay under `.cache`.

For focused checks, dot-source `./scripts/env.ps1` and use `./.venv/Scripts/python.exe -B -m pytest tests/test_cli.py`, `-B -m ruff check src tests`, `-B -m ruff format --check src tests`, or `-B -m mypy`. Tests assert input contracts, source-time bounds, cancellation and unknown cost semantics. `tests/test_media_integration.py` (marker `media`) generates local video fixtures; Job/process tests verify Windows descendants, pipe draining and handle cleanup. Missing FFmpeg skips media tests and cannot prove F002. No ordinary test calls a real model.

Add domain/input unit tests, FFmpeg/SQLite integration tests and CLI smoke tests when commands exist. Use `tests/test_<module>.py` or mirrored subdirectories and behavior names such as `test_search_returns_source_intervals_for_mechanic_query`. Integration tests using real models are explicitly selected, never silently paid during ordinary unit runs. No percentage coverage target is set; failure behavior and declared feature criteria determine required checks.

F004 uses `test_sqlite_schema.py`, `test_writer_lock.py`, `test_sqlite_store.py` and `test_storage_process.py`: real process reload/crash, atomic rollback/checkpoints, same-run/media FKs, unknown versus zero billing, damaged snapshots/files, Windows junction boundaries, and cancellation-safe thread closing. `storage_process_helper.py` contains labeled storage fixtures, not model-quality evidence. `test-storage.ps1 -AllLocal` separately round-trips real F002 bundles without semantic inference.

For retrieval quality, build a local benchmark from representative game recordings. The source plan suggests 10–20 recordings; keep raw footage outside Git. Store only permitted fixture metadata and human labels. Each benchmark case should capture a query, relevant time ranges, judged results, reviewer/date, provider/model/prompt version, runtime, and cost.

Compute Top-10 Useful Rate with a fixed denominator of ten; missing and duplicate-event slots count zero. Human-judged usable/highly relevant independent events count toward the numerator. Main, sparse-positive, and negative queries are frozen before inference and reported separately. Follow [phase-0-benchmark.md](./phase-0-benchmark.md) for full contracts and executable metric regression. Track timecode errors and false positives; report every query rather than hiding failures in an aggregate.

Do not mark a feature passed because code compiles alone. Attach the feature's test evidence to `progress.md` or a sprint evaluation file.

Temporal checks cover legacy fingerprints, frame alias boundaries, ordered/different evidence, config persistence and window resumption; real bounded comparisons use `scripts/validate-temporal-gameplay.py` (only `--execute` calls the paid provider). A refused static hallucination demonstrates validation, not a successful model negative control. `test_workspace_launcher.py` runs real Windows CMD/PowerShell service start/reuse/concurrency/foreign-port/failed-start cleanup with `-NoBrowser`, project-only logs and no paid calls. Browser smoke can specify `--query`; its three-candidate basket fixture does not require every gameplay query to return three results.

The CLI demo's historical verification and real-video evidence are in `sprint-demo.md`; workspace results are in `sprint-inspection-workspace.md` and the latest layout/ordering checks in `sprint-workspace-usability.md`. `test_analyze_v2.py` covers partial window recovery, presend ASR identity and unknown-charge consent; `test_search_cli.py` covers nullable audio-only candidates and unverified billing. `test_retrieval_persistence.py` covers schema3 vector identity, foreign keys and transaction rollback. Run `scripts/validate-demo.py --project <project> --run <completed-run>` explicitly for offline real-model comparisons and another process's reads; it makes no paid requests and keeps the human gate null for unlabelled inputs.

`test_inspection_http.py` covers registered media/evidence, relative URL identity, Range/HEAD/416, file changes, valid HTTP errors, project/database boundaries and unknown costs. The real file-symlink check may skip on Windows without symlink privilege; a separate portable canonical-path regression still runs. Check the actual skip reason.

Browser validation is opt-in and needs the locked `ui-test` extra. On a prepared repository:

`test_detail_pilot_review.py` checks the exact frozen record anchors, independent nullable judgments, absent-result barriers, original-input preservation and new-directory protection. Its real file:// browser cases cover blank and saved fixture results, actual download/load, duplicate-key refusal and preserving the form after invalid input. Actual-source smoke records six-frame hashes/dimensions and keeps all new real judgments empty; neither fixture success nor a saved record passes F006.

```powershell
. ./scripts/env.ps1
./.tools/uv/uv.exe --no-config sync --locked --extra asr --extra retrieval --extra ui-test --python ./.venv/Scripts/python.exe --no-python-downloads
./.venv/Scripts/python.exe -B -m playwright install chromium
./.venv/Scripts/python.exe -B scripts/validate-inspection-ui.py --project artifacts/demo-phase0 --run f76f5d6495314c04ae04083614d4afd6
```

Tools stay in `.venv`/`.tools/browsers`; temporary profiles use project TEMP. The script starts its own loopback server, checks real playback/seek, images, filter isolation, empty negative search, chronological basket/storage/JSON/CSV, deep-list scroll preservation, desktop 1440×900/1366×768 geometry and mobile overflow, and writes ignored `artifacts/inspection-ui-validation/`. Add `--query "Find clips of fighters attacking each other in the arena" --output artifacts/inspection-ui-validation-english` for the English smoke. Existing source files, database and local E5 weights are required. No analysis or paid API occurs. Browser success and selected clips do not pass F006.
