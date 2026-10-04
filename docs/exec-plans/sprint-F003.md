# F003 模型分析与替换

状态：实施中，`passes: false`。2026-10-04 Grok Build 从 `dd44284` 接续，随后Codex复核并保存交接检查点；工作目录 `G:\Tools\ChatGPTRepo\GameingCreatorAgent`，分支 `codex/F003-models`。最新HEAD/未提交状态以Git为准，分工见 assignments。

最新：用户要求 Codex 复核 Grok交接；复核记录 `review-F003-grok-2026-10-04.md` 优先于历史下一步。补齐HTTPX正式依赖及独立pytest目录，恢复24个pyc漂移后完整verify通过：332 passed/0skip（20.06s）、Ruff/mypy与两次同hashwheel。没有GUI/检索产品Demo，CLI视觉仍因费用快照缺失停止，F003false。工作已准备为本地可恢复检查点，不等额度耗尽才记录。

已落地、不要重做：项目内 ASR wheels 与 tiny 模型、`av==16.1.0`、四段运行时、129/129 uncertainty 回读、readiness 后的真实取消/超时，以及 root 上的视觉 schema、逐 attempt 用量、未知费用、预算、重试和可替换 Provider。本地 ASR 仍区分 `no_audio` / `no_speech` / failure。WAV 时间只经 F002 piecewise mapping 回到源时钟一次。未知费用保持未知。候选来源见 `docs/references/asr-readiness.md`。

`gamingcreator analyze` 已接到媒体预处理、本地 ASR 和 root 的 `DeepSeekVisionProvider` / `BudgetLedger`。没有请求费用上界时返回 `budget.estimate_missing`，不发付费请求。已完成 run 可以 resume 重读。未完成且各阶段均已完成的 run 从 checkpoint 续跑，不重做已完成的 media/asr；进行中的阶段返回 `storage.run_incomplete`。失败、取消或中断不自动重放。`search` / `benchmark` 仍是 `feature.not_implemented`。中英参考未人工确认，三支 PV 为 `no_speech`，U10 未测。F005/F006 和正式 UI 未开始。

下一步：未完成且各阶段均已完成的 run 会从 checkpoint 续跑，不重做已完成的 media/asr。正在进行的阶段仍返回 `storage.run_incomplete`。失败、取消或中断不自动重放。没有价目快照时不发付费请求。`./scripts/verify.ps1` 于 2026-10-04 退出码 0：Ruff、mypy（36 个源文件）通过；pytest `-W error` 332 passed（25.87s，汇总行没有 skipped）；两次离线 wheel SHA256 同为 `1DA2ACA59EF97F37DF30239EAA87C1DF507589BF7C816B6159E78D124AF9EA04`。不要把 F003 标成通过。中英参考仍未人工确认，三支 PV 为 `no_speech`，U10 未测。下一位不要重做续跑，也不要开始 F005/F006 或正式 UI。

F002/F004 本地提交分别 `45d3e42`/`ca0394e` 已整合本地 main；GitHub main 当前仍 `754125f`，最近推送为连接443超时。禁止强推或更改全局网络配置；本地继续。

## 2026-10-04 恢复检查点（尚未验收）

- 根分支 `codex/F003-models` 基于 `ca0394e`。ASR facade/可终止 worker 和 SQLite v2 已复制到 root；旧 worker worktree 冻结。本检查点当时 Vision 只在 `.worktrees/f003-vision`；2026-10-04 已接到 root，见文末。
- 项目 `.venv` 已安装固定 ASR wheels，`.tools/native/msvc/14.51.36247` 已按官方 Microsoft VSIX 中白名单提取并逐文件校验；原 CPython DLL 未覆盖。tiny 四个模型文件已按固定 commit/size/SHA 验证。`scripts/prepare-asr-assets.py --offline` 可复核。
- `.cache/asr-native-probe.json` 记录四包 import、CPU int8、Silero CPU session 及实际 DLL 路径；相关运行库均在项目内。此结果仅验证 native 准备，不验证完整 ASR。
- 已记录 ASR 37 项离线合同测试通过（`pytest tests/test_local_asr.py -W error`）。SQLite v2 worker 的50项检查通过；root 尚未运行更新后的完整 verify。上次完整147项是 F004 历史结果，不能沿用为 F003 验收。
- 首次真实实验报告：`artifacts/asr-F003/a38f832f10e540e4bc6075b9a660fe52/validation.json`。当时四段真实素材及静音均 `failed/asr.inference`，无音轨 `no_audio`；诊断是 faster-whisper 1.2.1 调用 `av.open(metadata_errors="ignore")`，PyAV 19.0.1 已移除该参数。不是 native 或权重缺失。该失败保留；随后的 `av==16.1.0` 复验已通过，见下文。
- 随后已把兼容版本固定为 `av==16.1.0`，并完成 synthetic、四段素材、uncertainty 回读、readiness 取消/超时和 root 视觉切片。中英参考仍未人工确认，U10 仍未测。本轮无付费请求。
- 恢复入口：先 `git status --short` 和 `HANDOFF.md`，不要重做 F001/F002/F004，也不要运行系统安装器。按节点持续更新本记录并提交可恢复检查点。
- 恢复后 root 重跑 `python -m pytest -W error`：**200 passed in 17.86s，0 skip**；`git diff --check` 通过。当前源码回归通过，不代表真实 ASR 或完整 format/type/build 检查通过。
- 已保存本地检查点 `dd44284`（F003 false）。兼容版本已固定为 `av==16.1.0`：官方 v16.1.0 `av/container/core.pyx` 保留 `metadata_errors`，v19 changelog明确删除。Windows标准cp313 wheel SHA256 `565093ebc93b2f4b76782589564869dadfa83af5b852edebedd8fee746457d06`，31,729,230 bytes。
- 兼容修复已在项目 `.venv` 完成，native复验 `.cache/asr-native-probe-av16.json` 通过；实际静音 `no_speech`、无音轨 `no_audio`（报告 `artifacts/asr-F003/0a9ef42cf63644f0828a08349311e4be/validation.json`）。首次19版失败报告保留。四段素材与取消/超时的结果在下一节。
- 验证脚本现在每个 case 原子保存报告，运行中 `validationPassed:null`，预期之外失败返回非零。四段实验已经完成，报告在下一节，无网络 API 费用。

