# F003 模型分析与替换

状态：实施中，`passes: false`。2026-10-04 Codex root；ASR worker 独立 worktree，分工见 assignments。

当前先验证固定 Windows CPU wheels、项目内 native DLL 来源和完整 tiny multilingual 模型快照。不会运行系统安装器。候选 SHA/官方来源和待测合同见 `docs/references/asr-readiness.md`，不能把该只读研究当成推理已通过。

ASR 在可终止进程中完成加载和 segments 物化；本地音频 no_audio/no_speech/failed 区分，VAD 后 WAV 时间只回映射一次到 F002 源时钟。随后补视觉 schema/usage/预算/重试与替换验证。F004 ports 已可用；未知费用不可改零。

F002/F004 本地提交分别 `45d3e42`/`ca0394e` 已整合本地 main；GitHub main 当前仍 `754125f`，最近推送为连接443超时。禁止强推或更改全局网络配置；本地继续。

## 2026-10-04 恢复检查点（尚未验收）

- 根分支 `codex/F003-models` 基于 `ca0394e`。ASR facade/可终止 worker 和 SQLite v2 已复制到 root；旧 worker worktree 冻结。Vision 文件仅在 `.worktrees/f003-vision`，未集成，不能当成 root 已实现。
- 项目 `.venv` 已安装固定 ASR wheels，`.tools/native/msvc/14.51.36247` 已按官方 Microsoft VSIX 中白名单提取并逐文件校验；原 CPython DLL 未覆盖。tiny 四个模型文件已按固定 commit/size/SHA 验证。`scripts/prepare-asr-assets.py --offline` 可复核。
- `.cache/asr-native-probe.json` 记录四包 import、CPU int8、Silero CPU session 及实际 DLL 路径；相关运行库均在项目内。此结果仅验证 native 准备，不验证完整 ASR。
- 已记录 ASR 37 项离线合同测试通过（`pytest tests/test_local_asr.py -W error`）。SQLite v2 worker 的50项检查通过；root 尚未运行更新后的完整 verify。上次完整147项是 F004 历史结果，不能沿用为 F003 验收。
- 首次真实实验报告：`artifacts/asr-F003/a38f832f10e540e4bc6075b9a660fe52/validation.json`。四段真实素材及静音均 `failed/asr.inference`，无音轨 `no_audio`；诊断是 faster-whisper 1.2.1 调用 `av.open(metadata_errors="ignore")`，PyAV 19.0.1 已移除该参数。**不是 native 或权重缺失，ASR 推理尚未通过。**
- 下一步固定兼容 PyAV wheel 并更新 uv.lock，在项目 venv 重装；先 synthetic-only，再四段素材。需要实际推理 readiness 后取消/超时、持久化 uncertainty、Vision schema/预算/逐attempt及替换验证。中英参考未人工确认，U10 gate 未验证；本轮无付费请求。
- 恢复入口：先 `git status --short` 和 `HANDOFF.md`，不要重做 F001/F002/F004，也不要运行系统安装器。按节点持续更新本记录并提交可恢复检查点。
- 恢复后 root 重跑 `python -m pytest -W error`：**200 passed in 17.86s，0 skip**；`git diff --check` 通过。当前源码回归通过，不代表真实 ASR 或完整 format/type/build 检查通过。
