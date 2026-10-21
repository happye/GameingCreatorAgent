# Sprint：检索 move 步态别名 walk／行走／走动／位移

**状态（2026-10-22）：已推送 origin/main 8d47ba7。** `_ACTION_TERMS["move"]` 与 `_CROSS_LINGUAL_TERMS` 增补 `walk`／`walking`／`walked`／`walks` 与中文 `行走`／`走动`／`位移`。词法交叉扩展到「移动」等；move 仍在 tag-only 噪声集。顺手把跨语言词边界与动作识别对齐为含 `_`，避免 `walk_walk` 之类下划线拼接误扩。pytest + demo-phase0 Completed 只读：walk 系列与「移动」同命中集，正文须含移动类词。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。攻击 tag-only 仍保留。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 动作／跨语言别名与边界、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

英文搜 walk／walking，或中文搜行走／走动／位移时，以前对不上本机完成片里正文写了「移动」的片段。这轮把这些词收进移动动作，检索会交叉扩到「移动」，裸「角色移动」标签噪声照旧扔掉。另外修了跨语言匹配的下划线边界，避免 walk_walk 这种拼接词误扩。没改版本号，攻击只靠标签还能召回的约定没动。

## Acceptance

- [x] move 含 walk／行走／走动／位移；跨语言 walk→移动
- [x] 跨语言词边界含 `_`；tag-only 噪声／非动作词 pytest 绿
- [x] demo-phase0 Completed：walk 系列与「移动」同命中集
- [ ] 已推送 `origin/main`（SHA 待填）