# Sprint：检索 heal／damage 跨语言别名 + interacted + 信封 evidence／range

**状态（2026-10-22）：待推送 origin/main。** 三件事合成一轮离线检索质量：(1) _CROSS_LINGUAL_TERMS 增补 heal／healing／healed／heals→治疗、damage／damaging／damages→伤害；(2) _ACTION_TERMS["interact"] 增补 interacted；(3) ssert_persisted_retrieval_contract 加深：hits 与 candidates 的 start_us／end_us、evidence_ids↔evidenceIds 必须对齐。pytest 单元 + demo-phase0 Completed／retrieval_runs 只读。验证＝**pytest + 只读 SQLite／JSON**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不改写 DB。RETRIEVAL_VERSION 仍为 m25-e5-rrf-v7。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：main
- Owned：
etrieval.py 跨语言／interact 别名与信封加深、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关、改写 timeline.sqlite3

## 白话

英文搜 heal／damage 以前对不上本机片里写了「治疗」「伤害」的中文正文；这轮加上跨语言扩展。interacted 也收进交互动作，空证据时词法模式照旧弃权。顺手把 SQLite 读回信封再钉一层：命中表的时间范围和证据 ID 必须和结果 JSON 里的候选对得上，不能只对名次／分数。没改版本号，没改库，攻击只靠标签还能召回的约定没动。

## Acceptance

- [x] heal／damage 跨语言→治疗／伤害；非动作词不误扩
- [x] interacted→interact；词法空证据 abstention
- [x] 信封 evidence／range 漂移拒绝；demo-phase0 heal／damage 只读绿
- [ ] 已推送 origin/main（SHA 待填）
