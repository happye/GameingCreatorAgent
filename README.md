# Gaming Creator Agent

This repository is the starting point for a local-first game-content creation tool. The source plan is [`游戏内容创作与商业化产品总方案 V1.0.txt`](./游戏内容创作与商业化产品总方案%20V1.0.txt). The first milestone validates whether a semantic timeline can find useful moments in local game footage before a desktop UI or commercial system is built.

## Current state

The repository contains planning documents, a Codex workflow, and empty source/test directories. There is no application or test runner yet. The planned implementation uses C#/.NET, SQLite, and FFmpeg; model providers must remain replaceable.

## Start here

1. Read [`AGENTS.md`](./AGENTS.md), [`CODEX.md`](./CODEX.md), and [`docs/product-specs/phase-0.md`](./docs/product-specs/phase-0.md).
2. In PowerShell, run `./scripts/init.ps1 -CheckOnly` to verify scaffold files and `feature_list.json`.
3. Run `./scripts/init.ps1` to check prerequisites for later Phase 0 development. Install a .NET SDK and FFmpeg if the script reports they are missing.
4. Continue with F000, the technical review, in `feature_list.json`. Record progress in `progress.md`.

Build and test commands will be added after the first executable project is created.
