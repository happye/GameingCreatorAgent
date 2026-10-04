# Progress Log

## 2026-10-03 — F002 local media accepted

- F001 integrated/pushed to main at `754125f`. Implemented local FFmpeg media port, exact PTS/Fraction/common origin, timestamped JPEG, 16k WAV with piecewise sample mapping, hashes and validated manifest publication.
- Independent worktree worker delivered Windows Job containment; root integrated suspended-start/assign/resume and EOF drain. Fixed venv parent-only cancellation leaks, AAC samples beyond declared end, symmetric resampling boundary quantization and the final hash cancellation race.
- Verification: 87 tests (0 skipped, warnings as errors), Ruff 27 files, strict mypy 21 files, import checks, CLI smoke and matching offline wheels passed. Four full local videos totaling 490.693314 seconds produced 492 images and mapped audio; no paid API calls.
- Real recording has 12,928 audio PTS discontinuities, reinforcing the piecewise requirement. Completed media bundles do not mark a full AnalysisRun complete.
- Tool/runtime isolation and specified host fingerprints remained unchanged. Recorded TD001 log cap, TD002 exact metadata support and TD003 media distribution provenance; hour-long/semantic quality remain unverified.
- Shared docs/handoff updated for Codex/Claude/Grok; F000/F001/F002 true, F003–F006 false. Next independent work is F004 storage plus F003 model preparation.

## 2026-10-03 — F001 isolated Python core accepted

- Installed hash-verified portable uv 0.12.22 and standard CPython 3.13.16/build 20261001 exclusively inside `.tools`; created `.venv` without system packages and pinned 17 package entries in `uv.lock`.
- Added installable four-layer package, CLI input/config/resume checks, Int64 source-time records and typed Provider/usage/cancellation contracts. Processing remains explicitly unimplemented; no dummy run or database is created.
- Validation: 50 pytest tests, Ruff formatting/lint, strict mypy for source/Provider fake and import boundaries pass. Two offline wheels have the same SHA256; only package/metadata entries are included. Installed CLI help/version pass.
- Offline setup from another directory preserves caller location and rejects inherited external uv project settings. User/machine environment and three Python registry subtree fingerprints stayed unchanged; this checks those boundaries, not all system activity.
- Fixed isolated Python probes rewriting local bytecode (`-I` ignores cache environment); use `-I -B` and restore from the verified archive. Read-only contract/environment reviewers found remaining pipeline checks belong to later features.
- Shared entry rules, README, architecture, engineering/environment/testing docs and handoff reconciled. Only F000/F001 true; F002 media preprocessing is next. No paid API requests this round.

## 2026-10-03 — Language clarification and Phase 0 baseline v2

- User clarified that C# is optional. A read-only language review selected Python for Phase 0 to directly use local ASR/embedding/evaluation tooling and reduce cross-language IPC; later desktop UI remains undecided. ADR-001 supersedes the initial .NET recommendation, not product scope or acceptance.
- Synchronized: AGENTS/CODEX/README/HANDOFF, architecture/engineering specs, feature/task lists, coding/testing/environment rules and prerequisite scripts. Shared Claude/Grok adapters inherit AGENTS rather than duplicating the language decision.
- Isolation: portable uv and CPython under `.tools`, all packages in `.venv`, project caches/temp; uv Windows registry registration/global links explicitly disabled. F001 pins versions and verifies imports/build; no Python/uv or global packages were installed in this review.
- Version checkpoint: review commit `55d0fb1` and Python decision `c2b7571` pushed to GitHub `main`. Initial HTTPS connection failed; a per-command HTTP/1.1 retry succeeded without changing global Git/network settings. `main` now tracks `origin/main`.
- Acceptance: only F000 true. CLI/ASR/SQLite/search and formal human Top10 benchmark still unimplemented/unverified. Next task is Python F001, not .NET setup; earlier progress entries are historical evidence.
- Verification after alignment: scaffold, PowerShell parsing, process paths and uv registry/link guard checks passed; media and metric smoke reruns passed. Full check correctly exits 1 for missing local uv/CPython venv. The language reviewer found no remaining contract conflict; no paid API rerun.

## 2026-10-03 — F000 review, limited Phase 0 experiments, and engineering baseline

