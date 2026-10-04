# Repository Guidelines

## Project and source of truth

Gaming Creator Agent turns local game footage and a brief into content. Phase 0 validates video analysis, a semantic timeline, and clip search. Read `游戏内容创作与商业化产品总方案 V1.0.txt`, `docs/product-specs/phase-0.md`, and `feature_list.json` before changing scope. Python provides media, local ASR, SQLite and partial analyze integration; vision acceptance and retrieval remain unfinished.

## Repository map

- `src/gamingcreator/{cli,application,domain,infrastructure}/`: four-layer Python core; `tests/test_*.py`: pytest behavior and architecture tests.
- `docs/design-docs/`: architecture and decisions; `docs/product-specs/`: accepted scope.
- `docs/exec-plans/`: reverse review, validation evidence, task plan, feedback, and debt; `docs/references/`: benchmark and environment rules.
- `prompts/`, `templates/`, `music/`: future versioned assets. Do not commit user footage or credentials.
- `CODEX.md`, `CLAUDE.md`, `.grok/rules/project.md`: tool adapters; shared rules live here and in `docs/`.
- `HANDOFF.md`: latest resumption snapshot; `progress.md`: historical work log.

## Environment and commands

Use Windows PowerShell. Keep runtimes in `.tools/`, packages in `.venv/`, and caches in `.cache/`; never install globally or change user/system configuration. `toolchain.json` pins portable uv and CPython. See `docs/references/isolated-environment.md`.

- `./scripts/setup-env.ps1`: prepare verified tools and locked dependencies; `-Offline` reuses cached archives/packages.
- `./scripts/init.ps1`: check scaffold, exact toolchain and media prerequisites; `-CheckOnly` checks scaffold.
- `./scripts/verify.ps1`: format, lint, types, pytest, and reproducible offline wheel builds.
- `./.venv/Scripts/gamingcreator.exe --help`: inspect CLI contracts.
- `./scripts/test-media.ps1 -AllLocal`: validate footage in ignored `GameVideos/`.
- `./scripts/test-storage.ps1 -AllLocal`: verify media persistence and a second process's reads.
- `./scripts/test-retrieval-score.ps1`: fixed-slot metric regression.

## Architecture and coding rules

Follow `docs/design-docs/architecture.md`, `phase-0-engineering-spec.md`, and ADR-001. Phase 0 uses Python; future UI requires a separate decision. Use four-space indentation, snake_case functions/modules and PascalCase types; Ruff formats/lints and mypy checks contracts. Keep domain independent of I/O, video bytes local, and provider versions/cost/timing traceable.

## Testing and acceptance

Follow `docs/references/testing-guide.md` and `phase-0-benchmark.md`. Top-10 Useful Rate uses ten fixed slots: missing and duplicate events count zero; human-judged usable independent events count toward ≥70%. Synthetic tests and image API smoke success do not prove retrieval quality. Mark `passes: true` only after the feature criteria have recorded evidence.

## Changes, commits, and handoff

Codex, Claude Code, and Grok Build share acceptance criteria. Read `HANDOFF.md` and the shared `docs/references/agent-workflow.md` at session start. Assign ownership; parallel writers use separate worktrees. Record verification and resumable work before transfer. Existing subjects use imperative `chore:`/`docs:`; feature commits use `feat(F002): add local frame extraction`. PRs describe behavior, link a feature and include evidence. Never commit secrets, footage, generated media or databases.
