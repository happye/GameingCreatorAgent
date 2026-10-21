# Sprint：检索场景名词跨语言 平台／烟雾／落地／城堡

**状态（2026-10-22）：已推送 origin/main 296ac1f（docs 记录提交另记）。** `_CROSS_LINGUAL_TERMS` 增补：`platform(s)`→平台、`smoke`／`smokes`／`smoking`→烟雾、`landing(s)`／`landed`／`lands`→落地、`castle(s)`→城堡。语料依据 demo-phase0 真实观察（平台／烟雾／落地／城堡高频）。**不加**裸 `land`（homeland／inland 等非游戏义）。验证＝**pytest**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only、裸 `run` 不入 move、转录 `eventId=None` 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 跨语言、`test_retrieval_action_aliases.py`、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

demo 里到处是「悬浮**平台**」「白色**烟雾**轨迹」「跳跃后**落地**」「向**城堡**方向奔跑」。用英文搜 platform／smoke／landing／castle 以前对不上这些中文观察。这轮把四组场景名词接上跨语言扩展；故意不收光杆 land，免得 homeland 这类词误伤。

## Acceptance

- [x] platform／smoke／landing／castle 系列→平台／烟雾／落地／城堡
- [x] 裸 land 与 lookalike 不召回
- [x] 既有 scene／move／attack 合同回归绿
- [x] 已推送 `origin/main`（feature `296ac1f`；docs 记录另提交）

## Verification

```text
pytest tests/test_retrieval_action_aliases.py tests/test_retrieval_local_completed_td010.py \
  tests/test_retrieval.py tests/test_project_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改 `RETRIEVAL_VERSION`；攻击 tag-only 与裸 run 排除合同保留。
