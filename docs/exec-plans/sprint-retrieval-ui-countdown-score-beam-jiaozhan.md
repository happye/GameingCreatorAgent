# Sprint：检索 UI 观察跨语言（倒计时／比分／光束）+ 交战别名

**状态（2026-10-22）：待推送 origin/main。** 基于 demo-phase0 真实正文：`_CROSS_LINGUAL_TERMS` 增补 countdown／timer→倒计时／计时、score／scoreboard→比分、beam→光束；`_ACTION_TERMS["fight"]` 增补「交战」（tag-only 噪声仍排除）。pytest + demo-phase0 Completed 只读。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料；不改写 DB。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` UI 跨语言与 fight 交战别名、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

本机片里顶部常写倒计时、比分、光束，英文搜 countdown／timer／score／beam 以前对不上。这轮加上跨语言扩展。正文里偶发「交战」也收进战斗动作，只靠标签的交战仍当噪声扔掉。没编 Boss／射击假片，没改版本号。

## Acceptance

- [x] countdown／timer／score／scoreboard／beam 跨语言；交战∈fight
- [x] 非词误扩拒绝；交战 tag-only 排除
- [x] demo-phase0 Completed 只读绿
- [ ] 已推送 `origin/main`（SHA 待填）
