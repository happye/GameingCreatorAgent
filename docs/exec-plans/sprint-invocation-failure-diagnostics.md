# Sprint：失败调用诊断投影进入 inspect／工作台

**状态（2026-10-22）：本轮交付。** 只读 `invocation_failure_diagnostics` 把失败调用的 `schemaError`／`schemaDetail`／`httpStatus`／`httpErrorProjection` 有界投影放进 inspect；工作台阶段列表展示「失败诊断」。0 付费；不代选 A／B／D；不声称三缺口已清；不改 feature_list。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`invocation_diagnostics.py`、inspect 载荷、app.js 阶段列表、相关 pytest、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D

## 白话

分析失败后，工作台「分析阶段」里能直接看到失败诊断摘要（例如同帧拒因或接口错误说明），不用再花钱重跑，也不用翻原始日志。

## Acceptance

- [x] inspect 含 `invocationFailures` 有界投影
- [x] 工作台展示失败诊断
- [x] 相关 pytest 绿
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 推送 `origin/codex/visual-details`
