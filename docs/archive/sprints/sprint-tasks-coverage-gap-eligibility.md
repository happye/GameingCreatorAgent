# Sprint：任务列表区分覆盖缺口与检索资格

**状态（2026-10-22）：已交付并推送 3230651。** 覆盖缺口脚手架已齐；本轮回到 Phase-0 可用性：`tasks` 快照把 `analysis.coverage_gap` 从笼统「分析未完成」拆出，并标明不可检索／无完整资格。0 付费；不代选 A／B／D；不声称三缺口已清；不改 feature_list。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`application/tasks.py`、`ui/static/app.js` 任务下一步文案、相关 pytest、本 sprint、HANDOFF／progress／assignments／human-inputs 顶部
- 不做：launcher、DeepSeek、TD010 局部修、改 F006/F009/F010

## 白话

钟馗长片停在「有 3 个失败窗口」时，任务列表以前只说「分析未完成」，容易以为还能当正式结果去搜。现在会明确写成**保留覆盖缺口、未获完整资格**，并提示不能当正式检索／验收；另外两段仍「素材已保存，等待分析」的录像保持原样。

## Acceptance

- [x] `analysis_coverage_gap` 相位 + `searchEligible`／`completedEligible`；相关 pytest 绿
- [x] 工作台任务卡下一步文案区分缺口
- [x] TASKS_VERSION → material-tasks-v2
- [x] 普通提交并推送 `origin/codex/visual-details`

## Stop

- 禁止付费；禁止代选 A／B／D；禁止标 feature true。
