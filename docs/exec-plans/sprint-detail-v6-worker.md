# Detail action eligibility worker — 2026-10-05

## Ownership and trigger

Isolated `.worktrees/detail-v6`, branch `codex/detail-v6`, baseline `e9183b3`.
Own only `deepseek_vision.py`, new `test_detail_action_eligibility.py`, and this
record. Root and other workers own configuration, UI, pilot and shared records;
their edits must be preserved.

Root reports V5 run `c78f204907e04eb3a2ac97a9017dcad9` reached 9/16 windows,
24 events, then window 31.5–35.5 seconds twice produced a single-frame event
with identical start/end frame. Parser correctly rejected the unsupported
temporal segment. Repeating V5 or loosening the guard would not fix the defect.

## Scope and state

Implement a separately fingerprinted V6 prompt: qualify a visible multi-frame
subject action before describing its attributes; omit single-frame appearance,
static inventory, and camera-cut-only segments while preserving other valid
actions. Add explicit boundary/evidence self-check and abstain rather than
guessing boundaries. V1–V5 prompts/behavior remain frozen. V6 uses the existing
V5 detail image profile, six-field temporal schema, fact/alias and static guards.

Implementation and focused offline verification in progress. No paid calls or
installs; root isolated tools, caches, environment and Python `-B` only.

## Resumption checkpoint

Resumed the existing three owned files without replacing earlier implementation.
Root `scripts/init.ps1 -CheckOnly` and full isolated toolchain/media checks pass.
Initial Ruff format/lint checks on the two Python files and mypy on all 43 worker
source files pass. Initial focused pytest had 1 passed/12 fixture errors because
the command did not create its independent root-cache run parent; no provider test
executed in those errored fixtures. Creating that parent fixes the invocation:
the original 13 eligibility tests pass (0.27 seconds).

Parallel read-only review found no implementation gap and recommended explicit
1281-pixel and tenth-image presend rejection coverage; those tests were added.
Root then required V6-only uncertainty self-check wording (null or nonempty string,
never false/empty/other types/extra fields), without assuming the old run's exact
invalid value. Added the wording and corresponding parser-contract regressions;
V5 text and parser acceptance remain frozen. Final verification/commit pending.

## Final offline verification and integration handoff

V6 prompt fingerprint (SHA-256):
`a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00`.
The new test pins this value and all five old hashes; V5 remains
`c64c644e9889fcfd91cc0e9a26d8bf1b9546ce73c548e6ac056a5067498ff98a`.
The preliminary V6 fingerprint changed only before paid calls, when the explicit
uncertainty self-check was added; no historical prompt bytes changed.

All commands dot-source root `scripts/env.ps1`, run root
`.venv/Scripts/python.exe -B`, and set only current-process `PYTHONPATH` to this
worker's `src`. Mypy, Ruff and unique pytest run/cache directories use root `.cache`.

- Root scaffold/full isolated toolchain/media checks: passed.
- Ruff format `--check` and lint on both owned Python files: passed.
- Default configured mypy: 49 files passed.
- Pytest `-W error` over `test_detail_action_eligibility.py`, `test_deepseek_vision.py`,
  `test_detailed_vision.py`, `test_temporal_vision.py`, `test_temporal_frame_contract.py`
  and `test_providers.py`: 264 passed, 3 deselected, 1.83 seconds. This includes
  all 21 V6 cases and existing V5 image/detail/alias and older provider regressions.

The three intentionally deselected old identity tests still assert V6 is unsupported:
`test_v5_is_new_identity_with_all_legacy_prompt_bytes_frozen`,
`test_legacy_prompt_hashes_remain_frozen_and_v3_has_independent_identity`, and
`test_all_previous_prompt_hashes_are_frozen_and_v4_has_new_identity`.
Root owns changing their unsupported-version probe to V7. Their legacy hash checks
are all repeated by the new V6 test; no old source/test file was edited here.

One attempted joint pytest invocation mistakenly listed nonexistent
`tests/test_http_transport.py`, causing no tests to run. After checking the actual
test list, the corrected suite above passed; transport behavior is covered in the
provider tests. Both this command failure and the initial fixture setup failure are
retained as verification evidence, with no change to acceptance requirements.

Ready for root integration; only the provider, new eligibility test and this record
are to be committed. Freeze the worktree after that commit and do not push.
No API, model download, installation, config/global-environment mutation or quality
claim occurred. Root runs the bounded 31.5–35.5-second real control and decides whether
to create a new full run; parser compliance remains distinct from F006/human quality.

## Follow-up

Root integrates version whitelists/config/pipeline identity and runs an independent
bounded real control. Contract tests cannot establish actual action or detail quality.
