# Sprint [feature ID]: [name]

Use a sprint file only for milestone-sized or blocked/multi-session work; simple work is recorded in the commit message.

## Goal

- Feature ID and user-visible result:
- Owned files (and worktree if parallel writers are active):
- Dependencies, fee/freeze gates:

## Acceptance

- Checks from `feature_list.json` `test_criteria`:
- Stop conditions:

## Verification

- Iterate: `./scripts/test-affected.ps1`; milestone end: `./scripts/verify.ps1`.
- Commands run and outcomes:

## Result

- Pass / fail / unverified per acceptance check, with evidence:
- Remaining work or blocker (with reproduction) and next action:

Mark `passes: true` only when the acceptance checks have evidence; tests do not replace human acceptance.
