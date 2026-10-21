# Sprint：检索否定保护不受裸 mechanicTags 覆盖（TD010）

**状态（2026-10-22）：已交付（待推送）。** `_denied_action_documents` 仅在 observable facts／transcripts（`positive_text`）上判定显式否定与肯定；裸 `mechanicTags` 不再单独击穿「事实已否定该动作」的排除。0 付费；不代选 A／B／D；不标 F006 true；不宣称人评／验收通过；不声称覆盖缺口已清。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、`test_retrieval_negation.py`、本 sprint、tech-debt／交接顶栏
- 不做：付费视觉、改 feature_list 为 true、代选 A／B／D、声称 F006 通过

## 白话

以前：镜头事实写着「没有跳跃」，但标签里挂了 jump，检索「跳跃」时仍可能把这段当命中。现在：否定保护只看事实／字幕正文，标签不能单独拆掉否定。

## Acceptance

- [x] Document 区分 text 与 positive_text
- [x] 否定护栏扫描 positive_text
- [x] 回归 pytest：裸 tag 无法击穿显式否定；原有 negation 套件绿
- [x] tech-debt TD010 记录离线进展
- [ ] 已推送 `origin/main`（推送后勾）
