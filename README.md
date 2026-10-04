# Gaming Creator Agent

Version repository: [happye/GameingCreatorAgent](https://github.com/happye/GameingCreatorAgent). Use the current working branch named in [`HANDOFF.md`](./HANDOFF.md); unfinished features may not be on `main`. Keep media, keys, environments, and caches outside tracked files.

This repository is the starting point for a local-first game-content creation tool. The source plan is [`游戏内容创作与商业化产品总方案 V1.0.txt`](./游戏内容创作与商业化产品总方案%20V1.0.txt). The first milestone validates whether a semantic timeline can find useful moments in local game footage before a desktop UI or commercial system is built.

## Current state

The command-line demo now analyzes local footage, stores a semantic timeline, and finds candidate clips from a natural-language query. It combines local ASR, sampled-frame DeepSeek vision, SQLite, lexical search and local multilingual E5 embeddings. F000–F005 meet their technical acceptance criteria; F006's independent human quality gate remains unverified. The integrated checks passed 557 tests with no skips, Ruff/mypy and matching offline wheel builds. There is no GUI or complete commercial content-production workflow. Phase 0 uses Python, SQLite and FFmpeg; see the [language decision](./docs/design-docs/adr-001-phase-0-language.md).

On the prepared workstation, open the existing completed demo without API calls or network access:

```powershell
./scripts/setup-demo.ps1 -Offline
./scripts/run-demo.ps1 -Run f76f5d6495314c04ae04083614d4afd6 -Query "寻找角色打斗和攻击的片段"
```

See the [demo quickstart](./docs/references/demo-quickstart.md) for new footage, explicit resume and result files. Local videos, models and the demo database are ignored and do not arrive with a Git clone.

## Start here

1. Read [`AGENTS.md`](./AGENTS.md), [`HANDOFF.md`](./HANDOFF.md), and the [shared workflow](./docs/references/agent-workflow.md). Open the same repository or your assigned worktree in whichever tool is available.
2. In PowerShell, run `./scripts/init.ps1 -CheckOnly` to verify scaffold files and `feature_list.json`.
3. Run `./scripts/setup-env.ps1` to download hash-pinned portable uv/CPython and synchronize `uv.lock` into `.venv`. Use `-Offline` only when archives and packages are cached. Run `./scripts/init.ps1` to check exact tools and the separately prepared local FFmpeg. Follow the [isolated environment rules](./docs/references/isolated-environment.md); everything stays inside `.tools/`, `.venv/`, and `.cache/`.
4. Resume your assigned task; review the [reverse review](./docs/exec-plans/reverse-review-2026-10-03.md), [engineering specification](./docs/design-docs/phase-0-engineering-spec.md), and [task dependencies](./docs/exec-plans/phase-0-plan.md). Record ownership and preserve a concrete handoff.

Run `./scripts/verify.ps1` for Ruff, strict mypy, pytest (warnings are errors), import boundaries, CLI smoke and two identical offline wheel builds. Media integration tests need the pinned local FFmpeg and otherwise skip; inspect skip counts. Details: [F001](./docs/exec-plans/sprint-F001.md), [F002](./docs/exec-plans/sprint-F002.md).

F004 evidence is in [sprint-F004](./docs/exec-plans/sprint-F004.md). `./scripts/test-storage.ps1 -AllLocal` round-trips real media bundles through SQLite and a separate reader process. It makes no model calls; runs explicitly require only the media stage. See [storage contracts](./docs/references/timeline-storage.md) for writer locks, recovery, and future integration.

Inspect commands with `./.venv/Scripts/gamingcreator.exe --help`. `config.example.json` uses schema v2: a dated CNY price snapshot, vision prompt version/content hash, output limit, sampling and ASR language. Five-frame windows overlap by one frame and cover every extracted frame. New analysis requires `--max-cost-cny` and process-local `DEEPSEEK_API_KEY`; it sends selected images to DeepSeek. API attempts reserve a conservative amount, record usage and preserve unknown charges. Resume keeps the original configuration and budget; uncertain uncommitted calls require explicit `--retry-uncertain`.

`search` defaults to local `hybrid` retrieval; `--mode lexical` needs no embedding model, and `--mode semantic` uses local E5. Searches read a Completed run and save rankings, evidence and embedding-space identity. `benchmark` generates a report from a frozen label manifest; exit 6 means its gate is false or unverified, not that no report was written. Search scores are ranking signals, not probabilities or proof of usefulness.

## Phase 0 validation utilities

The completed 95.175874-second manga PV demo produced 24 visual windows, 111 events and no transcript segments, with estimated API cost ¥0.06246088 for that run; this is not a confirmed invoice. An attack query returned intervals around 28–29, 31–32 and 30–31 seconds; its first hybrid search took 2574 ms. These are smoke results, not a measured human Top-10 pass or an hour-scale performance claim.

Offline validation repeated three queries in three modes with stable results and a second process's SQLite reads. Real-video quality still has clear gaps: the English attack query returned no candidates in any mode; a car-repair negative query returned none in lexical/hybrid but ten false candidates in pure semantic mode. Chinese attack results remain unjudged. See the local ignored report `artifacts/demo-phase0/demo-validation.json`; independent human labels and real bilingual threshold calibration are the next validation steps.

The earlier local ASR utility remains available: `. ./scripts/env.ps1`, then `./.venv/Scripts/python.exe -B ./scripts/validate-asr.py --input "GameVideos/2025-08-17 15-26-27.mp4"`. It makes no API calls and saves each result immediately; transcripts remain ungraded. The [Grok handoff review](./docs/exec-plans/review-F003-grok-2026-10-04.md) documents the earlier integration state, not today's feature availability.

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
