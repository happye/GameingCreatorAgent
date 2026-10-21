# Sprint：检索打分 inert 合同（score_is_probability／allowlist）

**状态（2026-10-22）：已推送 origin/main 7bbf773。** 增加 `SCORE_KINDS`／`ABSTENTION_REASONS`／`LEXICAL_EVIDENCE_CHANNELS` 与 `SearchResult.score_is_probability=False`；`assert_search_result_contract` 在 `_search_documents` 出口强制校验；CLI 投影改读 `result.score_is_probability`。验证=**pytest + demo-phase0 只读**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、CLI 投影、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／TD 全关

## 白话

检索分一直是排序信号，不是「有多大把握」。这轮把合同钉死：结果上必须 `score_is_probability=false`；打分种类只能是 bm25／cosine／rrf；弃权原因只能是已知那几个；候选 why 必须带「ranking signal, not probability」。谁把分当概率、或写未知弃权码，校验直接打回。

## Acceptance

- [x] SearchResult／ProjectSearchResult.score_is_probability 默认 False
- [x] assert_search_result_contract 出口强制；CLI 投影同源
- [x] fixture＋demo-phase0 只读合同绿；未知 kind／弃权／概率旗拒绝
- [ ] 已推送 `origin/main`（SHA 待填）
