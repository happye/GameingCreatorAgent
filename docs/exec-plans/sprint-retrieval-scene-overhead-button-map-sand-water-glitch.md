# Sprint：检索场景跨语言 俯视／按钮／地图／沙地／水域／失真／扭曲／石柱

**状态（2026-10-22）：已推送 origin/main FEATURE_SHA（docs 记录提交另记）。** `_CROSS_LINGUAL_TERMS` 增补：`overhead`／`topdown`→俯视、`button(s)`→按钮、`map(s)`→地图、`sand*`→沙地、`water(s)`→水域、`glitch(es)`→失真、`distortion(s)`→扭曲、`pillar(s)`→石柱。语料依据 demo-phase0 真实 facts／tags（俯视视角、技能按钮、地图场景、沙地／水域、glitch／distortion、stone pillars）。**不加** mapping／bitmap／sandwich／waterfall／distort／pillow 等夹心或残词。验证＝**pytest**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；不发明 Boss／射击语料。`RETRIEVAL_VERSION` 仍 `bm25-e5-rrf-v7`；攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 跨语言、`test_retrieval_action_aliases.py`、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

本机画面描述里大量「**俯视**视角」、右侧「技能**按钮**」、「**地图**场景」、「**沙地**／**水域**」、花屏「**失真**／**扭曲**」，入口还有「石柱」。英文 overhead／topdown／button／map／sand／water／glitch／distortion／pillar 以前对不上。这轮接上；mapping、waterfall、sandwich、pillow 这类夹心词不算命中。

## Acceptance

- [x] CROSS 增补八组别名
- [x] 正向命中中文证据；非词／夹心不命中
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_retrieval_action_aliases.py -q -k overhead_button
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料。
