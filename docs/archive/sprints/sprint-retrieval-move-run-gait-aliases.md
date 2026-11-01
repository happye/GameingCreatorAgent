# Sprint：检索 move 奔跑／迈步／running 步态别名

**状态（2026-10-22）：已推送 origin/main c9773d4（docs 记录提交另记）。** 扩展 `_ACTION_TERMS["move"]`：中文 `奔跑`／`迈步`；英文 `running`／`runs`／`ran`／`runner`／`runners`（**不加**裸 `run`，避免与 `run-0` 任务号撞车）。`_CROSS_LINGUAL_TERMS`：running 系列→`移动`。move 仍在 `_TAG_ONLY_NOISE_ACTIONS`，裸 mechanicTag 铬层继续排除。语料依据 demo-phase0 真实观察（奔跑／迈步高频）。验证＝**pytest**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 别名、`test_retrieval_action_aliases.py`、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

demo 里很多片段写的是「向城堡方向**奔跑**」「向前**迈步**」。英文搜 running／runner 以前对不上这些中文观察。这轮把奔跑／迈步和 running 系列收进 move 步态别名（和之前的 walk／行走同一路），并故意不收光杆 run，免得和任务号 run-0 搅在一起。只有标签、正文没有移动证据的铬层命中照旧剔除。

## Acceptance

- [x] move：奔跑／迈步／running／runs／ran／runner／runners
- [x] 跨语言 running→移动；裸 run 不召回
- [x] tag-only 铬层排除仍适用于新别名
- [x] 已推送 `origin/main`（feature `c9773d4`；docs 记录另提交）

## Verification

```text
pytest tests/test_retrieval_action_aliases.py tests/test_retrieval_local_completed_td010.py \
  tests/test_retrieval.py tests/test_project_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改 `RETRIEVAL_VERSION`；攻击 tag-only 合同保留。
