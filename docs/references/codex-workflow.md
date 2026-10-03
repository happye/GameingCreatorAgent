# Codex session workflow

## Start

Confirm the repository path and inspect `git status` and recent commits. Read `AGENTS.md`, `progress.md`, `feature_list.json`, and the documents for the next unfinished feature. Run `./scripts/init.ps1 -CheckOnly`; run the full prerequisite check when SDK-based development begins.

## Plan, build, evaluate

Select one feature. Write a proposal using `docs/exec-plans/sprint-template.md`, including expected output and checks. Review its fit with Phase 0 before coding. Implement it, then evaluate it against the stated acceptance criteria with actual commands and evidence. For CLI work, use fixtures and benchmark labels; browser automation and visual scoring only apply when a UI exists. A separate Codex session may review the work, but no multi-agent setup is required.

## Handoff

Update `progress.md` with what changed, what passed, what failed, and the next action. Change `feature_list.json` only when criteria pass. Keep code and documentation changes together. Make a descriptive commit when the repository is in a coherent, verified state; do not force a commit for incomplete work. Review touched links and `docs/exec-plans/tech-debt.md` before finishing.
