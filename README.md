# Gaming Creator Agent

The local workspace's “验收流程” entry connects source/query registration, raw-footage references, freezing, explicit selection of existing Completed analysis versions, local ranking and fixed-candidate review/scoring. Submitted steps preserve their inputs and new output directories; refresh or restart recovers progress and saved analysis choices. Forms require downloading edits and submitting the saved file. Ranking runs on an explicit click; scoring performs no search. See the [acceptance workspace guide](docs/references/benchmark-workspace-guide.md). Independent human retrieval acceptance remains pending.

Version repository: [happye/GameingCreatorAgent](https://github.com/happye/GameingCreatorAgent). Use the current working branch named in [`HANDOFF.md`](./HANDOFF.md); unfinished features may not be on `main`. Keep media, keys, environments, and caches outside tracked files.

This repository is the starting point for a local-first game-content creation tool. The source plan is [`游戏内容创作与商业化产品总方案 V1.0.txt`](./游戏内容创作与商业化产品总方案%20V1.0.txt). The first milestone validates whether a semantic timeline can find useful moments in local game footage before a desktop UI or commercial system is built.

## Current state

Explicit compound conditions can scan all saved events in selected Completed recordings through the workspace's “核对复合条件” entry or `match-project-details`. Results distinguish full, partial, contrary evidence and unverified, with filtering, stable-snapshot pages, original-source preview and current-page download. Exact base/refinement versions are required; no model, paid request, search persistence or automatic human judgment occurs. See the [condition guide](docs/references/project-detail-query-guide.md). Daily use does not require filling the acceptance workflow; required human tasks and timing are tracked in the [human-input list](docs/exec-plans/human-inputs.md).

After a joint search, “核对候选条件” or `match-search-details` attaches explicit condition evidence to every original returned candidate, preserving rank, scores and unknown candidates. The saved ranking digest and actual Completed sources are verified before matching; transcript-only candidates remain unverified. Switching recordings for preview keeps the annotation, while editing the search, conditions or profile clears it. A separate download includes the original ranking and evidence. See the [candidate evidence guide](docs/references/search-detail-evidence-guide.md).

One query can jointly search explicitly selected completed recordings in the local workspace's “选择多段录像” dialog or with `./scripts/search-project.ps1`. Results retain original source/run identities, timecodes, evidence and uncertainty; click a candidate to preview its own recording. BM25/E5/RRF rank a shared corpus, while baskets stay separate by run. Download the complete joint ranking without another search. See the [joint retrieval guide](./docs/references/project-retrieval-guide.md); no paid analysis is dispatched.

Multiple recordings can be prepared locally through the workspace's “准备多段录像” page or one bounded CLI list, with fixed task IDs, saved per-task configuration/limits and explicit continuation of the same batch. The page shows progress, reconnects after refresh and offers explicit stop/resume and saved batches. Bad recordings do not block later input items; ready tasks are checked and reused without extraction, and tasks already in model analysis are only reported. No model, upload or budget reservation occurs. See the [preparation page guide](./docs/references/media-preparation-workspace-guide.md) or [CLI batch guide](./docs/references/media-batch-preparation-guide.md).

Phase 0 now has a local [candidate review workflow](./docs/references/benchmark-candidate-review-guide.md): open an actual saved benchmark ranking, replay source intervals, fill human grades/reasons, download and reload records, then import verified judgments into the existing benchmark format. Ten positions remain fixed, including missing and duplicate events. Generation/import are read-only and make no model or search calls; independent human acceptance remains pending.

Before inference, the separate local [raw-footage reference page](./docs/references/benchmark-reference-review-guide.md) opens a predeclared plan, plays original recordings and lets a person register action intervals, save and reload reference drafts. Import rechecks the actual sources and fixed declarations before exporting a plan for the existing freeze workflow. It does not display model results, confirm human labels automatically or establish independent acceptance.

Start that plan with the local [source/query registration form](./docs/references/benchmark-plan-editor-guide.md): save incomplete drafts with unknown declarations, explicitly select source usage and whether results were viewed, then export an unconfirmed plan for raw-footage review. Registration does not read footage or infer recording independence, and refuses existing human references rather than clearing them.

Add `-Score` when importing a review record to score the original saved ranking with the existing quality rules. Source verification stays read-only, original search timings and unknown analysis costs are preserved, and scoring time is reported separately. Failed/unverified gates exit 6 while keeping the report; this makes no new searches or paid requests.

Completed searches now expose an unscored ten-slot diagnostic in the local workspace, with original ranks, missing positions, known duplicates, source preview and a bound JSON snapshot. See the [diagnostic guide](./docs/references/retrieval-diagnostics-guide.md). It does not establish human retrieval acceptance.

The command-line demo analyzes local footage, stores a semantic timeline, and finds candidate clips using local ASR, sampled-frame DeepSeek vision, SQLite, lexical search and local multilingual E5 embeddings. The local inspection workspace adds video preview, evidence, timeline filtering and selected-interval JSON/CSV exports. F000–F005 meet their technical criteria; F006's independent human quality gate remains unverified. The workspace has passed real-video browser validation and integrated checks; see the [verification record](./docs/exec-plans/sprint-workspace-usability.md). Video rendering and the commercial workflow remain future work. Phase 0 uses Python, SQLite and FFmpeg; see [ADR-001](./docs/design-docs/adr-001-phase-0-language.md) and the [workspace decision](./docs/design-docs/adr-002-local-inspection-ui.md).

On the prepared workstation, open the existing completed demo without API calls or network access:

```powershell
./scripts/setup-demo.ps1 -Offline
./scripts/run-demo.ps1 -Run f601fb9b3e734d5ea188fc15c790acbb -Query "黑色高礼帽白色面具角色挥动指挥棒"
./Start-Workspace.cmd
```

Double-click [Start-Workspace.cmd](./Start-Workspace.cmd) to start the local workspace and open the browser. Repeated launches reuse a matching repository service; conflicts report an error. Logs and PID state stay in `.cache/workspace`. No analysis or paid request occurs at startup. For another port use `./scripts/start-workspace.ps1 -Port 8766`; `run-ui.ps1` remains the foreground option. See the [user manual](./docs/references/user-manual.md) and [demo quickstart](./docs/references/demo-quickstart.md). Local videos, models and the demo database do not arrive with a Git clone.

Open `http://127.0.0.1:8765/`, choose a project and completed run, search, preview candidates, and add intervals to the clip basket. JSON/CSV preserve source identity, microsecond ranges and evidence; they are interval manifests. Desktop preview, timeline and basket remain visible while their lists scroll independently. Basket/storage/export use source time order; retrieval preserves relevance rank. To analyze new footage, use the CLI first.

The evidence panel reads saved actor details for the selected refinement version. The page defaults to v2, with explicit v1/v2/v3/v4 selection; the inspection API retains its v1 default. Select a clip and click “核对同主体条件” to build positive AND conditions, group attributes of the same garment or held object, and inspect full/partial/no_match/unverified with supporting frames. Missing results remain unverified. “精分析费用与调用” reads known estimates, unknown reservations and shared project commitment separately from base analysis. Opening, refreshing, matching and viewing cost history make no refinement calls. The condition dialog can draft editable positive conditions from supported Chinese/English descriptions. Unknown text remains visible and subset matching requires explicit confirmation; this does not turn ordinary retrieval into a full-sentence guarantee. Independent human acceptance remains pending.

The current browser workspace and backend run locally; DeepSeek vision uses remote inference on sampled frames. It is not yet packaged as an EXE. The source plan retains a future Windows desktop application with local media processing; see the [deployment roadmap](./docs/references/deployment-roadmap.md). Human content acceptance follows the [F006 guide](./docs/references/human-acceptance-guide.md), separately from UI usability.

Registered human feedback appears beside the exact saved actor description and its condition matches. Accepted or rejected descriptions retain the user's words and the original model output; other descriptions remain unreviewed. Feedback cannot carry over to another analysis result or count as attribute, action or retrieval acceptance. See the [description feedback report](./docs/exec-plans/report-2026-10-06-description-feedback.md).

## Start here

1. Read [`AGENTS.md`](./AGENTS.md), [`HANDOFF.md`](./HANDOFF.md), and the [shared workflow](./docs/references/agent-workflow.md). Open the same repository or your assigned worktree in whichever tool is available.
2. In PowerShell, run `./scripts/init.ps1 -CheckOnly` to verify scaffold files and `feature_list.json`.
3. Run `./scripts/setup-env.ps1` to download hash-pinned portable uv/CPython and synchronize `uv.lock` into `.venv`. Use `-Offline` only when archives and packages are cached. Run `./scripts/init.ps1` to check exact tools and the separately prepared local FFmpeg. Follow the [isolated environment rules](./docs/references/isolated-environment.md); everything stays inside `.tools/`, `.venv/`, and `.cache/`.
4. Resume your assigned task; review the [reverse review](./docs/exec-plans/reverse-review-2026-10-03.md), [engineering specification](./docs/design-docs/phase-0-engineering-spec.md), and [task dependencies](./docs/exec-plans/phase-0-plan.md). Record ownership and preserve a concrete handoff.

Run `./scripts/verify.ps1` for Ruff, strict mypy, pytest (warnings are errors), import boundaries, CLI smoke and two identical offline wheel builds. Media integration tests need the pinned local FFmpeg and otherwise skip; inspect skip counts. Details: [F001](./docs/exec-plans/sprint-F001.md), [F002](./docs/exec-plans/sprint-F002.md).

F004 evidence is in [sprint-F004](./docs/exec-plans/sprint-F004.md). `./scripts/test-storage.ps1 -AllLocal` round-trips real media bundles through SQLite and a separate reader process. It makes no model calls; runs explicitly require only the media stage. See [storage contracts](./docs/references/timeline-storage.md) for writer locks, recovery, and future integration.

Inspect commands with `./.venv/Scripts/gamingcreator.exe --help`. `config.example.json` uses schema v2: a dated CNY price snapshot, vision prompt version/content hash, output limit, sampling and ASR language. Five-frame windows overlap by one frame and cover every extracted frame. New analysis requires `--max-cost-cny` and process-local `DEEPSEEK_API_KEY`; it sends selected images to DeepSeek. API attempts reserve a conservative amount, record usage and preserve unknown charges. Resume keeps the original configuration and budget; uncertain uncommitted calls require explicit `--retry-uncertain`.

To prepare footage locally first, use `./scripts/prepare-media.ps1 -Video "GameVideos/your-video.mp4" -Project artifacts/demo-phase0 -Config config.example.json -MaxCostCny 5`. This extracts and saves images/audio plus the original configuration, then leaves the run pending explicit analysis. Preparation needs neither an API key nor installed ASR weights, constructs no model/transport/budget ports, and makes no paid request or reservation. The saved amount applies to later analysis. Its JSON reports the run ID, window/upload-frame coverage and a separate next command; insufficient coverage remains pending with no next command. `-Resume <id>` reuses completed media or resumes a failed media-only task without overriding configuration. See the [user manual](./docs/references/user-manual.md).

`search` defaults to local `hybrid` retrieval; `--mode lexical` needs no embedding model, and `--mode semantic` uses local E5. Searches read a Completed run and save rankings, evidence and embedding-space identity. `benchmark` generates a report from a frozen label manifest; exit 6 means its gate is false or unverified, not that no report was written. Search scores are ranking signals, not probabilities or proof of usefulness.

`match-details` reads a Completed run and an explicit manifest such as `detail-query.example.json`. Conditions must share one actor and, within a `partGroup`, one actual part and common frames. Unknown or uncertain attributes cannot satisfy a condition. It reads the exact published refinement profile and performs no inference:

```powershell
./.venv/Scripts/python.exe -B -m gamingcreator match-details --project artifacts/demo-phase0 --run <completed-run-id> --event <stored-event-id> --input detail-query.example.json --profile v2
```

The JSON report contains `full`, `partial`, `no_match` or `unverified`, individual condition support, source ranges and identities. Add `--save-match` to save an immutable report beside an existing refinement; missing details remain unverified without creating sidecars. `humanLabels` and `qualityGate` stay null. The independent v2 Provider and durable attempt recovery are implemented with no automatic retries; a paid CLI/page action is not exposed yet. See the [Provider](./docs/exec-plans/sprint-detail-provider.md) and [query](./docs/exec-plans/sprint-detail-query.md) records.

## Phase 0 validation utilities

The offline [same-footage pilot comparison](./docs/references/detail-pilot-comparison-guide.md) generates a standalone HTML page, source data and a human-review template from the exact frozen two-candidate proposal. It preserves the original six frames and description feedback; missing v4 results remain explicitly unexecuted, with new judgments empty. The page works directly from a local file, including JSON downloads. It makes no provider calls or budget changes and does not pass the independent retrieval gate.

Add `--review-editor` to generate a standalone local [review form](./docs/references/detail-pilot-review-guide.md) with file download/load. `--review-file <absolute-path>` validates a record against regenerated current sources; use `--dry-run` to check or `--output-dir <new-absolute-directory>` to archive the original input, normalized record, comparison snapshot, summary and provenance. Missing v4 results disable judgments, metadata does not imply acceptance, and each dimension stays separate.

User acceptance on 2026-10-04 rejected gameplay retrieval: Boss, jumping and shooting queries have no usable results, and descriptions lack action continuity. F006 remains failed/pending formal U10. The temporal correction is an unaccepted F009 experiment; see [validation and resumption](./docs/references/temporal-gameplay-validation.md) and HANDOFF before reusing earlier smoke results as quality evidence.

The prepared workstation's current default is completed Atom detail trial `f601fb9b3e734d5ea188fc15c790acbb`: 54.743220 seconds, 16 windows, 33 events and estimated API cost ¥0.10270124 (not an invoice). Explicit `config.detailed-v6.example.json` uses V6, 2 FPS, nine ordered images, two-frame overlap and a 1280-pixel width limit. Descriptions include clothing, held items, scenery and effects; uncertain observations appear separately. Existing facts, run configurations and basket identities remain unchanged. Internal frame aliases are cleaned for display, indexing and exports. See the [detail evidence](./docs/exec-plans/sprint-visual-details.md).

Real browser checks verified the new default, playback, evidence, chronological baskets and JSON/CSV exports. Offline retrieval v5 returns two jump candidates at 0–2 and 11.5–12.5 seconds, and detail candidates for heart-shaped glasses, scenery and a character with a conductor's baton. These remain unjudged. Long free-text queries can combine different actors' attributes; the demon-lord/armor/staff/shockwave example still returns unsupported partial candidates. The [actor-detail contract](./docs/design-docs/actor-detail-matching-spec.md), independent Provider, durable sidecars and explicit offline CLI matching are implemented. Two authorized real refinements completed at an estimated ¥0.01850612, both partial under their compound constraints. Model part binding and appearance errors still require independent human review. An offline v3 nested-parts contract addresses attribute binding without changing frozen v2 outputs; it has no real model validation yet. Page condition controls and a bounded editable description draft are implemented; full free-text understanding remains unverified. Earlier V4 and manga runs remain available.

The completed 95.175874-second manga PV demo produced 24 visual windows, 111 events and no transcript segments, with estimated API cost ¥0.06246088 for that run; this is not a confirmed invoice. An attack query returned intervals around 28–29, 31–32 and 30–31 seconds; its first hybrid search took 2574 ms. These are smoke results, not a measured human Top-10 pass or an hour-scale performance claim.

Offline validation repeated three queries in three modes with stable results and a second process's SQLite reads. On 2026-10-04 the default hybrid search returned evidence-bearing 28–32 second intervals for both the Chinese attack query and `Find clips of fighters attacking each other in the arena`; the car-repair query returned none in hybrid. Pure semantic still returns false car-repair candidates. Chinese attack results remain unjudged. See the local ignored report `artifacts/demo-phase0/demo-validation.json`; independent human labels and real bilingual threshold calibration are the next validation steps.

The earlier local ASR utility remains available: `. ./scripts/env.ps1`, then `./.venv/Scripts/python.exe -B ./scripts/validate-asr.py --input "GameVideos/代号：Atom/录音/2025-08-17 15-26-27.mp4"`. It makes no API calls and saves each result immediately; transcripts remain ungraded. The [Grok handoff review](./docs/exec-plans/review-F003-grok-2026-10-04.md) documents the earlier integration state, not today's feature availability.

The [2026-10-03 validation report](./docs/exec-plans/phase-0-validation-2026-10-03.md) records real local media/DeepSeek experiments and their limits. Run `./scripts/test-media-spike.ps1 -Synthetic` for the local media smoke and `./scripts/test-retrieval-score.ps1` for fixed-denominator metric regression. `test-deepseek-vision.ps1 -SourcePath <video>` needs process-local `DEEPSEEK_API_KEY` and makes one paid request of five extracted frames. It is a limited experiment, not the final CLI or a passed retrieval benchmark.

`./scripts/test-media.ps1 -SourcePath <local-video>` runs the implemented F002 service; `-AllLocal` processes current `GameVideos/**/*.mp4`. Results remain ignored in `artifacts/media-F002/<run>/`, with PTS/timebase, piecewise WAV sample mapping, source/artifact hashes, versions and a completed manifest after validation. No model request is made. Exact stream timing metadata is required; see [media processing](./docs/references/media-processing.md) for support limits.

For longer footage, set explicit local limits, such as `-MaxFrames 4000 -SamplingIntervalMs 1000 -TimeoutSeconds 600` for one frame per second. Timing logs are consumed incrementally while unknown output and individual lines remain bounded. A synthetic one-hour media/storage check passes; real gameplay performance and understanding still need validation. The prepared PowerShell 7 entry is verified; Windows PowerShell 5 compatibility is deferred in TD011.

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
