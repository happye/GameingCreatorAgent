# Sprint：检索场景名词跨语言 看台／闪光／轨迹

**状态（2026-10-22）：已推送 origin/main 1485255（docs 记录提交另记）。** `_CROSS_LINGUAL_TERMS` 增补：`bleacher(s)`／`grandstand(s)`→看台、`flash`／`flashes`／`flashing`→闪光、`trail(s)`／`trajectory(ies)`→轨迹。语料依据 demo-phase0 真实观察（看台／闪光／轨迹高频）。**不加**裸 `stand`／`stands`／`standing`（非看台义太多）。验证＝**pytest**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only、裸 run／land 排除、转录 `eventId=None` 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 跨语言、`test_retrieval_action_aliases.py`、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

demo 里竞技场背景常写「有**看台**」、技能命中有「白色**闪光**」、奔跑身后有「烟雾**轨迹**」。英文 bleacher／grandstand／flash／trail／trajectory 以前对不上。这轮接上；故意不收 stand／stands，免得站立／货架这类词搅进来。flashback／flashlight／trailhead 这类连写词也不算命中。

## Acceptance

- [x] bleacher／grandstand／flash／trail／trajectory 系列→看台／闪光／轨迹
- [x] stand／flashback／trailhead 等不召回
- [x] 既有 scene／move 合同回归绿
- [x] 已推送 `origin/main`（feature `1485255`；docs 记录另提交）

## Verification

```text
pytest tests/test_retrieval_action_aliases.py tests/test_retrieval_local_completed_td010.py \
  tests/test_retrieval.py tests/test_project_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改 `RETRIEVAL_VERSION`；既有排除合同保留。
