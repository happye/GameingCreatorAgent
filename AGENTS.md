# Repository Guidelines

## Project and state

Gaming Creator Agent turns local game footage and a brief into content. Scope: `游戏内容创作与商业化产品总方案 V1.0.txt`, `docs/product-specs/phase-0.md`, `feature_list.json`; route: `docs/exec-plans/accelerated-product-roadmap.md` and ADR-003 (all 51 items may be built; implementation, quality and release statuses stay separate; never mark stubs as delivered).

Read root `STATUS.md`, then `HANDOFF.md` (≤5KB overwrite snapshot). Update STATUS once at milestone or session end. `progress.md`, `assignments.md` and `docs/archive/` are history: do not append or read by default.

## Map

- `src/gamingcreator/{cli,application,domain,infrastructure,ui}/`, `tests/test_*.py`
- `docs/design-docs/`, `docs/product-specs/`, `docs/exec-plans/` (live plans), `docs/references/` (guides), `docs/archive/` (history)
- Tool adapters `CLAUDE.md`, `CODEX.md`, `.grok/rules/project.md` hold only tool-specific notes; roles in `.claude/agents/`, `.codex/agents/`.

## Environment

Windows PowerShell. Runtimes `.tools/`, packages `.venv/`, caches `.cache/`; never install globally (`docs/references/isolated-environment.md`). Load `. ./scripts/env.ps1` before Python. Script usage lives in each script header and `docs/references/`. Paid vision only through an explicitly authorized path (e.g. `run-demo.ps1 -Video`).

Write files with the editor tool, a single-quoted here-string, or Python; never PowerShell double-quoted strings (they turn `` `a `` `` `f `` `` `t `` into control characters). Throwaway scripts go in `.cache/scratch/`.

## Code

Follow `docs/design-docs/architecture.md`, `phase-0-engineering-spec.md`, ADRs. Ruff + mypy; snake_case / PascalCase; domain has no I/O. Preserve video bytes, source clocks, provider/prompt/embedding identities and unknown costs; ordering and evidence rules: `docs/references/golden-principles.md`.

Design budget:
- Locally produced JSON: check schema version plus one whole-file hash. Field-level defenses only at paid-call, ledger and evidence boundaries.
- Keep new functions ≤80 lines. Five or more hardening commits to one file in a day means stop and record tech debt.
- A pilot ends with a one-page ADR naming the winner; delete losing paths in the same change (already-paid results stay readable).
- Reuse `infrastructure/local_files.py` helpers before writing another strict reader.

## Testing

1. Iterate with `./scripts/test-affected.ps1` (affected tests only; browser/local_data excluded unless UI changed).
2. Run `./scripts/verify.ps1` (full suite) at milestone end or before merge.
3. Run `./scripts/verify.ps1 -Release` before distribution.

Known failures: `xfail(strict=False, reason="TDxxx")` plus a tech-debt row. Top-10 Useful Rate: ten fixed slots, missing/duplicate count zero, ≥70% after human judgment. Mark `passes: true` only with evidence; tooling readiness is not acceptance.

## Commits

One commit = one user-visible capability or one fix, message says behavior + verification. Batch micro-edits before committing. Push at milestone end, session end or before long tasks; never force-push `main`. No docs commit just to record a SHA or push. Parallel writers: `.worktrees/`, ≤3, one writer per tree. Never commit secrets, footage, generated media or databases.

## Cache

`.cache/` is rebuildable. Media intermediates need byte/dir/free-space budgets; FFmpeg `-fs` hit = failed render. Never reclaim models, user creations, original analysis/evidence, billing, labels or active work (`cache-maintenance-guide.md`).

## Delivery and reporting

- Primary metric: end-to-end journeys in `docs/exec-plans/journeys.json`. Counts come from `python -B scripts/status.py`; never invent them.
- Report to the user only when a primary metric changes: ≤150 Chinese characters plus one openable artifact.
- Prefer milestone delivery over polishing loops; hard issues go to `docs/exec-plans/tech-debt.md`.
- Need user annotation or manual help: tell the user at once and add a row to `docs/exec-plans/human-inputs.md`. Pending items block only dependent work.
- Delegation: `development-agent-pipeline.md`, routing guides in `docs/references/`. `agent-workflow.md` covers handoff, parallel and fee mechanics.

## Fees, freeze, protections

- ¥50 monthly preauthorization for user-designated footage analysis only; every overage asks again; the hard send gate stays (`detail-billing-confirmation-guide.md`).
- P038 and P046–P051 stay frozen until journey J1 (玩法展示) is human-evaluated.
- Paid calls gated; evidence and ledgers immutable; no automatic re-pay or re-label; the toolchain check may narrow but not be removed; harness work never flips `passes` or delivery statuses.
