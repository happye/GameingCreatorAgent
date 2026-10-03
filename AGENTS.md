# Repository Guidelines

## Project and source of truth

Gaming Creator Agent aims to turn local game footage and a creative brief into publishable content. The current repository is a planning and harness scaffold; no application code exists yet. Read `游戏内容创作与商业化产品总方案 V1.0.txt` before changing scope. The immediate milestone is Phase 0: local video analysis, a semantic timeline, and natural-language clip search. See `docs/product-specs/phase-0.md` and `feature_list.json` for the executable scope.

## Repository map

- `src/`: future C#/.NET CLI and processing modules; `tests/`: future automated and benchmark tests.
- `docs/design-docs/`: architecture and decisions; `docs/product-specs/`: accepted scope.
- `docs/exec-plans/`: reverse review, validation evidence, task plan, feedback, and debt; `docs/references/`: benchmark and environment rules.
- `prompts/`, `templates/`, `music/`: future versioned assets. Do not commit user footage or credentials.
- `CODEX.md`, `CLAUDE.md`, `.grok/rules/project.md`: tool adapters; shared rules live here and in `docs/`.
- `HANDOFF.md`: latest resumption snapshot; `progress.md`: historical work log.

## Environment and commands

Use Windows PowerShell. All runtimes/packages must be project-isolated: `.tools/` for portable SDKs/tools, `.venv/` for Python packages, `.cache/` for caches. Never install globally or change user/system environment. See `docs/references/isolated-environment.md`. Run `./scripts/init.ps1 -CheckOnly` for scaffold validation, `./scripts/init.ps1` for isolated prerequisites, `./scripts/test-media-spike.ps1 -Synthetic` for media smoke tests, and `./scripts/test-retrieval-score.ps1` for metric regression. There is no application build yet; planned `gamingcreator` commands remain unimplemented.

## Architecture and coding rules

Follow `docs/design-docs/architecture.md` and `phase-0-engineering-spec.md` as the implementation baseline after F000 review. Keep video bytes local by default; model providers replaceable; versioned prompts and model/cost/timing records traceable. Follow `.editorconfig` and `docs/references/coding-standards.md`; create only the active feature's modules.

## Testing and acceptance

Follow `docs/references/testing-guide.md` and `phase-0-benchmark.md`. Top-10 Useful Rate uses ten fixed slots: missing and duplicate events count zero; human-judged usable independent events count toward ≥70%. Synthetic tests and image API smoke success do not prove retrieval quality. Mark `passes: true` only after the feature criteria have recorded evidence.

## Changes, commits, and handoff

Codex, Claude Code, and Grok Build share scope, architecture, and acceptance criteria. Read `HANDOFF.md` and `feature_list.json` at session start; use `docs/references/agent-workflow.md` for ownership, worktrees, and transfer steps. Each agent handles one assigned feature; parallel work needs separate worktrees and explicit file ownership. The integrator reconciles shared state after review. Record resumable work before switching tools. Use imperative commit subjects, such as `feat(F002): add local frame extraction`; PRs link a feature and verification evidence. Never commit secrets, raw footage, generated media, or local databases.
