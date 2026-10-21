# Sprint：检索场景／玩法跨语言 收集／骑乘／过场／滚动／冲击波

**状态（2026-10-22）：已推送 origin/main FEATURE_SHA（docs 记录提交另记）。** `_CROSS_LINGUAL_TERMS` 增补：`collect*`→收集、`mount*`／`ride*`→骑乘、`cutscene*`／`cinematic*`→过场、`scroll*`→滚动、`shockwave*`→冲击波。语料依据 demo-phase0 真实 mechanic tags（收集／骑乘／过场画面／滚动）与检索查询（冲击波）。**不加**裸 `roll`／`shock`／`wave`（多义噪声）。验证＝**pytest**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010／人评关单**；不发明 Boss／射击语料。`RETRIEVAL_VERSION` 仍 `bm25-e5-rrf-v7`。攻击 tag-only 与既有排除合同保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 跨语言、`test_retrieval_action_aliases.py`、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

本机 demo 标签里已有「**收集**」「**骑乘**／骑乘移动」「**过场**画面」「**滚动**」，查询里也有「释放**冲击波**」。英文 collect／mount／ride／cutscene／cinematic／scroll／shockwave 以前对不上这些中文证据。这轮接上；故意不收光杆 roll／shock／wave，也不收 mountain／override／scrollbar 这类夹心词。

## Acceptance

- [x] CROSS 增补五组别名
- [x] 正向英文查询命中中文证据；非词／夹心不命中
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_retrieval_action_aliases.py -q -k collect_mount
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料。
