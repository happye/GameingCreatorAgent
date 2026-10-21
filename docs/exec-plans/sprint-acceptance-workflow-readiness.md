# Sprint：验收流程页只读挂接验收就绪

**状态（2026-10-22）：已交付（待推送）。** 验收流程「关联已完成的分析」读取任务时，同时拉 `/api/acceptance-readiness` 并展示只读汇总；`assertReadinessInert` 拒绝任何通过声明；页头／总览文案强调就绪 ≠ 已验收／F006。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评／验收通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：benchmark-workflow.js／html／css、静态 pytest、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D、声称验收通过

## 白话

在验收流程第 5 步点「读取可关联的分析」时，旁边会多一块「验收就绪」说明：现在能不能谈正式验收、卡在哪。**绝不会写成已经通过。**

## Acceptance

- [x] 关联读取时展示 readiness；含通过声明则拒显
- [x] 文案区分质量门槛／F006／人评
- [x] 静态 pytest 绿；0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 已推送 `origin/codex/visual-details`（推送后勾）
