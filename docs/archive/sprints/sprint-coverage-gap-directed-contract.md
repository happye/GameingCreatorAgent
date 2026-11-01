# Sprint：定向补窗离线合同（isolate 与选项 B 边界）

**状态（2026-10-21）：已交付并推送 8fcc226。** 用户已选 C；本 sprint **不代选** A／B／D，也 **不** 发 DeepSeek、不重跑 launcher、不标 F006/F009/F010 true。三缺口仍在；清缺口仍须以后选项 B（新提案＋新费用授权）。

## Assignment

- Owner：root／GamingCreatorAgent（单 Agent）
- Branch：`codex/visual-details`
- Owned：`analysis_reliability.py` 定向补窗只读助手、`tests/test_directed_gap_fill_contract.py`、本 sprint、HANDOFF／assignments／progress／human-inputs 顶部；可选同步 `sprint-coverage-gap-plan.md`
- 不做：付费调用、改 feature_list、放松同帧合同、自动重发 3 缺口、实现真实补窗 launcher

## 白话合同

1. **现在的 isolate-schema-v1**：拒绝窗记下来继续往后跑；**不会**也不许把已拒绝窗或已成功窗再发一遍。续跑只处理「还没跑」的窗。
2. **以后若选 B（定向补窗）**：那是**另一份**提案身份（`directed-gap-fill-v1`），**不是**再按 isolate 续跑。目标只能从覆盖清单里的 `rejected` 窗里挑；**禁止**带上 269 个已成功窗；**禁止**把未执行窗塞进补窗名单。
3. **本轮只做离线护栏**：从 `analysis_coverage.json` 生成库存清单、校验目标集合；`feeAuthorized`／`sendAuthorized` 恒为 false。写清单 ≠ 消缺口 ≠ 授权花钱。

## Acceptance

- [x] `directed_gap_fill_inventory`／`validate_directed_gap_fill_targets` 落地；相关 pytest 绿
- [x] 真实长钟馗覆盖（若在仓）断言仅三拒绝可作目标，夹带成功窗必拒
- [x] 0 DeepSeek／0 launcher；F006/F009/F010 仍 false；不声称三缺口已清
- [x] human-inputs 保留 A／B／D 待决说明（C 已决）；B 仍须新提案＋新授权
- [x] 普通提交并推送 `origin/codex/visual-details`

## Stop

- 禁止付费；禁止用旧 v2／余额冒充补窗许可；禁止改 feature_list；禁止代用户选 A／B／D。

## Follow-on

- 提案草稿模板：见 [sprint-coverage-gap-proposal-draft.md](sprint-coverage-gap-proposal-draft.md)（不代选 B）。
