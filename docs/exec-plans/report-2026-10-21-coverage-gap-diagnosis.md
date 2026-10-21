# 报告：覆盖缺口只读拒因诊断包（2026-10-21）

**状态**：已交付只读诊断；**0 付费**；人工 A/B/C/D 仍待决。  
**分支**：`codex/visual-details`  
**正式工件**：[`artifacts/coverage-gap-diagnosis-20261021/`](../../artifacts/coverage-gap-diagnosis-20261021/)（`diagnosis-v1.json`、`report.md`、`whitelist-snippets-v1.json`）  
**规划依据**：[sprint-coverage-gap-plan.md](sprint-coverage-gap-plan.md)

## 结论摘要

1. 三缺口均为 `provider.schema` / `event_frame_boundaries`；248／253 白名单投影显示末事件 `f8→f8` 同帧，021 的 legacy `schemaDetail` 同属同帧模式。
2. 248／253 缺 `schemaDetail` 是因为提交 `1e3f420` 用 `schemaProjection` **替换**而非并存写入；非不同拒因。
3. isolate-schema-v1 记录齐全：失败检查点与费用保留；021 未被接续重发；248／253 拒后继续到尾。
4. 明确值得的离线代码修复：同时持久化 `schemaDetail` + `schemaProjection`（仍 0 付费、不消现有缺口）。
5. 清缺口仍须新授权定向补窗（选项 B）；旧 v2／余额不可冒充。未选 C/B 前保持 docs-only，不改产品源码与 feature 标志。

## 未做

- 未调用 DeepSeek／vision／launcher／execute-continuation  
- 未代选 A/B/C/D  
- 未 force-push、未碰 main、未标 F006/F009/F010 true  

## 下一建议

- 若选 **C**：先实现 schemaDetail 并存写入 + 同帧提示／fake-transport 测试。  
- 若选 **B**：提案须引用本诊断包同帧证据，并建议先做 C 再发。  
- 若选 **A/D**：本包仍可归档备查。
