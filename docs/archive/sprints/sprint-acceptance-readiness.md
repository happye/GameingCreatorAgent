# Sprint：离线验收就绪只读汇总

**状态（2026-10-22）：已交付并推送 d911068。** 新增 `acceptance_readiness` 与 CLI `acceptance-readiness`：从任务快照汇总可检索／覆盖缺口／阻断；`formalAcceptancePassed`／`humanEvalPassed`／F006/F009/F010 恒为 false；有可检索运行时仅 `awaiting_human_labels_and_freeze`，永不输出 passed。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`acceptance_readiness.py`、CLI 入口、相关 pytest、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D、声称验收通过

## 白话

本机可跑：`gamingcreator acceptance-readiness --project <项目目录>`（可选 `--output` 写 JSON）。它只告诉你现在能不能谈正式验收、卡在哪——**绝不会说已经验收通过**。

## Acceptance

- [x] 无任务／仅缺口／有可检索 三种状态文案正确且永不 passed
- [x] inert 护栏拒绝把 F006／人评／qualityGate 标真
- [x] 相关 pytest 绿；CLI 只读不碰媒体／模型
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [x] 已推送 `origin/codex/visual-details`（d911068）