## 2026-10-04 Grok Build 接续

工作目录是 `G:\Tools\ChatGPTRepo\GameingCreatorAgent`，分支 `codex/F003-models`，HEAD 仍是 `dd44284`。F003 `passes` 仍为 false。

四段素材实验已经结束。报告 `artifacts/asr-F003/6133e370bc014955aa0585ac3db0528a/validation.json`：`state=completed`，`validationPassed=true`。包版本是 faster-whisper 1.2.1、ctranslate2 4.8.2、av 16.1.0、onnxruntime 1.30.0。这只证明运行时合同和存储回读，不证明转录质量，F003 仍是 `passes: false`。

| 素材 | 状态 | 段数 | elapsed / worker | 检测语言 |
| --- | --- | ---: | --- | --- |
| Atom PV | no_speech | 0 | 1626 / 1223 ms | cy |
| Atom 实机 PV | no_speech | 0 | 1559 / 1187 ms | cy |
| `2025-08-17 15-26-27.mp4` | completed | 129 | 21428 / 20848 ms | zh |
| 漫画群星 PV | no_speech | 0 | 1574 / 1182 ms | cy |
| synthetic-silence | no_speech | 0 | 1211 / 873 ms | zh |
| synthetic-no-audio | no_audio | 0 | 0 ms | — |

有语音的录像 sha256 是 `dd4cc33653bd7c8b6a4c2040e22fc6dd1354ed7f910555b644e01739f8366e2d`，时长 275.831 秒。SQLite `transcript_segments` 里 `asr-002` 为 129/129 条带 `uncertainty`，脚本对完成态做了回读相等检查。三支 PV 被判无语音且语言成了 cy，中英参考仍未人工确认。无网络 API 费用。U10 未测。PyAV 19 的失败报告 `a38f832f10e540e4bc6075b9a660fe52` 保留。

取消/超时已完成。脚本 `scripts/validate-asr-control.py` 通过 `load_media_bundle("asr-002")` 只读续跑，不重新抽帧，也不写那份 SQLite。

root 的 `local_asr.py`、`asr_worker.py` 和 `tests/test_local_asr.py` 已经引用 `asr_runtime`，文件本身当时只在 `.worktrees/f003-asr`。已原样复制到 root：`src/gamingcreator/infrastructure/asr_runtime.py`、`tests/test_asr_runtime.py`。worktree 没有改。随后只做了 Ruff 格式和 import 排序，没有改行为。

取消/超时实验已完成，报告 `artifacts/asr-F003/34e9c47a2fff470a8e665f7a9ce537e5/validation.json`，`validationPassed=true`。源是只读 `load_media_bundle("asr-002")`，sha256 与四段报告一致，音频 sha256 `fef2cf79c23ac1924e10c64eb8d95ab3a3d10bc6f625968dcd42155fb2b64671`。包版本仍是 av 16.1.0 那一组。无网络 API 费用。

- 取消：`ready.json` 在 3192ms 出现（pid 76720，`inference_started`，`completedSegments=1`），随后 `asr.cancelled`，`outputPublished=false`，进程 `WaitForSingleObject=0`，请求目录已删除。总耗时 3199ms。
- 超时：截止 7.192s。握手在 2999ms（pid 70460），7204ms 时 `asr.timeout`，同样没有发布 segments，进程已退出。不需要第二次收紧截止时间。

