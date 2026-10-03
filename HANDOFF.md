# 当前交接

更新时间：2026-10-03（Asia/Hong_Kong）。供 Codex、Claude Code、Grok Build 接续；历史见 `progress.md`，验收见 `feature_list.json`。

## 当前状态

- 版本库：`https://github.com/happye/GameingCreatorAgent`；远端 `origin`，主分支 `main`。提交及未提交变更以 `git log -1 --oneline`、`git status --short` 为准。
- 审查与 Python 决策已在远端 `main`；本轮 F001 分支 `codex/F001-core`，提交/推送状态以 Git 为准。HTTPS 不稳时使用单次 HTTP/1.1，不改全局配置、不强推。
- F000 六方向反向审查、架构与工程合同、任务依赖已验收；入口为 `docs/exec-plans/sprint-F000.md`。原产品总方案未改动。
- F001 已验收：隔离固定工具、可安装四层包、CLI 输入、领域/Provider DTO、50 个测试及重复离线构建。证据 `docs/exec-plans/sprint-F001.md`。CLI 入口存在，但正常 analyze/search/benchmark 返回 `feature.not_implemented`；尚无媒体/ASR/SQLite/检索流水线。
- F002–F006 未验收，完整 Phase 0 人工 Top10 ≥70% gate 未测量。下一项 F002；具体活跃归属看 assignments，允许 F004 在独立 worktree 并行。
- 语言决定：用户明确不强制 C#，Phase 0 使用 CPython 3.13 模块化核心；未来 UI 单独选型。先读 `docs/design-docs/adr-001-phase-0-language.md`，不要照历史 .NET 建议重建工程。

## 实测与限制

用户授权 `GameVideos/` 测试。三段短视频共 214.862313 秒：两段 PV 和一段标为实机的剪辑；Atom 两段先按同源开发组处理。已验证短窗抽帧/音频提取、合成无音轨以及 DeepSeek `deepseek-flash` 三次五帧请求。15 帧费用上界估算合计 ¥0.024076，未账单确认，不代表源小时成本或事件识别质量。

详细配置、结果路径与限制见 `docs/exec-plans/phase-0-validation-2026-10-03.md`。媒体和响应保存在 Git 忽略的 `artifacts/`；换机器需自备授权素材并重建。F001 后盘点发现目录另有 275.831s Atom 录像，初始 PTS 有变帧间隔，尚未完整验收；旧三段实验记录不扩充成四段成功。仍缺小时级录像、冻结独立主组与正式人工评级。

## 环境与检查

- 所有工具、包和缓存只用项目内 `.tools/`、`.venv/`、`.cache/`，禁止全局安装与修改用户/系统环境。先 `. ./scripts/env.ps1`；详细规则见 `docs/references/isolated-environment.md`。
- `toolchain.json` 固定 uv 0.12.22、CPython 3.13.16/build 20261001 和官方归档 SHA；`.tools` 逐文件 receipt、标准 x64/GIL 与 `.venv` 系统包隔离通过。开发依赖 `uv.lock`；ASR/权重仍属 F003。Phase 0 不需要 .NET。
- 新机运行 `./scripts/setup-env.ps1`，已有缓存可 `-Offline`；依赖 owner 才用 `-CreateLock`。`./scripts/verify.ps1` 的 50 测试、Ruff、严格 mypy、两次同 hash wheel、CLI help/version 通过；init 精确检查通过。用户/系统环境与三处 Python 注册表指纹未变，不代表全系统监控。
- FFmpeg/ffprobe 与 DLL 已复制到 `.tools/ffmpeg/bin`，未改原安装；含 GPL 组件，分发前需评审，新机另备本地副本。uv 注册/全局链接禁用，所有工具显式项目路径、无配置继承或外部项目目录覆盖。
- `./scripts/test-deepseek-vision.ps1` 会上传五张帧并发出一次付费请求；密钥只读进程 `DEEPSEEK_API_KEY`，不写文件，不自动重试。先前聊天中暴露的凭据应轮换，不得复制进交接或提交。
- Claude Code 导入已配置；真实模型会话加载未测。上次 Grok 检查为 `projectTrusted:false`、空 instructions；首次使用处理信任提示后重查，不把适配文件存在当实际加载通过。

## 下一 owner 的具体动作

1. 读取共享规则、原方案、工程规格和任务依赖，检查分支/未提交工作；先 init/verify，登记独立分支与文件归属。
2. F002 使用 copyts 与整数 PTS/timebase 提取证据；验证 VFR、非零起点、音轨偏移、音频重采样不连续、无音轨、坏文件和可取消子进程。不可按帧序号/FPS 或 WAV 0 秒推源时间。
3. F004 可独立并行；F003 依赖 F002，再进入 F005/F006。模型包/权重不提前全装，原生依赖不自动安装到本机。
4. 标签准备可先行。每次交接记录实际证据；未通过项保留 false，不重复建立 F001。

不得重复初始化、提前进入正式 UI/商业系统，或用合成计分与图像请求成功替代真实检索验收。
