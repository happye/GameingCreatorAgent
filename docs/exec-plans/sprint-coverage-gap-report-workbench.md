# Sprint：工作台只读覆盖缺口报告

**状态（2026-10-22）：已交付（待推送）。** 工作台新增「覆盖缺口 ↗」对话框与 `/api/coverage-gap-report`；health 能力位 `coverage-gap-report-v1`；前端拒绝 cleared／optionChosen／F006 通过声明。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评／验收通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：ui service／server／static、相关 pytest、本 sprint、交接顶栏
- 不做：付费视觉、选 B 发送、标 F006 true、代选 A／B／D、声称验收通过、清除覆盖缺口

## 白话

命令行能看覆盖缺口之后，工作台也能一键只读查看：有哪些缺口 run、拒了哪些窗，并提醒仍要你选 A／B／D；页面不会写成已修好或已通过。

## Acceptance

- [x] `/api/coverage-gap-report` + health `coverage-gap-report-v1`
- [x] 工作台按钮／对话框／inert 渲染
- [x] HTTP／静态 pytest
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 已推送 `origin/main`（推送后勾）
