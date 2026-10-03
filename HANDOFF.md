# 当前交接

更新时间：2026-10-04（Asia/Hong_Kong）。供 Codex、Claude Code、Grok Build 接续；历史见 `progress.md`，验收见 `feature_list.json`。

## 当前状态

- 版本库：`https://github.com/happye/GameingCreatorAgent`；远端 `origin`，主分支 `main`。提交及未提交变更以 `git log -1 --oneline`、`git status --short` 为准。
- F001 `754125f` 已推送远端 `main`；F002 `45d3e42`、F004 `ca0394e` 已整合本地 main，再次推送443超时，GitHub仍待补。当前 root 在 `codex/F003-models`；ASR独立worker归属见 assignments。HTTPS 不稳时使用单次 HTTP/1.1，不改全局配置、不强推。
- F000 六方向反向审查、架构与工程合同、任务依赖已验收；入口为 `docs/exec-plans/sprint-F000.md`。原产品总方案未改动。
- F001/F002/F004 已验收：隔离工具、CLI/Provider、媒体及 SQLite service；147 个测试（0skip/资源警告失败）、Ruff/mypy 与重复离线构建通过。证据 sprint-F001/F002/F004。正常 analyze/search/benchmark 仍返回 `feature.not_implemented`；尚无模型/检索完整流水线。
- F003/F005/F006 未验收，完整人工 Top10 gate 未测量。下一项 F003 模型分析；具体活跃归属看 assignments。
- 语言决定：用户明确不强制 C#，Phase 0 使用 CPython 3.13 模块化核心；未来 UI 单独选型。先读 `docs/design-docs/adr-001-phase-0-language.md`，不要照历史 .NET 建议重建工程。

## 实测与限制

用户授权 `GameVideos/` 测试。三段短视频共 214.862313 秒：两段 PV 和一段标为实机的剪辑；Atom 两段先按同源开发组处理。已验证短窗抽帧/音频提取、合成无音轨以及 DeepSeek `deepseek-flash` 三次五帧请求。15 帧费用上界估算合计 ¥0.024076，未账单确认，不代表源小时成本或事件识别质量。

F002 已完整处理当前四段（另有 275.831s Atom 录像），合计490.693314s、492张图及四个WAV，记录原始PTS/时基和音频分段映射。约4分半录屏有12,928个音频不连续点，不能用全局offset。结果 `artifacts/media-F002/026b702c0d8d4a65ba29c744bcf15140/validation.json`；详见 sprint-F002。旧三段 F000 模型实验不扩充成四段成功。

媒体/响应仍忽略；换机自备授权素材。缺小时级录像、独立冻结主组和人工标签；长视频日志限制 TD001 与精确metadata范围 TD002 必须按计划处理。

F004 四段真实媒体在 `artifacts/storage-F004/2f4b113a813448d5907e24c370b46c4e/validation.json` 完整重读（492图片/4WAV，media-only，无模型调用/事件）。九表 STRICT/组合FK、专用连接线程、项目进程锁、原子checkpoint/逐attempt账本和完整性恢复已通过；`load_media_bundle` 支持未完成run已完成媒体阶段。详见 `docs/references/timeline-storage.md`。旧媒体测试已改为持有原Windows interpreter句柄并在5s上限内等退出信号；产品Job.close未改。

## 环境与检查

- 所有工具、包和缓存只用项目内 `.tools/`、`.venv/`、`.cache/`，禁止全局安装与修改用户/系统环境。先 `. ./scripts/env.ps1`；详细规则见 `docs/references/isolated-environment.md`。
- `toolchain.json` 固定 uv 0.12.22、CPython 3.13.16/build 20261001 和官方归档 SHA；`.tools` 逐文件 receipt、标准 x64/GIL 与 `.venv` 系统包隔离通过。开发依赖 `uv.lock`；ASR/权重仍属 F003。Phase 0 不需要 .NET。
- 新机运行 setup-env，有缓存可 `-Offline`；依赖 owner 才用 `-CreateLock`。最新 verify 的147测试（0skip，警告失败）、Ruff、严格mypy、同hash wheel与CLI通过；init核对media-toolchain九个工具/DLL hash。此前用户/系统环境与Python注册表指纹未变，不代表全系统监控。
- FFmpeg/ffprobe 与 DLL 已复制到 `.tools/ffmpeg/bin`，未改原安装；含 GPL 组件，分发前需评审，新机另备本地副本。uv 注册/全局链接禁用，所有工具显式项目路径、无配置继承或外部项目目录覆盖。
- `./scripts/test-deepseek-vision.ps1` 会上传五张帧并发出一次付费请求；密钥只读进程 `DEEPSEEK_API_KEY`，不写文件，不自动重试。先前聊天中暴露的凭据应轮换，不得复制进交接或提交。
- Claude Code 导入已配置；真实模型会话加载未测。上次 Grok 检查为 `projectTrusted:false`、空 instructions；首次使用处理信任提示后重查，不把适配文件存在当实际加载通过。

## 下一 owner 的具体动作

1. 先检查 Git 与 assignments，运行 init/verify；登记分支/文件归属。不要重复创建已验收 F001/F002。
2. F004已完成，不要重建。F003 已在项目内安装 ASR 包、官方 app-local CRT 和 tiny 固定模型，native/CPU/VAD probe 通过；首轮真实推理失败：PyAV19移除 `metadata_errors`，与 faster-whisper1.2.1 不兼容。先固定兼容 wheel、更新 lock/项目 venv，再运行 synthetic-only/真实素材；详见 sprint-F003，不能把 native probe 当成 ASR 成功。
3. F003 使用现有媒体 namespace/piecewise mapping 和 TimelineStore；通过load_media_bundle续跑，不能直接按WAV秒数映射或私读DB。随后实现视觉schema/预算/逐attempt/retry；F005/F006仍依赖模型与独立人工gate。
4. `.worktrees/f002-job`、`f004-schema`、`f004-process` 为已集成且冻结的worker scratch，不是接续点；具体源码以root分支/提交为准。每次转交保留实际证据和false未完成项。

不得重复初始化、提前进入正式 UI/商业系统，或用合成计分与图像请求成功替代真实检索验收。

## 持续检查点（2026-10-04）

用户要求在额度耗尽前持续保存，已写入 `agent-workflow.md`：每个实现/验证节点、失败和长任务启动前落盘；不等用户提醒。F003 保持 false。root 未提交文件包括 ASR settings/worker/facade/37项测试、SQLite v2 uncertainty迁移、ASR准备/诊断脚本、pins、pyproject/lock、文档；以 `git status` 为准。当前完整 verify 尚未重跑，147项仅是已提交 F004 的历史证据。

首轮失败报告 `artifacts/asr-F003/a38f832f10e540e4bc6075b9a660fe52/validation.json` 已保存，原生探针 `.cache/asr-native-probe.json` 已保存。它们被 Git 忽略，仅本机可用；固定版本/hash/失败原因在已跟踪文档中。Vision草稿在 `.worktrees/f003-vision`，未集成。现已重新委派兼容性只读研究及 Vision 审查；未收到验证结果前不能标记完成。其他旧ASR/SQLite worker停止且文件已归root集成，不再占用编辑任务。

最新 root `pytest -W error`：200 passed/0 skip（17.86s），diff检查通过；完整 format/type/build 仍待重跑。提交检查点不等于 F003 验收，具体提交以 `git log` 为准。
