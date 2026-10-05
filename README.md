# Gaming Creator Agent

Version repository: [happye/GameingCreatorAgent](https://github.com/happye/GameingCreatorAgent). Use the current working branch named in [`HANDOFF.md`](./HANDOFF.md); unfinished features may not be on `main`. Keep media, keys, environments, and caches outside tracked files.

This repository is the starting point for a local-first game-content creation tool. The source plan is [`游戏内容创作与商业化产品总方案 V1.0.txt`](./游戏内容创作与商业化产品总方案%20V1.0.txt). The first milestone validates whether a semantic timeline can find useful moments in local game footage before a desktop UI or commercial system is built.

## Current state

The command-line demo analyzes local footage, stores a semantic timeline, and finds candidate clips using local ASR, sampled-frame DeepSeek vision, SQLite, lexical search and local multilingual E5 embeddings. The local inspection workspace adds video preview, evidence, timeline filtering and selected-interval JSON/CSV exports. F000–F005 meet their technical criteria; F006's independent human quality gate remains unverified. The workspace has passed real-video browser validation and integrated checks; see the [verification record](./docs/exec-plans/sprint-workspace-usability.md). Video rendering and the commercial workflow remain future work. Phase 0 uses Python, SQLite and FFmpeg; see [ADR-001](./docs/design-docs/adr-001-phase-0-language.md) and the [workspace decision](./docs/design-docs/adr-002-local-inspection-ui.md).

On the prepared workstation, open the existing completed demo without API calls or network access:

```powershell
./scripts/setup-demo.ps1 -Offline
./scripts/run-demo.ps1 -Run f601fb9b3e734d5ea188fc15c790acbb -Query "黑色高礼帽白色面具角色挥动指挥棒"
./Start-Workspace.cmd
```

Double-click [Start-Workspace.cmd](./Start-Workspace.cmd) to start the local workspace and open the browser. Repeated launches reuse a matching repository service; conflicts report an error. Logs and PID state stay in `.cache/workspace`. No analysis or paid request occurs at startup. For another port use `./scripts/start-workspace.ps1 -Port 8766`; `run-ui.ps1` remains the foreground option. See the [user manual](./docs/references/user-manual.md) and [demo quickstart](./docs/references/demo-quickstart.md). Local videos, models and the demo database do not arrive with a Git clone.

Open `http://127.0.0.1:8765/`, choose a project and completed run, search, preview candidates, and add intervals to the clip basket. JSON/CSV preserve source identity, microsecond ranges and evidence; they are interval manifests. Desktop preview, timeline and basket remain visible while their lists scroll independently. Basket/storage/export use source time order; retrieval preserves relevance rank. To analyze new footage, use the CLI first.

The current browser workspace and backend run locally; DeepSeek vision uses remote inference on sampled frames. It is not yet packaged as an EXE. The source plan retains a future Windows desktop application with local media processing; see the [deployment roadmap](./docs/references/deployment-roadmap.md). Human content acceptance follows the [F006 guide](./docs/references/human-acceptance-guide.md), separately from UI usability.

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

User acceptance on 2026-10-04 rejected gameplay retrieval: Boss, jumping and shooting queries have no usable results, and descriptions lack action continuity. F006 remains failed/pending formal U10. The temporal correction is an unaccepted F009 experiment; see [validation and resumption](./docs/references/temporal-gameplay-validation.md) and HANDOFF before reusing earlier smoke results as quality evidence.

The prepared workstation's current default is completed Atom detail trial `f601fb9b3e734d5ea188fc15c790acbb`: 54.743220 seconds, 16 windows, 33 events and estimated API cost ¥0.10270124 (not an invoice). Explicit `config.detailed-v6.example.json` uses V6, 2 FPS, nine ordered images, two-frame overlap and a 1280-pixel width limit. Descriptions include clothing, held items, scenery and effects; uncertain observations appear separately. Existing facts, run configurations and basket identities remain unchanged. Internal frame aliases are cleaned for display, indexing and exports. See the [detail evidence](./docs/exec-plans/sprint-visual-details.md).

Real browser checks verified the new default, playback, evidence, chronological baskets and JSON/CSV exports. Offline retrieval v5 returns two jump candidates at 0–2 and 11.5–12.5 seconds, and detail candidates for heart-shaped glasses, scenery and a character with a conductor's baton. These remain unjudged. Long queries can match only some words or combine different actors' attributes; the demon-lord/armor/staff/shockwave example still returns unsupported partial candidates. Appearance errors, idle poses and cross-cut continuity remain unresolved. [Actor-detail matching](./docs/design-docs/actor-detail-matching-spec.md) specifies the next implementation; its availability must be checked in HANDOFF. Earlier V4 and manga runs remain available.

The completed 95.175874-second manga PV demo produced 24 visual windows, 111 events and no transcript segments, with estimated API cost ¥0.06246088 for that run; this is not a confirmed invoice. An attack query returned intervals around 28–29, 31–32 and 30–31 seconds; its first hybrid search took 2574 ms. These are smoke results, not a measured human Top-10 pass or an hour-scale performance claim.

Offline validation repeated three queries in three modes with stable results and a second process's SQLite reads. On 2026-10-04 the default hybrid search returned evidence-bearing 28–32 second intervals for both the Chinese attack query and `Find clips of fighters attacking each other in the arena`; the car-repair query returned none in hybrid. Pure semantic still returns false car-repair candidates. Chinese attack results remain unjudged. See the local ignored report `artifacts/demo-phase0/demo-validation.json`; independent human labels and real bilingual threshold calibration are the next validation steps.

The earlier local ASR utility remains available: `. ./scripts/env.ps1`, then `./.venv/Scripts/python.exe -B ./scripts/validate-asr.py --input "GameVideos/代号：Atom/录音/2025-08-17 15-26-27.mp4"`. It makes no API calls and saves each result immediately; transcripts remain ungraded. The [Grok handoff review](./docs/exec-plans/review-F003-grok-2026-10-04.md) documents the earlier integration state, not today's feature availability.

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

An earlier Grok inspection reported `projectTrusted: false` and no loaded instructions; later live loading has not been rechecked by Codex. Run `grok inspect` in the current workspace to confirm it. Claude's import is configured, but its live session loading has not been tested here.

Loading behavior was checked against official documentation on 2026-10-03: [Codex project instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Claude Code imports](https://code.claude.com/docs/en/memory#import-additional-files), and [Grok project rules](https://docs.x.ai/build/features/project-rules). Local account permissions and model execution are separate from repository adapter validation.
