# Sprint：定向补窗提案草稿模板（离线、不代选 B）

**状态（2026-10-21）：离线实现中／本轮交付。** 在已落地的 `directed-gap-fill-v1` 护栏之上，补一份**未冻结、未授权**的提案草稿形状，方便以后若你选 B 时直接填费用／确认，而不是从零拼字段。本 sprint **不代选** A／B／D，0 付费，不重跑 launcher，不标 F006/F009/F010 true，不声称三缺口已清。

## Assignment

- Owner：root／GamingCreatorAgent（单 Agent）
- Branch：`codex/visual-details`
- Owned：`directed_gap_fill.py`、相关 pytest、本 sprint、HANDOFF／assignments／progress／human-inputs 顶部；示例 JSON（若有）
- 不做：真实补窗执行器、付费调用、改 feature_list、代选 B、把草稿标成已授权

## 白话

1. 护栏已经会拦「乱点成功窗口」。还缺一张**空白合同纸**：写明补哪几个失败窗、不能动哪些成功窗、费用栏先空着／仅占位、授权全是否。
2. 本轮生成的是 `template-unfrozen` 草稿：`selectsOptionB=false`，`executionAuthorized/feeAuthorized/sendAuthorized=false`，`gapsCleared=false`。
3. 填了费用数字也**不等于**批准；真正选 B 并批准后，才另开冻结提案／执行路径。

## Acceptance

- [x] `build_directed_gap_fill_proposal_draft`／`assert_directed_gap_fill_draft_inert` 落地；相关 pytest 绿
- [x] 默认目标＝全部 rejected；可子集；夹带 completed 必拒；草稿恒 inert
- [x] 0 DeepSeek／0 launcher；F006/F009/F010 仍 false
- [x] human-inputs 仍保留 A／B／D；说明草稿≠选 B
- [ ] 普通提交并推送 `origin/codex/visual-details`

## Stop

- 禁止付费；禁止把草稿当授权；禁止代选 A／B／D；禁止改 feature_list。
