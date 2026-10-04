# Repository Guidelines

## Project and source of truth

Gaming Creator Agent turns local game footage and a brief into content. Phase 0's CLI analyzes footage and searches a semantic timeline; human retrieval acceptance remains pending. Read `游戏内容创作与商业化产品总方案 V1.0.txt`, `docs/product-specs/phase-0.md`, and `feature_list.json` before changing scope.

## Repository map

- `src/gamingcreator/{cli,application,domain,infrastructure}/`: four-layer Python core; `ui/`: local inspection workspace; `tests/test_*.py`: pytest behavior and architecture tests.
- `docs/design-docs/`: architecture and decisions; `docs/product-specs/`: accepted scope.
- `docs/exec-plans/`: reverse review, validation evidence, task plan, feedback, and debt; `docs/references/`: benchmark and environment rules.
- `prompts/`, `templates/`, `music/`: future versioned assets. Do not commit user footage or credentials.
- `CODEX.md`, `CLAUDE.md`, `.grok/rules/project.md`: tool adapters; shared rules live here and in `docs/`.
- `HANDOFF.md`: latest resumption snapshot; `progress.md`: historical work log.

## Environment and commands

Use Windows PowerShell. Keep runtimes in `.tools/`, packages in `.venv/`, and caches in `.cache/`; never install globally or change user/system configuration. `toolchain.json` pins portable uv and CPython. See `docs/references/isolated-environment.md`.

- `./scripts/setup-demo.ps1`: prepare isolated tools, dependencies, ASR and embedding models; `-Offline` requires cached assets.
- `./scripts/run-demo.ps1 -Run <id>`: search an existing demo; `-Video <path>` starts paid vision analysis.
- `./scripts/run-ui.ps1`: open local preview, evidence, search and interval exports.
- `./scripts/init.ps1`: check scaffold, exact toolchain and media prerequisites; `-CheckOnly` checks scaffold.
- `./scripts/verify.ps1`: format, lint, types, pytest, and reproducible offline wheel builds.
- `./scripts/test-media.ps1 -AllLocal`: validate footage in ignored `GameVideos/`.
- `./scripts/test-storage.ps1 -AllLocal`: verify media persistence and a second process's reads.

## Architecture and coding rules

Follow `docs/design-docs/architecture.md`, `phase-0-engineering-spec.md`, ADR-001 and ADR-002. Use four-space indentation, snake_case functions/modules and PascalCase types; Ruff formats/lints and mypy checks contracts. Domain excludes I/O. Preserve local video bytes, source clocks, provider/prompt/embedding identities and unknown costs. Basket/export order follows source time; retrieval keeps rank.

## Testing and acceptance

Use pytest `tests/test_*.py`; follow `docs/references/testing-guide.md` and `phase-0-benchmark.md`. Top-10 Useful Rate has ten fixed slots: missing and duplicate events count zero; independent human-judged usable events must reach ≥70%. Multi-frame inputs and index hits do not prove action understanding. Mark `passes: true` only after feature evidence. Benchmark exit 6 preserves its report when the gate fails or remains unverified.

## Changes, commits, and handoff

All agents share acceptance criteria; start with `HANDOFF.md` and `docs/references/agent-workflow.md`. Assign ownership; parallel writers use separate worktrees. Record verification and resumable work before transfer. Use imperative `chore:`/`docs:` subjects or `feat(F002): add local frame extraction`. PRs describe behavior, link a feature and include evidence. Never commit secrets, footage, generated media or databases.
