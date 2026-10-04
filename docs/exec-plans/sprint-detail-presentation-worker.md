# Legacy observation presentation and retrieval projection

Owner: Codex detail_presentation. Date: 2026-10-05 (Asia/Hong_Kong).
Worktree `.worktrees/detail-presentation`, branch `codex/detail-presentation`.

## Scope and acceptance

Own only observation_text.py, application/retrieval.py, ui/service.py,
ui/static/app.js, test_observation_presentation.py and this sprint. Other agents
own provider, configuration and shared documents; never overwrite their work.

- Display leaked lower-case f0–f8 window aliases as neutral corresponding
  observations, without inferring times from an event's smaller evidence subset.
- Keep immutable raw events, hashes, selection validation and saved identities.
- Expose event uncertainty separately on timeline, candidates, detail and basket.
- Clean only download copies after canonical revalidation; keep evidence IDs.
- Index the human projection, never uncertainty, with retrieval identity v5.
- Reuse isolated root tools and caches with env.ps1/Python -B. No API or installs.

## Current checkpoint

Implementation written and targeted tests passing. Initial inspection found
that source rows and saved baskets shared raw facts in every display/export path. The patch adds
displayFacts; matching still compares raw observableFacts and evidence IDs.
Legacy candidate fallback refreshes display/uncertainty from the canonical
timeline event. JSON/CSV facts are projected only in a new serialization copy.

## Integration documentation required

Root must align the workspace API/manual and timeline retrieval references:
additive displayFacts, uncertainty, factsProjectionVersion; bm25-e5-rrf-v5;
JSON retains schemaVersion 1 but human observableFacts are projected, not a
byte-for-byte source-event copy. LocalStorage schema 1 and raw facts remain.
CSV adds uncertainty and factsProjectionVersion. No raw evidence IDs are hidden.
V5 profile is detailed while analysisKind remains temporal for compatibility;
menu/detail label is “细节动作（试验）”. With no preserved preference the UI
chooses Completed detailed first, then Completed temporal/legacy. Unknown
prompts and unknown client profiles degrade to ordinary frame observations.

## Verification and resumption

First targeted run: 22 passed/1 browser fixture failed (2.79s). Browser CSP
correctly forbids string evaluation; test now uses Playwright locator assertions
instead of wait_for_function expression strings. Ruff also found one unused
fixture import, now removed. A second browser fixture failed because it placed
the database beneath artifacts/fixture/project; discovery intentionally scans
artifacts/*/timeline.sqlite3 only. Fixed the fixture directory, no production
discovery change. No production CSP weakening or global change.

Latest new tests: 31 passed, 6.35s (previous baseline 24/5.15s), including real
Chromium event and candidate legacy
baskets, restored raw facts, separately displayed uncertainty, timeline and
candidate text, JSON/CSV human projections, rejecting tampered canonical
facts and Completed detail-first menu selection with failed/unknown fallbacks.
The old/new embedding hashes coexist for the same persisted event with valid
foreign keys and distinct cache identities.
The earlier cache-coexistence fixture initially omitted the owner's required
transaction and was correctly rejected; updated fixture uses existing explicit
transaction helper. This is a test setup correction, no storage bypass.

Focused legacy regression: 196 passed/1 Windows symlink permission skip/18
failed, 10.65s. All 18 failures are the same parameterized old version assertion
in test_retrieval_negation.py:127 (v4 expected, v5 actual); all candidate denial
assertions passed. Root owns the necessary assertion update; worker did not edit
the old test. After the final detail-menu changes, the same focused suite with
those 18 obsolete version assertions deselected passed 203 tests/1 permission
skip/18 deselected, 11.94s. Strict mypy on the three owned source files passed. F006/F009
unchanged. Root must run the updated version assertion/full verify after
integration; no model-quality claim follows from these tests. Final source
format, lint and strict mypy passed. Freeze after owned-file commit; no API
request, installation, runtime/global settings change or raw-event rewrite.
