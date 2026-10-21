# Sprint：检索场景／HUD 跨语言（血条／场地／草地／建筑／掩体）

**状态（2026-10-22）：已推送 origin/main 73e75d1。** 基于 demo-phase0 真实正文：`_CROSS_LINGUAL_TERMS` 增补 healthbar／hp→血条、building→建筑、arena／field→场地、grass→草地、cover→掩体。保留 avatar 可检索（不停用）。pytest + demo-phase0 Completed 只读。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料；不改写 DB。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 场景／HUD 跨语言、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关、把 avatar 加回停用词

## 白话

本机片里常见血条、场地、草地、建筑、掩体，英文搜 healthbar／hp／arena／field／grass／building／cover 以前对不上。这轮加上跨语言扩展。avatar 肖像查询继续可用，没有退回停用词。没编 Boss／射击假片，没改版本号。

## Acceptance

- [x] healthbar／hp／building／arena／field／grass／cover 跨语言
- [x] 非词误扩拒绝；avatar 仍可检索
- [x] demo-phase0 Completed 只读绿
- [ ] 已推送 `origin/main`（SHA 待填）
