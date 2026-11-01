# Sprint：验收绑定选项对齐覆盖缺口拒文

**状态（2026-10-22）：已交付并推送 5877395。** `binding_choices` 对 `analysis.coverage_gap` 给出与检索相同的白话拒文，并下发 `searchEligible`／`errorCode`；验收流程绑定选择列表禁用该任务。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`benchmark_run_selection.py`、验收流程 JS 文案、相关 pytest、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D、声称验收通过

## 白话

在「验收流程」里关联分析时，有覆盖缺口的任务会灰色不可选，并写明：**保留覆盖缺口、未获完整资格，不能用于检索或正式验收**。不会假装已经评测通过。

## Acceptance

- [x] coverage_gap 不可选且文案对齐
- [x] 相关 pytest 绿
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [x] 已推送 `origin/codex/visual-details`（5877395）
