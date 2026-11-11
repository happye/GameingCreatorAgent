# Repository Guidelines

## Project and state

Gaming Creator Agent turns local game footage and a brief into content. Scope: `游戏内容创作与商业化产品总方案 V1.0.txt`, `docs/product-specs/phase-0.md`, `feature_list.json`; route: `docs/exec-plans/accelerated-product-roadmap.md` and ADR-003 (all 51 items may be built; implementation, quality and release statuses stay separate; never mark stubs as delivered).

Read root `STATUS.md`, then `HANDOFF.md` (≤5KB overwrite snapshot). Update STATUS once at milestone or session end. `progress.md`, `assignments.md` and `docs/archive/` are history: do not append or read by default.

## Delivery discipline

- Delivery first: prioritize the agreed user outcome, not engineering activity or test counts.
- Converge: define scope, acceptance and evidence before work. Justify scope growth; defer nonblocking improvements without stopping authorized work.
- Reuse existing code, checks and records. Repeat analysis, reviews or documentation only when new evidence or changes require it.
- Validate by risk: run cheap static/contract and affected behavior checks first; broaden for demonstrated risk. Keep the Testing and safety gates below. Diagnose failures before expanding fixes or tests.
- Close the agreed verification, integration and delivery record within task scope before switching the main task. Independent parallel work remains allowed; blockers affect dependent work only. Stay autonomous within authorization; do not impose quotas on task splits, tests or time.

## Map

- `src/gamingcreator/{cli,application,domain,infrastructure,ui}/`, `tests/test_*.py`
- `docs/design-docs/`, `docs/product-specs/`, `docs/exec-plans/` (live plans), `docs/references/` (guides), `docs/archive/` (history)
- Tool adapters `CLAUDE.md`, `CODEX.md`, `.grok/rules/project.md` hold only tool-specific notes.
- Roles: one set per tool — `.claude/agents/*.md` (Claude), `.codex/agents/task_*.toml` + `harness_*.toml` (Codex). Never generate one tool's roles from another's; project rules live here, not copied into role files.

## Environment

Windows PowerShell. Runtimes `.tools/`, packages `.venv/`, caches `.cache/`; never install globally (`docs/references/isolated-environment.md`). Load `. ./scripts/env.ps1` before Python. Paid vision only through an explicitly authorized path (e.g. `run-demo.ps1 -Video`).

Write files with the editor tool, a single-quoted here-string, or Python; never PowerShell double-quoted strings (backtick escapes become control characters). Throwaway scripts go in `.cache/scratch/`.

## Code

Follow `docs/design-docs/architecture.md`, `phase-0-engineering-spec.md`, ADRs. Ruff + mypy; snake_case / PascalCase; domain has no I/O. Preserve video bytes, source clocks, provider/prompt/embedding identities and unknown costs; ordering and evidence rules: `docs/references/golden-principles.md`.

Design budget:
- Locally produced JSON: check schema version plus one whole-file hash. Field-level defenses only at paid-call, ledger and evidence boundaries.
- Keep new functions ≤80 lines. Five or more hardening commits to one file in a day means stop and record tech debt.
- A pilot ends with a one-page ADR naming the winner; delete losing paths in the same change (already-paid results stay readable).
- Reuse `infrastructure/local_files.py` helpers before writing another strict reader.

## Testing

1. Default to affected tests (`./scripts/test-affected.ps1`) or explicit failing node IDs/files. With `--lf`, use the original failure cache and `--last-failed-no-failures=none`; an empty/missing cache must never silently run everything.
2. Full `./scripts/verify.ps1` is for the end of a substantive delivery batch. Never run it per feature, local fix, commit, review or documentation update; do not rename a failure fix as a new batch.
3. If full verification fails, preserve its failing node IDs and passing evidence; repair and rerun only failures plus genuinely affected behavior. Passing targeted checks close that repair; they do not automatically trigger another full run. Test-only sampler/fixture fixes do not invalidate unrelated passing business checks.
4. A second full run in the same batch requires an explicit user instruction (`verify.ps1` enforces this via `.cache/verify-last.json`: after a failed/interrupted run it refuses until a new `feat:` commit or `-AllowRerun`). Otherwise defer it to the next substantive batch and continue authorized development; do not manufacture an approval request or use “closure / must be all green” to force a rerun.
5. Run `./scripts/verify.ps1 -Release` before distribution. Report full, targeted and interrupted results separately; never label a failed/stopped full run green because targeted repairs pass.
6. Token economy: run long checks via `./scripts/quiet.ps1 <test-affected|verify|pytest> [args]` (full log to `.cache/test-logs/`, console gets counts + failing IDs + a rerun file). Read only the failing parts of the log; never poll or re-read whole logs; never start a second pytest while one runs (shared basetemp is wiped; `quiet.ps1` refuses via `.cache/test-run.lock`).

Known failures: `xfail(strict=False, reason="TDxxx")` plus a tech-debt row. Top-10 Useful Rate: ten fixed slots, missing/duplicate count zero, ≥70% after human judgment. Mark `passes: true` only with evidence; tooling readiness is not acceptance.

## Commits

One commit = one user-visible capability or one fix, message says behavior + verification. Batch micro-edits before committing. Push at milestone end, session end or before long tasks; never force-push `main`. No docs commit just to record a SHA or push. Dashboard/node syncs ride in the feature commit; STATUS/HANDOFF once per batch end. Batch 2-4 small features, then one `test-affected -Base <batch start>` run. Parallel writers: `.worktrees/`, ≤3, one writer per tree. Never commit secrets, footage, generated media or databases.

## Cache

`.cache/` is rebuildable. Media intermediates need byte/dir/free-space budgets; FFmpeg `-fs` hit = failed render. Never reclaim models, user creations, original analysis/evidence, billing, labels or active work (`cache-maintenance-guide.md`).

## Delivery and reporting

- Primary metric: journeys in `docs/exec-plans/journeys.json`; counts from `python -B scripts/status.py`, never invented.
- Dashboard `docs/progress/`: on a node change, edit its source or `nodes.json`, run `python -B scripts/progress_ui.py`, commit both (`docs/references/progress-dashboard.md`).
- Normal progress reports require a primary metric change: ≤150 Chinese characters plus one openable artifact. Promptly report needed user decisions, additional authorization, or persistent blockers that cannot be resolved autonomously; state the impact and what is needed even when metrics are unchanged.
- Prefer milestone delivery over polishing loops; hard issues go to `docs/exec-plans/tech-debt.md`.
- Need user annotation or manual help: tell the user at once and add a row to `docs/exec-plans/human-inputs.md`. Pending items block only dependent work.
- Delegation: `development-agent-pipeline.md`, routing guides in `docs/references/`. `agent-workflow.md` covers handoff, parallel and fee mechanics.

## Fees, freeze, protections

- ¥50 monthly preauthorization for user-designated footage analysis only; every overage asks again; the hard send gate stays (`detail-billing-confirmation-guide.md`).
- Creation AI text calls (DeepSeek): user authorized on 2026-11-11 automatic calls within ¥30/month and ¥1 per video (`application/ai_budget.py`); beyond either cap ask per call. Ledger, evidence and send gate unchanged; cloud voice stays off (local voice).
- P038 and P046–P051 were unfrozen on 2026-11-03 by the user after the third J1 trial; real platform publishing, payments and paid calls still need their own explicit approval.
- Paid calls gated; evidence and ledgers immutable; no automatic re-pay or re-label; the toolchain check may narrow but not be removed; harness work never flips `passes` or delivery statuses.
