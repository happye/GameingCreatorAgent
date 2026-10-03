# Repository Guidelines

## Project and source of truth

Gaming Creator Agent aims to turn local game footage and a creative brief into publishable content. The current repository is a planning and harness scaffold; no application code exists yet. Read `游戏内容创作与商业化产品总方案 V1.0.txt` before changing scope. The immediate milestone is Phase 0: local video analysis, a semantic timeline, and natural-language clip search. See `docs/product-specs/phase-0.md` and `feature_list.json` for the executable scope.

## Repository map

- `src/`: future C#/.NET CLI and processing modules; `tests/`: future automated and benchmark tests.
- `docs/design-docs/`: architecture and decisions; `docs/product-specs/`: accepted scope.
- `docs/exec-plans/`: review, sprint, feedback, and debt records; `docs/references/`: development rules.
- `prompts/`, `templates/`, `music/`: future versioned assets. Do not commit user footage or credentials.
- `CODEX.md`: Codex-specific workflow; this file is the shared navigation guide.

## Environment and commands

Use Windows PowerShell. Run `./scripts/init.ps1 -CheckOnly` to validate the scaffold. Run `./scripts/init.ps1` to check Phase 0 prerequisites; it currently requires a .NET SDK and FFmpeg. This machine has .NET runtimes but no SDK. There is no runnable app, build command, test command, or configured linter yet. The planned CLI examples `gamingcreator analyze gameplay.mp4` and `gamingcreator search "建筑破坏"` are not implemented. Add exact commands here when they work.

## Architecture and coding rules

The architecture in `docs/design-docs/architecture.md` is provisional until the technical review passes. Keep video bytes local by default. Make model providers replaceable; record model, prompt version, token usage, cost, and processing time. Store platform rules as versioned data. Follow `.editorconfig` and `docs/references/coding-standards.md` when adding code; do not invent dependencies or directories beyond the active feature.

## Testing and acceptance

Follow `docs/references/testing-guide.md`. Phase 0 needs repeatable clips, queries, and human judgments. Its go/no-go target is a Top-10 Useful Rate of at least 70% for clear game-mechanic queries. Mark `passes: true` in `feature_list.json` only after the feature's stated criteria have been verified and evidence is recorded.

## Changes, commits, and handoff

Work on one feature at a time. At session start, read `progress.md`, `feature_list.json`, and relevant docs. Before implementation, record the intended behavior and checks in `docs/exec-plans/`; after implementation, record results and next steps in `progress.md`. Use concise imperative commit subjects, such as `feat(F002): add local frame extraction`. PRs should link a feature or plan section, describe verification, and include sample output or screenshots when relevant. Never commit secrets, raw footage, generated media, or local databases.
