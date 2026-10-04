# Gaming Creator Agent

Version repository: [happye/GameingCreatorAgent](https://github.com/happye/GameingCreatorAgent), branch `main`. Keep media, keys, virtual environments, and runtime caches outside tracked files.

This repository is the starting point for a local-first game-content creation tool. The source plan is [`游戏内容创作与商业化产品总方案 V1.0.txt`](./游戏内容创作与商业化产品总方案%20V1.0.txt). The first milestone validates whether a semantic timeline can find useful moments in local game footage before a desktop UI or commercial system is built.

## Current state

F000 review, F001 core, F002 media preprocessing and F004 SQLite persistence are accepted. The package provides CLI/Provider contracts, source-time evidence, Windows process cleanup, atomic checkpoints, per-attempt billing records and integrity recovery. Local ASR, vision budgeting, and analyze resume from completed checkpoints are wired. Retrieval is not implemented, and F003 stays unaccepted. The real Phase 0 quality gate is unmeasured. Phase 0 uses Python, SQLite and FFmpeg; see the [language decision](./docs/design-docs/adr-001-phase-0-language.md). The later desktop UI remains undecided.

## Start here

1. Read [`AGENTS.md`](./AGENTS.md), [`HANDOFF.md`](./HANDOFF.md), and the [shared workflow](./docs/references/agent-workflow.md). Open the same repository or your assigned worktree in whichever tool is available.
2. In PowerShell, run `./scripts/init.ps1 -CheckOnly` to verify scaffold files and `feature_list.json`.
3. Run `./scripts/setup-env.ps1` to download hash-pinned portable uv/CPython and synchronize `uv.lock` into `.venv`. Use `-Offline` only when archives and packages are cached. Run `./scripts/init.ps1` to check exact tools and the separately prepared local FFmpeg. Follow the [isolated environment rules](./docs/references/isolated-environment.md); everything stays inside `.tools/`, `.venv/`, and `.cache/`.
4. Resume your assigned task; review the [reverse review](./docs/exec-plans/reverse-review-2026-10-03.md), [engineering specification](./docs/design-docs/phase-0-engineering-spec.md), and [task dependencies](./docs/exec-plans/phase-0-plan.md). Record ownership and preserve a concrete handoff.

Run `./scripts/verify.ps1` for Ruff, strict mypy, pytest (warnings are errors), import boundaries, CLI smoke and two identical offline wheel builds. Media integration tests need the pinned local FFmpeg and otherwise skip; inspect skip counts. Details: [F001](./docs/exec-plans/sprint-F001.md), [F002](./docs/exec-plans/sprint-F002.md).

F004 evidence is in [sprint-F004](./docs/exec-plans/sprint-F004.md). `./scripts/test-storage.ps1 -AllLocal` round-trips real media bundles through SQLite and a separate reader process. It makes no model calls; runs explicitly require only the media stage. See [storage contracts](./docs/references/timeline-storage.md) for writer locks, recovery, and future integration.

Inspect commands with `./.venv/Scripts/gamingcreator.exe --help`. `config.example.json` defines schema v1: non-secret vision provider/model and positive request/frame limits. New analysis also requires `--max-cost-cny`; resume forbids config/budget overrides. `search` and `benchmark` still return exit 3 with `feature.not_implemented`. `analyze` runs media preprocessing, local ASR, and the DeepSeek vision budget path; without a request price snapshot it stops with `budget.estimate_missing` and does not send a paid request. F003 remains unaccepted.

## Phase 0 validation utilities

The initial technical demo runs locally without API calls: load the process environment with `. ./scripts/env.ps1`, then run `./.venv/Scripts/python.exe -B ./scripts/validate-asr.py --input "GameVideos/2025-08-17 15-26-27.mp4"`. It extracts evidence, transcribes audio and round-trips results through SQLite; the report path is printed and each case is saved immediately. Current transcripts are ungraded. A complete natural-language clip-search demo and a UI are not available yet. See the [handoff review](./docs/exec-plans/review-F003-grok-2026-10-04.md).

The [2026-10-03 validation report](./docs/exec-plans/phase-0-validation-2026-10-03.md) records real local media/DeepSeek experiments and their limits. Run `./scripts/test-media-spike.ps1 -Synthetic` for the local media smoke and `./scripts/test-retrieval-score.ps1` for fixed-denominator metric regression. `test-deepseek-vision.ps1 -SourcePath <video>` needs process-local `DEEPSEEK_API_KEY` and makes one paid request of five extracted frames. It is a limited experiment, not the final CLI or a passed retrieval benchmark.

`./scripts/test-media.ps1 -SourcePath <local-video>` runs the implemented F002 service; `-AllLocal` processes current `GameVideos/**/*.mp4`. Results remain ignored in `artifacts/media-F002/<run>/`, with PTS/timebase, piecewise WAV sample mapping, source/artifact hashes, versions and a completed manifest after validation. No model request is made. Exact stream timing metadata is required; see [media processing](./docs/references/media-processing.md) for support limits.

## Tool adapters

| Tool | Repository entry | Loading check |
| --- | --- | --- |
| Codex | Native `AGENTS.md`; linked supplement `CODEX.md` | Verify active project instructions in a new session |
| Claude Code | `CLAUDE.md` imports `AGENTS.md` | `/memory` in Claude Code |
| Grok Build | `AGENTS.md` and `.grok/rules/project.md` | `grok inspect` from the repository root |

Entry files share rules through `AGENTS.md`; live work state is in `HANDOFF.md`, per-task sprint records, and `feature_list.json`. Follow the shared workflow for separate worktrees and file ownership during parallel development.

Common resumption prompt for any of the three tools:

```text
读取 AGENTS.md、HANDOFF.md 和 feature_list.json，检查当前分支及未提交修改，按共享工作流接续已分配任务；把验证结果和下一步写入仓库交接记录。
```

The local Grok inspection currently reports `projectTrusted: false` and no loaded project instructions. On first use, handle Grok's repository trust prompt, then rerun `grok inspect`. Claude's import is configured, but its live session loading has not been tested here.

Loading behavior was checked against official documentation on 2026-10-03: [Codex project instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Claude Code imports](https://code.claude.com/docs/en/memory#import-additional-files), and [Grok project rules](https://docs.x.ai/build/features/project-rules). Local account permissions and model execution are separate from repository adapter validation.
