# Sprint：工作台只读展示验收就绪

**状态（2026-10-22）：已交付并推送 cb35e90。** 工作台新增「验收就绪」对话框与 `/api/acceptance-readiness`；能力位 `acceptance-readiness-v1`；前端拒绝展示任何通过声明；顺手把素材任务 schema 校验改为 `material-tasks-v2`，任务卡补充 coverage_gap 文案。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评／验收通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：ui/service、ui/server、static HTML/JS/CSS、HTTP pytest、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D、声称验收通过

## 白话

选好项目后点「验收就绪 ↗」，只看资格和卡点——**页面不会写已经验收通过**。素材任务列表也重新能打开（schema 对齐 v2）。

## Acceptance

- [x] GET `/api/acceptance-readiness` 只读且 never passed
- [x] 工作台按钮／对话框／护栏文案
- [x] 相关 pytest 绿；health 含 `acceptance-readiness-v1`
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [x] 已推送 `origin/codex/visual-details`（cb35e90）
