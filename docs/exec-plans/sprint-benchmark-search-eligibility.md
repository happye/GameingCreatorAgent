# Sprint：评测／绑定／细节核对接入检索资格闸

**状态（2026-10-22）：本轮交付。** CLI `execute_benchmark`／`execute_bind_benchmark`／`execute_detail_match` 改为 `load_searchable_timeline`，覆盖缺口与未完成 run 在正式评测／绑定／细节核对面与 NL 检索同一拒文；run_benchmark 校验媒体时不再把 AppError 吞成软失败。0 付费；不代选 A／B／D；不声称三缺口已清；不改 feature_list。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`cli/main.py` 评测／绑定／细节入口、相关 pytest、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D

## 白话

以后拿「有覆盖缺口」的分析去做正式评测、绑定评测清单、或核对细节，系统也会直接说不能用于检索／正式验收——和搜索框同一套规矩。

## Acceptance

- [x] benchmark／bind／detail-match 使用 searchable 闸
- [x] 相关 pytest 绿
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 推送 `origin/codex/visual-details`
