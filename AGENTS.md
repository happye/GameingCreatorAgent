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
- `./scripts/search-project.ps1 -Run <ids> -Query <text>`: search explicitly selected different Completed recordings; optional `-DetailProfile v1|v2|v3|v4` uses exact saved, supported observations. The workbench exposes “含已有细节”; see `docs/references/saved-detail-retrieval-guide.md`. Text ranking does not prove same-actor conditions; no new analysis is dispatched.
- `./Start-Workspace.cmd`: start the workspace and open a browser; reuse matching service. Logs stay in `.cache/workspace`; startup makes no paid requests.
- Workbench “验收流程” / `/acceptance`: persist registration, raw references, explicit Completed-version selection, freeze/bind, ranking, fixed review and scoring; see `docs/references/benchmark-workspace-guide.md`. Metadata choices do not verify media; binding retains the original source/evidence checks.
- `./scripts/init.ps1`: check scaffold, exact toolchain and media prerequisites; `-CheckOnly` checks scaffold.
- `./scripts/verify.ps1`: format, lint, types, pytest, and reproducible offline wheel builds.
- `./scripts/test-media.ps1 -AllLocal`: validate footage in ignored `GameVideos/`.
- `./scripts/test-storage.ps1 -AllLocal`: verify media persistence and a second process's reads.
- `./scripts/prepare-benchmark.ps1`: freeze source/query plans, then bind Completed runs without inference; see `docs/references/benchmark-preparation-guide.md`.
- `./scripts/prepare-benchmark-references.ps1`: prepare a local raw-footage reference page, or verify its saved record and export a plan for freezing; see `docs/references/benchmark-reference-review-guide.md`.
- `./scripts/prepare-benchmark-plan.ps1`: prepare a local source/query form, save incomplete registration drafts and export unconfirmed plans; see `docs/references/benchmark-plan-editor-guide.md`.

## Architecture and coding rules

Follow `docs/design-docs/architecture.md`, `phase-0-engineering-spec.md`, ADR-001 and ADR-002. Use four-space indentation, snake_case functions/modules and PascalCase types; Ruff formats/lints and mypy checks contracts. Domain excludes I/O. Preserve local video bytes, source clocks, provider/prompt/embedding identities and unknown costs. Basket/export order follows source time; retrieval keeps rank.

## Testing and acceptance

Use pytest `tests/test_*.py`; follow `docs/references/testing-guide.md` and `phase-0-benchmark.md`. Top-10 Useful Rate has ten fixed slots: missing and duplicate events count zero; independent human-judged usable events must reach ≥70%. Multi-frame inputs and index hits do not prove action understanding. Mark `passes: true` only after feature evidence. Benchmark exit 6 preserves its report when the gate fails or remains unverified.

Use `benchmark --binding <bound-directory>` for the frozen preparation workflow; only candidate judgments and human review status may change. Preparation readiness and recorded human declarations do not prove F006 acceptance.

## Changes, commits, and handoff

All agents share acceptance criteria; start with `HANDOFF.md` and `docs/references/agent-workflow.md`. Assign ownership; parallel writers use separate worktrees. Record verification and resumable work before transfer. Use imperative `chore:`/`docs:` subjects or `feat(F002): add local frame extraction`. PRs describe behavior, link a feature and include evidence. Never commit secrets, footage, generated media or databases.

## Persistent delivery priority

用户要求按总方案和设计好的开发路径推进大方向，优先阶段性交付，不在同一个小bug上反复消耗时间和tokens。每轮先明确所属阶段与主要交付；小问题能直接修就修，需要持续定位／试错就记录到docs/exec-plans/tech-debt.md，保存复现与影响后继续主线。只有阻断当前主要交付或影响数据／费用等关键边界的问题才优先处理。不得把连续微修、诊断增强、报告数量或重复完整测试代替计划中的实际开发进展。此规则适用于所有项目Agent、子任务、会话恢复和工具切换，与下方通俗汇报规则共同持续生效。

## Persistent reporting mode

用户要求所有项目 Agent 在每次关键改动后给出不那么技术味的详细汇报，并说明接下来要做什么。此偏好跨会话、工具切换和子任务持续生效，恢复工作时必须加载。

先解释现在能做什么、对用户的使用有什么帮助，再说明实际验证结果、仍存在的问题和下一步具体动作。用用户熟悉的例子；提交号、测试数量和内部实现仅作必要证据，不能代替使用效果说明。关键改动包括功能或使用流程变化、模型理解或费用行为变化，以及影响验收的发现。

按 `docs/references/agent-workflow.md` 的汇报协议执行；将本次已汇报的结论及下一步写入任务 sprint 和 `HANDOFF.md`。Worker 向集成负责人提供同样内容，由负责人汇总给用户；已有授权内的工作继续推进。

## Persistent human assistance and progress alignment

用户于2026-10-07要求：发现需要用户标注、确认素材、手动操作或提供其他帮助时，第一时间用通俗语言提醒，并记录到 `docs/exec-plans/human-inputs.md`。记录具体事项、操作入口、触发时点、影响范围、状态及完成证据；不要等用户追问，也不要替用户填写真实判断。待人工事项仅阻断依赖它的工作，继续推进可以独立完成的开发。需要新费用授权时保留原问题与提案，不把开发继续当作授权。

持续对齐里程碑和进度：关键实现／验证／发布节点同步当前 sprint、`HANDOFF.md`、`docs/exec-plans/assignments.md` 与 `progress.md` 的当前摘要；阶段或验收状态变化同时核对规格与 `feature_list.json`。顶部明确已交付、开发中、人工待办和下一步，旧失败／旧发布记录保留为历史，不能覆盖当前事实。所有项目 Agent、子任务及工具切换共同遵守。
