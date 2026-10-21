# Sprint：跨面 acceptance-readiness 惰性合同加固

**状态（2026-10-22）：已交付（待推送）。** 扩展 `assert_acceptance_readiness_inert`（禁止 passed／已通过等状态与标签）；导出 `SURFACE_JS_INERT_GUARDS`；新增跨面合同测试核对 CLI／API 能力位与工作台／验收流程 JS 护栏一致。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评／验收通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`acceptance_readiness.py`、跨面／单元 pytest、本 sprint、交接顶栏
- 不做：付费视觉、标 F006 true、代选 A／B／D、声称验收通过

## 白话

把「就绪报告绝不能写成已通过」写成统一合同：Python 护栏更严，并自动检查工作台和验收流程页面的同样检查还在。

## Acceptance

- [x] 禁止状态／标签集合 + snapshotOnly 护栏
- [x] 跨面 JS／CLI／health 合同测试
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 已推送 `origin/main`（推送后勾）
