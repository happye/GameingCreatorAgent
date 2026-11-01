# Sprint：检索拒绝覆盖缺口／未完成 run（明确合同）

**状态（2026-10-22）：已交付并推送 8ef7291。** 自然语言检索入口在进入排序前，用 `load_searchable_timeline` 拒绝 `analysis.coverage_gap` 与未完成 run，并给出白话错误，避免落到笼统「项目存储校验失败」。0 付费；不代选 A／B／D；不声称三缺口已清；不改 feature_list。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`retrieval.py` 资格闸、`cli/main.py` 搜索入口、详情查询加载、相关 pytest、本 sprint、交接顶部
- 不做：付费视觉、改排名阈值、标 F006 true、重开 TD010

## 白话

如果你拿「有覆盖缺口」的长钟馗分析去搜，系统会直接说：**保留覆盖缺口、未获完整资格，不能用于检索或正式验收**——而不是含糊的存储失败。未完成／pending 任务仍提示只能检索已完成记录。

## Acceptance

- [x] `retrieval.coverage_gap`／未完成拒绝；单 run／多 run 搜索入口接线
- [x] 相关 pytest 绿
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 普通提交并推送 `origin/codex/visual-details`
