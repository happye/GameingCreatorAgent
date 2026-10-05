# Codex Project Guide

Read [AGENTS.md](./AGENTS.md) first; it is the repository-wide source of truth. This file records only Codex-specific working steps.

1. Confirm the working directory, inspect `git status`, then read `HANDOFF.md` and `feature_list.json`. Follow `docs/references/agent-workflow.md` for assignment and cross-tool handoff. Do not overwrite unrelated work.
2. Choose one assigned unfinished feature. Read the F000 review, Phase 0 engineering baseline and ADR-001 language decision; use the handoff to determine which feature is next. The original C# recommendation is superseded for Phase 0.
3. Write a short sprint proposal in `docs/exec-plans/` with acceptance checks. Implement only the accepted feature and run relevant checks. Use the review template in `docs/exec-plans/sprint-template.md`; separate planning and evaluation passes are sufficient when no other agent is assigned.
4. Record actual commands, outcomes, limitations, and the next action in the assigned sprint record. For sequential work, update `HANDOFF.md` and `progress.md`; for parallel work, let the integrator reconcile these shared files. Set `passes: true` only when the feature's `test_criteria` is met.
5. Keep decisions and evidence in repository files so a new Codex session can resume from them. Review stale links and technical debt when touching related areas.
6. Load the persistent reporting mode in `AGENTS.md` on every resumption. After each key change, give the user a detailed plain-language account of the resulting behavior, its usefulness, verified limits, and the next concrete action; follow the shared reporting protocol in `docs/references/agent-workflow.md`.

Codex discovers `AGENTS.md` natively; this file is linked guidance, not an assumed native configuration filename. Current status and environment findings belong in `HANDOFF.md`.
