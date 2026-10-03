# Codex Project Guide

Read [AGENTS.md](./AGENTS.md) first; it is the repository-wide source of truth. This file records only Codex-specific working steps.

1. Confirm the working directory, inspect `git status`, then read `HANDOFF.md` and `feature_list.json`. Follow `docs/references/agent-workflow.md` for assignment and cross-tool handoff. Do not overwrite unrelated work.
2. Choose one assigned unfinished feature. Read the F000 reverse review and Phase 0 engineering baseline before implementation; use the handoff to determine which feature is next.
3. Write a short sprint proposal in `docs/exec-plans/` with acceptance checks. Implement only the accepted feature and run relevant checks. Use the review template in `docs/exec-plans/sprint-template.md`; separate planning and evaluation passes are sufficient when no other agent is assigned.
4. Record actual commands, outcomes, limitations, and the next action in the assigned sprint record. For sequential work, update `HANDOFF.md` and `progress.md`; for parallel work, let the integrator reconcile these shared files. Set `passes: true` only when the feature's `test_criteria` is met.
5. Keep decisions and evidence in repository files so a new Codex session can resume from them. Review stale links and technical debt when touching related areas.

Codex discovers `AGENTS.md` natively; this file is linked guidance, not an assumed native configuration filename. Current status and environment findings belong in `HANDOFF.md`.
