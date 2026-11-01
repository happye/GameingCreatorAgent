# Sprint：工作台检索与 searchEligible／覆盖缺口拒文对齐

**状态（2026-10-22）：已交付并推送 aa114b8。** 工作台 inspect／runs／搜索 UI 与 CLI 的 `retrieval.coverage_gap` 白话拒文对齐；`searchEligible`／`completedEligible` 下发到 inspect 与 runs。0 付费；不代选 A／B／D；不声称三缺口已清；不改 feature_list。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`ui/service.py`、`ui/static/app.js`、相关 HTTP／服务测试、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D

## 白话

在工作台打开「有覆盖缺口」的分析时，搜索框会按不能检索处理，并明确提示：**保留覆盖缺口、未获完整资格，不能用于检索或正式验收**。多段录像选择列表只出现可检索（Completed）任务。接口返回与命令行同一套拒绝码。

## Acceptance

- [x] inspect／runs 带 `searchEligible`；覆盖缺口 abstention=`retrieval.coverage_gap`
- [x] 工作台文案与提交拦截对齐
- [x] 相关 pytest 绿
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [x] 已推送 `origin/codex/visual-details`（aa114b8）
