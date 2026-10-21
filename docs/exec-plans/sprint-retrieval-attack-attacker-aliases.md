# Sprint：检索 attack 英文施事别名 attacker／attackers

**状态（2026-10-22）：待推送 origin/main。** `_ACTION_TERMS["attack"]` 与 `_CROSS_LINGUAL_TERMS` 增补 `attacker`／`attackers`。此前 `attacker` 只靠跨语言塞入「攻击」做 BM25，未识别为 attack 动作，demo-phase0 命中缺少 `lexicalEvidence=mechanic_tags`；`attackers` 完全无召回。现与 `attack` 同路径，**保留** TD010 攻击 tag-only 召回。pytest + demo-phase0 Completed 只读。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 动作／跨语言别名、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关、把攻击 tag-only 改成噪声

## 白话

英文搜 attacker 时，以前只会塞「攻击」进检索词，却没当成攻击动作，本机完成片里靠「攻击」标签召回的片段对得上，但证据通道标成空；搜 attackers 更是零结果。这轮把 attacker／attackers 收进攻击动作：命中集合与「攻击」对齐，标签命中会标成 mechanic_tags。攻击只靠标签还能召回的旧约定特意保留。

## Acceptance

- [x] attack 动作含 attacker／attackers；跨语言表含 attackers
- [x] tag-only 仍可达且 lexicalEvidence=mechanic_tags；非动作词边界 pytest 绿
- [x] demo-phase0 Completed 只读：attacker／attackers 与「攻击」同命中集
- [ ] 已推送 `origin/main`（SHA 待填）