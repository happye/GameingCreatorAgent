# F006 worker checkpoint — 2026-10-04

Owner: Codex benchmark worker; branch `codex/demo-benchmark`, worktree `.worktrees/demo-benchmark`. Root integrates CLI/SQLite verification/retrieval. Other agents own other files; this worker does not modify shared handoff, feature flags or dependencies.

## Delivered contract

- Pure application benchmark runner with strict manifest v1, separate human references/candidate judgments, exact reviewed ranges, source/run identity metadata and explicit human confirmation/freeze/independence declarations.
- Fixed ten-slot scoring, independent human event deduplication, grades 0..3 with 2/3 useful, no eleventh-slot refill; main references require at least ten independent useful events. Sparse and negative groups remain separate.
- Injectable async search and media verifier; all query results, failures, misses, timing and endpoint errors recorded. Missing labels, unverified sources, failed query, or undeclared independent set cannot produce a passing quality gate. Unknown costs remain null.
- Unlabelled example and schema/integration guide. No fake human data generated for real acceptance. Tests use explicitly synthetic contract fixtures only.

## Verification checkpoint

Focused verification passed using root `.venv`, process-only `PYTHONPATH` pointing at this worktree, and distinct root-project cache/tmp directories:

- Ruff format/check: application and test files pass.
- Strict mypy: two source files pass.
- `pytest -W error tests/test_benchmark.py`: 49 passed, zero skips, 0.13s. Covers 7/10, 1/10, duplicate IDs/human groups, eleventh-slot exclusion, strict JSON/int/grade contracts, missing labels, source/run checks, failures, sparse/negative groups, timestamp validation, boundary changes and unknown/full cold/hot cost.

No packages installed and no API keys or paid requests used. Full repository verification and live CLI benchmark are integration-owner work, not claimed by this worker.

Example local verification (from this worktree, after `. ../../scripts/env.ps1`):

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& ../../.venv/Scripts/python.exe -B -m pytest -W error tests/test_benchmark.py --basetemp=../../.cache/pytest-demo-benchmark-001 -o cache_dir=../../.cache/pytest-cache-demo-benchmark
& ../../.venv/Scripts/python.exe -B -m mypy --cache-dir ../../.cache/mypy-demo-benchmark src/gamingcreator/application/benchmark.py tests/test_benchmark.py
```

## Integration tasks outside worker ownership

Root wires CLI `benchmark` using `loads_manifest`, maps retrieval results to `BenchmarkHit`, verifies source/run identity and source hash via SQLite, supplies recorded model/config metadata and full cold/hot attempt accounting when known. Report emission and CLI exit code handling belong to root. F006 remains unverified until independent frozen human footage/labels and actual query results meet the existing acceptance criteria.
