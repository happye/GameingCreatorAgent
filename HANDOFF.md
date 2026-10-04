# 当前交接

更新时间：2026-10-04（Asia/Hong_Kong）。供 Codex、Claude Code、Grok Build 接续；历史见 `progress.md`，验收见 `feature_list.json`。

## 当前实施（优先于下方复核快照）

用户已授权继续做完全可运行的Phase0 CLI Demo。root分支 `codex/phase0-demo` 基于 `dee146b`；计划和模块归属在 `docs/exec-plans/sprint-demo.md`。价格配置是待实现功能，非需要用户提供资料的阻碍；当前进程凭据存在，开发素材已授权，实际请求将受run预算限制。root负责全轴窗口/恢复和命令整合，三个独立worktree负责pricing、retrieval、benchmark。正式UI不提前开始，人工gate仍未验证。

## 最新复核（优先于下方历史结果）

用户要求检查 Grok handoff；Codex 已核对代码/实测报告并复验，详见 `docs/exec-plans/review-F003-grok-2026-10-04.md`。最新 verify：332 passed/0 skip（20.06s）、Ruff/mypy/CLI通过，两次wheel SHA256 `91f5aa449372679014232e5c0a4319bae000b97e19af31eb742f6c984d4433b8`。补齐默认 HTTPX依赖；恢复24个漂移pyc（固定归档、收据不变）；verify采用每轮独立项目内pytest目录，旧目录不删除/接管。

只有命令行技术Demo（媒体/ASR/SQLite），没有GUI或自然语言检索完整Demo。实际analyze因CLI尚无费用快照以 `budget.estimate_missing` 停止；search未实现。F003/F005/F006仍false。本次无付费请求。

下一步按复核记录补价目/费用预留配置、全时轴滑窗、显式中断恢复与预算账本恢复、ASR开始前调用登记，确认中英参考后推进F005/F006。Grok已完成接续交接；旧worker worktrees保持冻结，本轮Codex复核完成，待下一owner接续。源码及复核检查点 `377bb68` 已推送 `origin/codex/F003-models`；`main`/`origin/main` 已同步 `ca0394e`。接手当前模型进度须用F003分支，不要只拉main。

## 当前状态

- 版本库：`https://github.com/happye/GameingCreatorAgent`；远端 `origin`，主分支 `main`。提交及未提交变更以 `git log -1 --oneline`、`git status --short` 为准。
- F001/F002/F004 已推送远端 `main`，最新 `ca0394e`；当前 root 在 `codex/F003-models`，检查点 `377bb68` 已推送同名远端分支。早先443超时已恢复，未改全局配置或强推。归属及交接状态见 assignments。
- F000 六方向反向审查、架构与工程合同、任务依赖已验收；入口为 `docs/exec-plans/sprint-F000.md`。原产品总方案未改动。
- F001/F002/F004 已验收：隔离工具、CLI/Provider、媒体及 SQLite service；147 个测试（0skip/资源警告失败）、Ruff/mypy 与重复离线构建通过。证据 sprint-F001/F002/F004。`search` / `benchmark` 仍返回 `feature.not_implemented`。`analyze` 已接到媒体预处理、本地 ASR 和 root 的 `DeepSeekVisionProvider` / `BudgetLedger`。未完成且各阶段均已完成的 run 从 checkpoint 续跑，不重做已完成的 media/asr；进行中的阶段返回 `storage.run_incomplete`。没有请求费用上界时以 `budget.estimate_missing` 停止，不发付费请求。检索流水线仍未做。
- F003/F005/F006 未验收，完整人工 Top10 gate 未测量。F003 的 ASR 运行时、root 视觉切片、analyze 接线和未完成 run 续跑已有证据，`passes` 仍是 false。具体归属看 assignments。
- 语言决定：用户明确不强制 C#，Phase 0 使用 CPython 3.13 模块化核心；未来 UI 单独选型。先读 `docs/design-docs/adr-001-phase-0-language.md`，不要照历史 .NET 建议重建工程。

## 实测与限制

用户授权 `GameVideos/` 测试。三段短视频共 214.862313 秒：两段 PV 和一段标为实机的剪辑；Atom 两段先按同源开发组处理。已验证短窗抽帧/音频提取、合成无音轨以及 DeepSeek `deepseek-flash` 三次五帧请求。15 帧费用上界估算合计 ¥0.024076，未账单确认，不代表源小时成本或事件识别质量。

F002 已完整处理当前四段（另有 275.831s Atom 录像），合计490.693314s、492张图及四个WAV，记录原始PTS/时基和音频分段映射。约4分半录屏有12,928个音频不连续点，不能用全局offset。结果 `artifacts/media-F002/026b702c0d8d4a65ba29c744bcf15140/validation.json`；详见 sprint-F002。旧三段 F000 模型实验不扩充成四段成功。

媒体/响应仍忽略；换机自备授权素材。缺小时级录像、独立冻结主组和人工标签；长视频日志限制 TD001 与精确metadata范围 TD002 必须按计划处理。

F004 四段真实媒体在 `artifacts/storage-F004/2f4b113a813448d5907e24c370b46c4e/validation.json` 完整重读（492图片/4WAV，media-only，无模型调用/事件）。九表 STRICT/组合FK、专用连接线程、项目进程锁、原子checkpoint/逐attempt账本和完整性恢复已通过；`load_media_bundle` 支持未完成run已完成媒体阶段。详见 `docs/references/timeline-storage.md`。旧媒体测试已改为持有原Windows interpreter句柄并在5s上限内等退出信号；产品Job.close未改。

## 环境与检查

