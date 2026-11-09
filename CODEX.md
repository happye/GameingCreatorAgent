# Codex Project Guide

Codex loads `AGENTS.md` natively; it is the shared guide. This file adds only Codex steps.

1. Read root `STATUS.md`, then short `HANDOFF.md`; check `git status` and do not overwrite unrelated work.
2. Pick one item. Write a sprint only for milestone-sized or blocked/multi-session work (`docs/references/development-agent-pipeline.md`); simple work stays single-agent.
3. Record commands and outcomes in the commit message or the named sprint; update `STATUS.md` once at milestone or session end. When a module changes a progress node, refresh the dashboard in the same commit (`docs/references/progress-dashboard.md`). Do not append `progress.md`; `assignments.md` only for parallel writers.
4. Follow the reporting rules and decision/authorization/blocker exceptions in `AGENTS.md`.
5. Tests: follow `AGENTS.md` §Testing, including its batch boundary and full-rerun prohibition. Apply the same limits after resuming a chat; use failing node IDs/affected tests for repairs. Run them via `./scripts/quiet.ps1 test-affected|verify|pytest` and read only its summary; rerun failures with its failing-IDs file; do not tail or re-read full logs between steps.
6. Routing: `docs/references/codex-agent-routing-guide.md` and `.codex/agents/*.toml`; verify execution metadata before claiming a model ran.

A role's `sandbox_mode` can be overridden by the parent session's live permissions; state read-only limits in the task.
