# 当前交接

更新时间：2026-10-03（Asia/Hong_Kong）。供 Codex、Claude Code、Grok Build 接续；历史见 `progress.md`，验收见 `feature_list.json`。

## 当前状态

- 版本库：`https://github.com/happye/GameingCreatorAgent`；远端 `origin`，主分支 `main`。提交及未提交变更以 `git log -1 --oneline`、`git status --short` 为准。
- 审查与 Python 决策已推送至远端 `main`。首次连接失败后，用单次 `git -c http.version=HTTP/1.1 push -u origin main` 成功，未改全局配置。接手仍检查同步状态，不强推。
- F000 六方向反向审查、架构与工程合同、任务依赖已验收；入口为 `docs/exec-plans/sprint-F000.md`。原产品总方案未改动。
- F001–F006 未验收。没有应用 CLI、ASR、SQLite 或检索实现，完整 Phase 0 Top10 ≥70% gate 尚未测量。
- 当前无活跃编码任务；下一项 F001。分配前更新 `docs/exec-plans/assignments.md`。
- 语言决定：用户明确不强制 C#，Phase 0 使用 CPython 3.13 模块化核心；未来 UI 单独选型。先读 `docs/design-docs/adr-001-phase-0-language.md`，不要照历史 .NET 建议重建工程。

## 实测与限制

用户授权 `GameVideos/` 测试。三段短视频共 214.862313 秒：两段 PV 和一段标为实机的剪辑；Atom 两段先按同源开发组处理。已验证短窗抽帧/音频提取、合成无音轨以及 DeepSeek `deepseek-flash` 三次五帧请求。15 帧费用上界估算合计 ¥0.024076，未账单确认，不代表源小时成本或事件识别质量。

详细配置、结果路径与限制见 `docs/exec-plans/phase-0-validation-2026-10-03.md`。媒体和响应保存在 Git 忽略的 `artifacts/`；换机器需自备授权素材并重建。仍缺小时级未剪辑录像、冻结独立主组与正式人工事件/片段评级。

## 环境与检查

- 所有工具、包和缓存只用项目内 `.tools/`、`.venv/`、`.cache/`，禁止全局安装与修改用户/系统环境。先 `. ./scripts/env.ps1`；详细规则见 `docs/references/isolated-environment.md`。
- FFmpeg/ffprobe 与 DLL 已复制到 `.tools/ffmpeg/bin`，脚本显式调用副本。该构建含 GPL 组件，正式分发前需评审；项目 uv/CPython/venv 与 ASR 仍待准备，Phase 0 不需要 .NET。
- `./scripts/init.ps1 -CheckOnly`、媒体 smoke、计分回归、全部 PowerShell 语法及进程缓存/临时路径检查通过。完整检查仅接受项目内 uv 与 CPython 3.13 venv，缺环境时退出 1，不是已具备 Python 构建环境。
- uv 必须禁用 Windows 注册和全局可执行链接；`env.ps1` 已设隔离开关，F001 要固定支持它们的版本（≥0.11.8）并实际验证。
- `./scripts/test-deepseek-vision.ps1` 会上传五张帧并发出一次付费请求；密钥只读进程 `DEEPSEEK_API_KEY`，不写文件，不自动重试。先前聊天中暴露的凭据应轮换，不得复制进交接或提交。
- Claude Code 导入已配置；真实模型会话加载未测。上次 Grok 检查为 `projectTrusted:false`、空 instructions；首次使用处理信任提示后重查，不把适配文件存在当实际加载通过。

## 下一 owner 的具体动作

1. 读取共享规则、原总方案、工程规格和 `phase-0-plan.md`，检查工作树；在 `codex/F001-core` 或对应工具的独立分支/worktree 登记文件归属。
2. 为 F001 准备项目内 portable uv、固定 CPython 3.13 安全补丁/发行构建与下载校验；用该解释器创建 `.venv`，维护 `pyproject.toml`、`uv.lock`、`.python-version`，禁止系统 Python/注册/全局链接。
3. 建立 `src/gamingcreator/{cli,application,domain,infrastructure}` 和 pytest/Ruff/mypy/导入方向检查；实现输入错误行为及时间/Protocol/账本 DTO 合同。只装当前特性所需包，ASR 依赖与 worker 在 F003。
4. 合同集成后分配 F002 媒体映射与 F004 存储；F003 依赖 F002，再进入 F005/F006。正式人工标签准备可先行。每次交接记录实际命令和结果，未通过项保留 false。

不得重复初始化、提前进入正式 UI/商业系统，或用合成计分与图像请求成功替代真实检索验收。
