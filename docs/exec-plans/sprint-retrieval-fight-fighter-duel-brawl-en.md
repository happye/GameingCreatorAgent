# Sprint：检索 fight 英文别名 fighter／duel／brawl（堵 tag-only 漏洞）

**状态（2026-10-22）：待推送 origin/main。** `_ACTION_TERMS["fight"]` 与 `_CROSS_LINGUAL_TERMS` 增补 `fighter`／`fighters`／`duel`／`brawl`（及变形）。此前 `fighter` 只靠跨语言塞入「战斗」做 BM25，却未识别为 fight 动作，demo-phase0 上会漏进裸「战斗」标签噪声。现与 `fight`／`combat` 同路径：词法交叉扩展 + tag-only 排除。pytest + demo-phase0 Completed 只读。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。攻击 tag-only 仍保留。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 动作／跨语言别名、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

英文搜 fighter／fighters 时，系统以前只会把「战斗」塞进检索词，却没把它当成战斗动作，结果本机完成片里那些只打了「战斗」标签、正文没有对战描写的伤害飘字片段会漏进来。这轮把 fighter／duel／brawl 收进战斗动作：该扩的中文别名照扩，裸标签噪声照扔。没改版本号，也没动攻击只靠标签还能召回的约定。

## Acceptance

- [x] fight 动作含 fighter／duel／brawl 等英文别名；跨语言表同步
- [x] 正例／tag-only 噪声／非动作词边界 pytest 绿
- [x] demo-phase0 Completed 只读：fighter／duel／brawl 命中均有正文动作词
- [ ] 已推送 `origin/main`（SHA 待填）