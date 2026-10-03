# 当前交接

更新时间：2026-10-03（Asia/Hong_Kong）。供 Codex、Claude Code、Grok Build 接续；历史见 `progress.md`，验收见 `feature_list.json`。

## 当前状态

- 版本库：`https://github.com/happye/GameingCreatorAgent`；远端 `origin`，主分支 `main`。提交及未提交变更以 `git log -1 --oneline`、`git status --short` 为准。
- F001 `754125f` 已整合并推送远端 `main`；F002 在 `codex/F002-media`，提交/同步状态以 Git 为准。HTTPS 不稳时使用单次 HTTP/1.1，不改全局配置、不强推。
- F000 六方向反向审查、架构与工程合同、任务依赖已验收；入口为 `docs/exec-plans/sprint-F000.md`。原产品总方案未改动。
- F001/F002 已验收：隔离固定工具、可安装核心、CLI/Provider 合同和本地媒体 service；87 个测试及重复离线构建通过。证据 sprint-F001/F002。正常 analyze/search/benchmark 仍返回 `feature.not_implemented`；没有 ASR/SQLite/检索流水线。
- F003–F006 未验收，完整人工 Top10 gate 未测量。F003 模型与 F004 存储可以分开推进；具体活跃归属看 assignments。
- 语言决定：用户明确不强制 C#，Phase 0 使用 CPython 3.13 模块化核心；未来 UI 单独选型。先读 `docs/design-docs/adr-001-phase-0-language.md`，不要照历史 .NET 建议重建工程。

## 实测与限制

用户授权 `GameVideos/` 测试。三段短视频共 214.862313 秒：两段 PV 和一段标为实机的剪辑；Atom 两段先按同源开发组处理。已验证短窗抽帧/音频提取、合成无音轨以及 DeepSeek `deepseek-flash` 三次五帧请求。15 帧费用上界估算合计 ¥0.024076，未账单确认，不代表源小时成本或事件识别质量。

F002 已完整处理当前四段（另有 275.831s Atom 录像），合计490.693314s、492张图及四个WAV，记录原始PTS/时基和音频分段映射。约4分半录屏有12,928个音频不连续点，不能用全局offset。结果 `artifacts/media-F002/026b702c0d8d4a65ba29c744bcf15140/validation.json`；详见 sprint-F002。旧三段 F000 模型实验不扩充成四段成功。

媒体/响应仍忽略；换机自备授权素材。缺小时级录像、独立冻结主组和人工标签；长视频日志限制 TD001 与精确metadata范围 TD002 必须按计划处理。

## 环境与检查

- 所有工具、包和缓存只用项目内 `.tools/`、`.venv/`、`.cache/`，禁止全局安装与修改用户/系统环境。先 `. ./scripts/env.ps1`；详细规则见 `docs/references/isolated-environment.md`。
- `toolchain.json` 固定 uv 0.12.22、CPython 3.13.16/build 20261001 和官方归档 SHA；`.tools` 逐文件 receipt、标准 x64/GIL 与 `.venv` 系统包隔离通过。开发依赖 `uv.lock`；ASR/权重仍属 F003。Phase 0 不需要 .NET。
- 新机运行 setup-env，有缓存可 `-Offline`；依赖 owner 才用 `-CreateLock`。verify 的87测试（0skip，警告失败）、Ruff、严格mypy、同hash wheel与CLI通过；init核对media-toolchain九个工具/DLL hash。用户/系统环境与Python注册表指纹未变，不代表全系统监控。
- FFmpeg/ffprobe 与 DLL 已复制到 `.tools/ffmpeg/bin`，未改原安装；含 GPL 组件，分发前需评审，新机另备本地副本。uv 注册/全局链接禁用，所有工具显式项目路径、无配置继承或外部项目目录覆盖。
- `./scripts/test-deepseek-vision.ps1` 会上传五张帧并发出一次付费请求；密钥只读进程 `DEEPSEEK_API_KEY`，不写文件，不自动重试。先前聊天中暴露的凭据应轮换，不得复制进交接或提交。
- Claude Code 导入已配置；真实模型会话加载未测。上次 Grok 检查为 `projectTrusted:false`、空 instructions；首次使用处理信任提示后重查，不把适配文件存在当实际加载通过。

## 下一 owner 的具体动作

1. 先检查 Git 与 assignments，运行 init/verify；登记分支/文件归属。不要重复创建已验收 F001/F002。
2. F004 建立 sqlite3 单写线程、迁移/FK/WAL/FULL、run/checkpoint/证据/调用账本与文件恢复。F003 用现有媒体 DTO/namespace/piecewise mapping；不能直接按WAV秒数回映射。
3. F003 模型包/权重和 native worker 在项目环境验证；缺原生依赖不安装到系统。F005依赖模型＋存储，F006实际gate要独立人工标签和小时级日志/性能实验。
4. worker scratch `.worktrees/f002-job` 仅交付已集成的 WindowsJob 文件，不是可接续主分支；具体源码以root分支/提交为准。每次转交保留实际证据和false未完成项。

不得重复初始化、提前进入正式 UI/商业系统，或用合成计分与图像请求成功替代真实检索验收。
