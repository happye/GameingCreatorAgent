# Temporal frame contract worker — 2026-10-04

## Ownership and purpose

Worktree: `.worktrees/temporal-frame-contract`; branch: `codex/temporal-frame-contract`.
Own only `deepseek_vision.py`, `tests/test_temporal_frame_contract.py`, and this record.
Other agents own configuration, analysis/storage wiring, experiments, old tests, and shared handoff.
No dependency installation, paid model call, or credential read occurred in this worker.

The existing real v3 call failed with `evidence_outside_range`; its original response was not
retained. This worker does not claim which endpoint was wrong. Numeric diagnostics below are
covered with synthetic responses, not a recovery of that real response.

## Contract delivered

- Added prompt `phase0-vision-v4`, schema `temporal-actions-v1`, prompt SHA-256
  `9ea350e10eb028f1f5e2dc7d355ebd1d080ad8ae8397eb709705a25773323f48`.
- V4 still has exactly six event fields: `startFrameId`, `endFrameId`, `observableFacts`,
  `mechanicTags`, `evidenceIds`, `uncertainty`. Boundary aliases identify inclusive actual
  supplied frames. The program derives `SourceRange(first.sourceUs, last.sourceUs + 1, duration)`;
  model microsecond arithmetic is no longer accepted for this prompt.
- Endpoint frames must have increasing source clocks. Citations must include both endpoints,
  remain within the selected range, and follow input order. Actions need at least two distinct
  source instants and two distinct verified image hashes. Single/static windows can abstain.
- Preserve the nine-image / three-action cap and v3's conservative actor, boss, shooting,
  jumping, camera-cut and unseen-result rules. Native-video understanding is not claimed.
- Prompt/schema mismatches fail before HTTP and budget reservation. Internal domain events,
  public source ranges, usage accounting, durable attempt registration and failures retain their
  prior contracts. V1/v2/v3 prompt text and hashes remain byte-for-byte unchanged.
- Persist schema diagnostics as `execution_details.schemaError` plus optional `schemaDetail`.
  The latter admits only `eventIndex`, `startUs`, `endUs`, `sourceUs` as signed Int64 integers,
  and `frameAlias` as `f0`–`f8`. Original model text, arbitrary alias text and credentials are
  excluded. No unsupported range is silently repaired.

## Offline verification

Used the root project's existing `.venv/Scripts/python.exe -B`, with `PYTHONPATH` set only to
this worktree's `src`; temporary files and check caches stay in this worktree's `.cache/`.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'G:/Tools/ChatGPTRepo/GameingCreatorAgent/.venv/Scripts/python.exe' -B -m pytest `
  tests/test_temporal_frame_contract.py tests/test_deepseek_vision.py tests/test_temporal_vision.py `
  -k 'not legacy_prompt_hashes_remain_frozen_and_v3_has_independent_identity' `
  --basetemp=.cache/pytest-temporal-contract
```

Result: **177 passed, 1 deselected in 1.43s**. The deselected legacy test asserted that v4
must be unsupported; root was notified to update it under its ownership when integrating v4.
Ruff check and strict mypy both passed for the two owned Python files.

Tests cover exact inclusive-alias conversion and media-end boundaries; subset citations;
image/event limits; all legacy/v4 schema mismatches; endpoint type/identity/omission/reversal;
missing endpoint citations, out-of-range or unordered citations; static/single-frame action
rejection versus abstention; unchanged previous hashes; and safe v3 failure diagnostics with
preserved usage, unknown cost and durable records. Fake transport asserts pre-registration.

## Integration and acceptance

Root must wire prompt/schema compatibility through config, analysis, store and bounded pilot
before selecting v4. Full project checks and any real API result belong to the root record.
Offline contract success does not establish gameplay action recognition or F006 acceptance.
