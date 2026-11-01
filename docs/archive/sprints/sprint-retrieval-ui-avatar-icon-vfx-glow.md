# Sprint：检索 UI 肖像／图标／特效跨语言（avatar 出停用词）

**状态（2026-10-22）：已推送 origin/main da231a0。** 基于 demo-phase0 真实正文（特效≈63、光效≈24、图标≈10、头像≈8）：`_CROSS_LINGUAL_TERMS` 增补 avatar→头像、icon→图标、vfx／fx→特效、glow→光效；将 `avatar` 移出 `_STOP_WORDS`，避免「avatar」单独查询被 `empty_query` 弃权。pytest + demo-phase0 Completed 只读。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料；不改写 DB。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` UI 跨语言与 stopword、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

本机片里常写头像、图标、特效、光效，英文搜 avatar／icon／vfx／glow 以前对不上；更糟的是 avatar 被当成停用词，单独搜直接空查询弃权。这轮把 avatar 从停用词拿出来，并加上跨语言扩展。没编 Boss／射击假片，没改版本号。

## Acceptance

- [x] avatar 非停用词；avatar／icon／vfx／fx／glow 跨语言
- [x] 非词误扩拒绝；demo-phase0 Completed 只读绿
- [ ] 已推送 `origin/main`（SHA 待填）