这证明真实推理开始后，取消和超时都会终止 worker，并且不把部分转录当结果。它不证明转录质量，也不把 F003 标成通过。

同树检查：`ruff format --check` 与 `ruff check` 覆盖 `src`、`tests`、`scripts/validate-asr.py`、`scripts/validate-asr-control.py`，通过。`mypy` 按 pyproject 文件列表通过。`pytest -W error` 在关掉 cacheprovider 后 `217 passed in 15.51s`，ASR 相关 54 项在格式化后重跑仍通过。默认 `.cache/pytest` 曾出现 WinError 5，所以这次没有用它。`scripts/verify.ps1` 的离线 wheel 构建没有重跑。

2026-10-04 02:49 检查 `.worktrees/f003-vision`：上述五份文件最后写入停在 01:23–01:53，检查时无更新，按空闲处理。已原样接到 root，没有覆盖更新过的 ASR 与存储代码，没有发付费视觉请求：

- `src/gamingcreator/application/budget.py`
- `src/gamingcreator/infrastructure/deepseek_vision.py`
- `src/gamingcreator/infrastructure/http_transport.py`
- `tests/test_budget.py`
- `tests/test_deepseek_vision.py`

`asr_worker.py` 只把 native file 记录改成先检查类型再构造 `ModelFile`，合法记录不变，为的是 mypy 能通过。假传输测试覆盖坏 schema 拒绝、未知费用不记成 0、每次重试独立 attempt/用量，以及替换 Provider 不发网络请求。当时 `pytest -W error -p no:cacheprovider`：视觉与预算 104 passed（0.59s），`tests/test_local_asr.py` 39 passed（1.48s），含 `no_audio`、`no_speech` 和 failure。`ruff format --check`、`ruff check`（范围同 `scripts/verify.ps1`）和 `mypy` 通过。默认 `.cache/pytest` 再次 WinError 5，所以那次关掉 cacheprovider；见 `.learnings/ERRORS.md`。那次离线 wheel 还没重跑。2026-10-04 在项目 `--basetemp` 下再次用 `-W error` 跑过同一组：104 passed（0.68s），39 passed（1.52s）。全量 verify 见文末。

2026-10-04 接上 `analyze`：`application/analysis.py` 编排现有媒体预处理、本地 ASR 和视觉 Provider；CLI 用 root 的 `DeepSeekVisionProvider` 与 `BudgetLedger`。价目快照仍缺，`vision_for_run` 传入的预留费用是 `None`，账本在 HTTP 之前停止。假传输测试覆盖未知费用不记成 0、坏 schema 不完成时间线、替换 Provider 不发网络请求，以及 ASR 失败时不调用视觉。不可解码文件在 probe 失败，不创建项目。`tests/test_analyze.py` 与 `tests/test_cli.py` 31 passed（1.18s，`-W error`，关 cacheprovider）。mypy 36 个源文件通过。`.cache/pytest-tmp` 无法列出或删除，`--basetemp` 改到 `.cache/pytest-tmp-run` 后，全量 `./scripts/verify.ps1` 曾退出码 0：328 passed（25.66s），离线 wheel SHA256 `21BF2E9C7B11484A684B09B4D62874D00406B2AE7A6ABEECC265EC3D9FB422B9`。这次是续跑改动之前的结果。

2026-10-04 接上未完成 run 续跑。pending 或 running、且已有阶段全部完成时，从 checkpoint 继续，不调用已完成的 media/asr。进行中的阶段返回 `storage.run_incomplete`，运行保持 running。失败、取消、中断不自动重放。没有价目快照时，续跑在 HTTP 前停止，并且不重做已完成阶段。`tests/test_analyze.py` 与 `tests/test_cli.py` 35 passed（1.49s，`-W error`）。随后 `./scripts/verify.ps1` 退出码 0：332 passed（25.87s），离线 wheel SHA256 `1DA2ACA59EF97F37DF30239EAA87C1DF507589BF7C816B6159E78D124AF9EA04`。

下一步：未完成且各阶段均已完成的 run 会从 checkpoint 续跑，不重做已完成的 media/asr。正在进行的阶段仍返回 `storage.run_incomplete`。失败、取消或中断不自动重放。没有价目快照时不发付费请求。`./scripts/verify.ps1` 于 2026-10-04 退出码 0：Ruff、mypy（36 个源文件）通过；pytest `-W error` 332 passed（25.87s，汇总行没有 skipped）；两次离线 wheel SHA256 同为 `1DA2ACA59EF97F37DF30239EAA87C1DF507589BF7C816B6159E78D124AF9EA04`。不要把 F003 标成通过。中英参考仍未人工确认，三支 PV 为 `no_speech`，U10 未测。下一位不要重做续跑，也不要开始 F005/F006 或正式 UI。