- 所有工具、包和缓存只用项目内 `.tools/`、`.venv/`、`.cache/`，禁止全局安装与修改用户/系统环境。先 `. ./scripts/env.ps1`；详细规则见 `docs/references/isolated-environment.md`。
- `toolchain.json` 固定 uv 0.12.22、CPython 3.13.16/build 20261001 和官方归档 SHA；`.tools` 逐文件 receipt、标准 x64/GIL 与 `.venv` 系统包隔离通过。开发依赖 `uv.lock`；ASR/权重仍属 F003。Phase 0 不需要 .NET。
- 新机运行 setup-env，有缓存可 `-Offline`；依赖 owner 才用 `-CreateLock`。最新 `./scripts/verify.ps1` 于 2026-10-04 退出码 0：332 passed，Ruff、严格 mypy、同 hash wheel 与 CLI 通过。F004 历史结果是 147 项。init 核对 media-toolchain 九个工具/DLL hash。此前用户/系统环境与 Python 注册表指纹未变，不代表全系统监控。
- FFmpeg/ffprobe 与 DLL 已复制到 `.tools/ffmpeg/bin`，未改原安装；含 GPL 组件，分发前需评审，新机另备本地副本。uv 注册/全局链接禁用，所有工具显式项目路径、无配置继承或外部项目目录覆盖。
- `./scripts/test-deepseek-vision.ps1` 会上传五张帧并发出一次付费请求；密钥只读进程 `DEEPSEEK_API_KEY`，不写文件，不自动重试。先前聊天中暴露的凭据应轮换，不得复制进交接或提交。
- Claude Code 导入已配置；真实模型会话加载未测。上次 Grok 检查为 `projectTrusted:false`、空 instructions；首次使用处理信任提示后重查，不把适配文件存在当实际加载通过。

## 下一 owner 的具体动作

1. 先检查 Git 与 assignments。不要重复创建已验收的 F001/F002/F004，也不要重做已有证据的 ASR 运行时或 root 视觉切片。
2. F003 仍 false。PyAV 固定为 `av==16.1.0`。四段运行时、uncertainty 回读、readiness 取消/超时和 root 视觉测试见 sprint-F003。三支 PV 为 `no_speech`。native probe 只说明运行库就绪。
3. 下一步：未完成且各阶段均已完成的 run 会从 checkpoint 续跑，不重做已完成的 media/asr。正在进行的阶段仍返回 `storage.run_incomplete`。失败、取消或中断不自动重放。没有价目快照时不发付费请求。`./scripts/verify.ps1` 于 2026-10-04 退出码 0：Ruff、mypy（36 个源文件）通过；pytest `-W error` 332 passed（25.87s，汇总行没有 skipped）；两次离线 wheel SHA256 同为 `1DA2ACA59EF97F37DF30239EAA87C1DF507589BF7C816B6159E78D124AF9EA04`。不要把 F003 标成通过。中英参考仍未人工确认，三支 PV 为 `no_speech`，U10 未测。下一位不要重做续跑，也不要开始 F005/F006 或正式 UI。
4. `.worktrees/f002-job`、`f003-asr`、`f003-vision`、`f004-schema`、`f004-process` 是 scratch，不是接续点。root 源码为准。`.cache/pytest/v` 与 `.cache/pytest-tmp` 拒绝列出和删除，当前用户不能接管。pytest 缓存在 `.cache/pytest-cache`，`--basetemp` 在 `.cache/pytest-tmp-run`。不要指回旧目录。直接运行 `.venv\Scripts\python.exe` 而不先加载 `scripts/env.ps1` 会改写 `.tools/python` 里的标准库 `.pyc`，下一次 `verify.ps1` 会在收据校验失败。详见 `.learnings/ERRORS.md`。

不得重复初始化、提前进入正式 UI/商业系统，或用合成计分与图像请求成功替代真实检索验收。

## 持续检查点（2026-10-04）

F003 保持 false。Grok接续时可恢复提交为 `dd44284`；Codex复核后已准备保存包含Grok交付的检查点，最新提交和未提交文件以 `git log -1` / `git status --short` 为准。工作目录是 G: 根目录。

已有证据：四段报告 `artifacts/asr-F003/6133e370bc014955aa0585ac3db0528a/validation.json`；取消/超时报告 `artifacts/asr-F003/34e9c47a2fff470a8e665f7a9ce537e5/validation.json`；PyAV 19 失败报告 `a38f832f10e540e4bc6075b9a660fe52` 保留。root 视觉代码是 `budget.py`、`deepseek_vision.py`、`http_transport.py` 及对应测试。2026-10-04 再次用 `-W error` 跑 `tests/test_budget.py`、`tests/test_deepseek_vision.py` 与 `tests/test_local_asr.py`：104 passed（0.68s），39 passed（1.52s），覆盖坏 schema、未知费用不记成 0、独立 retry、替换 Provider、`no_audio`、`no_speech` 和 failure。Ruff 与 mypy 通过。`analyze` 接线后先有 31 passed。续跑接上后，`tests/test_analyze.py` 与 `tests/test_cli.py` 35 passed（1.49s，`-W error`）。最新 `./scripts/verify.ps1` 退出码 0：pytest `-W error` 332 passed（25.87s），离线 wheel SHA256 `1DA2ACA59EF97F37DF30239EAA87C1DF507589BF7C816B6159E78D124AF9EA04`。此前 328 passed 与 wheel `21BF2E9C…` 是续跑改动之前的一次通过，不是最终命令。F004 历史 147 项也不是。

下一步与上一节第 3 条相同。先读 sprint-F003。
