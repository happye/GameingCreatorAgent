# Sprint：检索场景名词跨语言 升起／护罩／悬浮／阶梯／拥抱／圆环／音符

**状态（2026-10-22）：已推送 origin/main 8bec125（docs 记录提交另记）。** `_CROSS_LINGUAL_TERMS` 增补：`rising`／`rises`→升起、`shield(s)`／`barrier(s)`→护罩、`floating`／`float(s|ed)`／`hover(ing|s)`→悬浮、`stair(s|case)`／`ladder(s)`→阶梯、`hug`／`embrace` 系列→拥抱、`ring(s)`→圆环、`note(s)`→音符。语料依据 demo-phase0 真实观察。**不加**裸 `rose`／`float`（多义词）。验证＝**pytest**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。既有排除合同保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 跨语言、`test_retrieval_action_aliases.py`、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

demo 里还有「向上**升起**」「球形**护罩**」「**悬浮**平台」「绿色**阶梯**」「**拥抱**粉色角色」「粉色**圆环**」「黄色**音符**」。英文 rising／shield／hover／stairs／hug／ring／note 以前对不上。这轮接上；故意不收 rose／光杆 float，免得花朵义或「漂浮物」乱入。earring／notebook／upstairs 这类连写或夹心词也不算命中。

## Acceptance

- [x] rising／shield／barrier／floating／hover／stairs／ladder／hug／embrace／ring／note 系列映射
- [x] rose／float／earring／notebook／upstairs 等不召回
- [x] 既有 scene／move 合同回归绿
- [x] 已推送 `origin/main`（feature `8bec125`；docs 记录另提交）

## Verification

```text
pytest tests/test_retrieval_action_aliases.py tests/test_retrieval_local_completed_td010.py \
  tests/test_retrieval.py tests/test_project_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改 `RETRIEVAL_VERSION`；既有排除合同保留。