- Delivered: six-axis reverse review, four-project architecture, CLI/time/Provider/SQLite/cost/recovery contracts, fixed-slot benchmark rules, F001–F006 dependencies and explicit ownership. Original product plan unchanged; F000 accepted as a document review only.
- Actual evidence: three short videos totaling 214.862313 seconds; local preprocessing and synthetic audio/no-audio smoke passed. DeepSeek `deepseek-flash` returned valid structured observations for 15 frames across three requests; conservative CNY estimate totals 0.024076, not confirmed billing or a source-hour benchmark.
- Review fixes: integer-only grades with boolean/string/fraction/out-of-range regression; all runtime/package/model/temp caches redirected inside the project; .NET 10-only prerequisite check; complete embedding space identity and run-scoped reuse for unresolved revisions. Three specialist reviews and a final read-only consistency review completed.
- Verification: scaffold, metric regression, media smoke, PowerShell parsing and process environment isolation passed. Full prerequisite check correctly exits 1 for missing project-local .NET 10 SDK. No global packages or system environment changes.
- Version setup: user-designated GitHub repository configured as `origin`; branch renamed to `main`. Raw media, credentials, portable tools, virtual environments, caches and generated evidence remain ignored.
- Remaining: application CLI, local ASR, SQLite, timeline/search, independent human labels, long-video speed, cold per-hour cost and real Top10 quality gate. F001–F006 remain false; no active coding assignment. Resume F001 from `HANDOFF.md`.

## 2026-10-03 — Cross-tool collaboration alignment

- Completed: Claude Code import adapter, Grok project rules adapter, shared task/ownership protocol, root handoff snapshot, assignment register, and sprint transfer fields. Codex guidance and README now refer to the shared protocol.
- Verification: scaffold check and whitespace checks passed; `CLAUDE.md` imports the existing `AGENTS.md`. Local versions: Claude Code 2.1.177 and Grok Build 1.0.46.
- Limitation: `grok inspect --json` reported `projectTrusted: false` and an empty project instruction list. Native loading remains to be checked after first-use repository trust; no Claude/Grok model session was run.
- Active feature: none. Product feature acceptance remains unchanged; F000 is next.
- Resume from: `HANDOFF.md`. For parallel work, assign distinct branches/worktrees and owned files before starting.

## 2026-10-03 — Harness initialization

- Completed: Codex-focused repository scaffold, Phase 0 scope and feature list, documentation map, prerequisite checker, and Git initialization.
- Active feature: none. F000 is next and remains `passes: false`.
- Verification: `./scripts/init.ps1 -CheckOnly` validates the scaffold; a full prerequisite check needs a .NET SDK before implementation can start.
- Next: write the F000 reverse review in `docs/exec-plans/`, then revise provisional scope or architecture as the evidence requires.
## 2026-10-04 F004 存储交付

SQLite 专用线程、进程锁、九表迁移/组合 FK、媒体/语义 checkpoint 原子提交、逐 attempt Decimal/NULL 账本与完整性恢复已验收。两个独立 worktree workers 交付 schema/lock 和真实进程测试，root 集成，另有只读审查。完整 verify：147 passed（0skip，资源警告失败）、Ruff/mypy 与重复离线 wheel 同 hash；F004 新增60项。四段真实素材的492图片/4WAV和全部音频映射跨进程重读一致，media-only，无模型结果。证据 sprint-F004。

修复旧媒体测试对 Windows 异步终止的立即句柄判断：保持原 interpreter 句柄，采用既有5s退出上限；独立50次均完成，无产品进程管理变更。F003/F005/F006仍false，人工Top10 gate未验证；后续工具不能将存储验收当模型/检索成功。所有包/工具/缓存继续项目隔离，无新安装或API请求。

## 2026-10-04 F003 持续保存检查点（未验收）

用户要求主动持久化，协作协议已补充每个实现/验证节点、失败和长任务前落盘及可恢复 Git 检查点，不等结束或用户提醒。root已有 ASR adapter/worker、固定模型/CRT准备、SQLite v2 uncertainty迁移；native探针与200项pytest回归（0skip，警告失败）通过。真实ASR首次失败原因已确定为PyAV19与faster-whisper1.2.1接口不兼容，完整实验保留；修正版本与视觉worker仍进行中。F003 false，尚无人工质量验收，本轮无付费调用；环境始终项目隔离。

## 2026-10-04 Grok交接后Codex复核

已核对Grok整合的Vision/budget/analyze与有限续跑、129段ASR及真实取消/超时报告。修正默认安装缺HTTPX及verify复用不可访问pytest目录；仅从固定归档恢复24个stdib pyc，收据/程序/DLL不变。最新完整verify：332 passed/0skip（20.06s）、Ruff/mypy/CLI与重复离线wheel通过，SHA `91f5aa449372679014232e5c0a4319bae000b97e19af31eb742f6c984d4433b8`。复核记录和README给出技术Demo命令；analyze仍缺视觉费用快照，search未实现，无GUI/完整产品Demo。已写具体后续工程缺口，F003/F005/F006false，未发付费请求；保存本地检查点以便直接接力。

版本持久化：检查点 `377bb68` 已推送 `origin/codex/F003-models`，本地与远端main同步 `ca0394e`。正常HTTP/1.1推送成功，未强推/修改全局网络配置。后续模型开发从F003分支接续，main仍是已验收F004基线。
