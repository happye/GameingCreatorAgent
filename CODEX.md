# Codex Project Guide

Read [AGENTS.md](./AGENTS.md) first; it is the repository-wide source of truth. This file records only Codex-specific working steps.

1. Confirm the working directory, inspect `git status`, then read `progress.md` and `feature_list.json`. Do not overwrite unrelated work.
2. Choose one unfinished feature. For the first development feature, finish F000's critical review of the product plan before committing to an implementation design.
3. Write a short sprint proposal in `docs/exec-plans/` with acceptance checks. Implement only the accepted feature and run relevant checks. Use the review template in `docs/exec-plans/sprint-template.md`; separate planning and evaluation passes are sufficient when no other agent is assigned.
4. Record actual commands, outcomes, limitations, and the next feature in `progress.md`. Set `passes: true` only when the feature's `test_criteria` is met.
5. Keep decisions and evidence in repository files so a new Codex session can resume from them. Review stale links and technical debt when touching related areas.

Current project state: the harness exists, but the CLI, tests, SDK-based build, and benchmark do not. `./scripts/init.ps1 -CheckOnly` validates only the scaffold. Do not describe the planned `gamingcreator` commands as working until implemented.
