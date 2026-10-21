# Sprint：内存检索结果 embedding_metadata 按 mode 加深

**状态（2026-10-22）：已推送 origin/main FEATURE_SHA（docs 记录提交另记）。** 新增 `_assert_search_embedding_metadata`：lexical 不得带 `embedding_metadata`；hybrid／semantic **有候选时**必须带；空弃权可省略。有 metadata 时校验 `provider`／`requested_model`／`schema_version`／`attempt≥1`；`actual_model` 若非 null 须＝requested。挂入 `assert_search_result_contract` 与 `assert_project_search_result_contract`；并校验 `min_similarity`／`min_semantic_margin` 数值。验证＝**pytest**（含 fixture hybrid／lexical）。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；`RETRIEVAL_VERSION` 仍 `bm25-e5-rrf-v7`；攻击 tag-only 仍保留。场景别名本轮不扩（收益递减，轮换合同）。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、相关 pytest、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

落盘 JSON 的 embedding 元数据上一轮已经钉过。这轮把**内存里的检索结果对象**也对齐：纯词法搜索不准带 embedding_metadata；混合／语义只要真正搜出了候选，就必须带上供应商／模型／schema／attempt；空查询弃权可以没有。实际模型若写了就必须和请求模型一致。

## Acceptance

- [x] 共享 `_assert_search_embedding_metadata`；search／project result 挂上
- [x] 阈值字段类型护栏
- [x] pytest 绿；伪造 mode／model 漂移拒绝
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_retrieval.py tests/test_project_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单。
