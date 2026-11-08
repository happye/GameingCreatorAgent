# Codex Project Guide

Codex loads `AGENTS.md` natively; it is the shared guide. This file adds only Codex steps.

1. Read root `STATUS.md`, then short `HANDOFF.md`; check `git status` and do not overwrite unrelated work.
2. Pick one item. Write a sprint only for milestone-sized or blocked/multi-session work (`docs/references/development-agent-pipeline.md`); simple work stays single-agent.
3. Record commands and outcomes in the commit message or the named sprint; update `STATUS.md` once at milestone or session end. Do not append `progress.md`; `assignments.md` only for parallel writers.
4. Follow the reporting rules and decision/authorization/blocker exceptions in `AGENTS.md`.
5. Tests: `./scripts/test-affected.ps1` while iterating; `./scripts/verify.ps1` at milestone end.
6. Routing: `docs/references/codex-agent-routing-guide.md` and `.codex/agents/*.toml`; verify execution metadata before claiming a model ran.

A role's `sandbox_mode` can be overridden by the parent session's live permissions; state read-only limits in the task.
