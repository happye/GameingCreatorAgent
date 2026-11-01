# Sprint：持久化检索信封 parameters／embeddingSpace 加深

**状态（2026-10-22）：已推送 origin/main 3aa3ac4（docs 记录提交另记）。** 加深 `assert_persisted_retrieval_contract`：`parameters` 必为对象；`mode`∈RETRIEVAL_MODES 且＝`result.mode`；`topK`≥1 且 candidates 数≤topK；`minSimilarity`／`minSemanticMargin`／`abstentionReason` 若在 parameters 中须与 result 一致；`embeddingSpace`：hybrid／semantic 必有（dimension≥1、model／provider／revision_scope 非空、normalization＝`l2`），lexical 必须为 null。pytest + demo-phase0 `timeline.sqlite3` 只读（217 行）。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；不改写 SQLite；RETRIEVAL_VERSION 仍 `bm25-e5-rrf-v7`；攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、SQLite 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 DB、声称 F006／TD 全关

## 白话

持久化检索信封以前已经核对命中行和 result 对得上。这轮把信封上的 **parameters** 和 **embeddingSpace** 也钉死：参数里的 mode／topK／阈值要和结果一致，候选数不能超过 topK；hybrid／semantic 必须带着合法的向量空间描述（维度、模型、l2、供应商、revision），纯 lexical 反而不准带 embeddingSpace。本机 217 条只读全过，不改库、不宣称关单。

## Acceptance

- [x] parameters 对齐 mode／topK／阈值字段
- [x] embeddingSpace 按 mode 必有／必无 + 字段形态
- [x] demo-phase0 只读绿；伪造拒绝绿
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_retrieval_sqlite_local_readonly.py \
  tests/test_run_search_local_readonly.py tests/test_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不改写 artifacts／SQLite。
