# Sprint：检索 JSON 投影／candidate_sources 清单 inert 合同

**状态（2026-10-22）：待推送 origin/main。** 新增 `assert_search_document_contract`：`scoreIsProbability=false`；弃权白名单；`qualityGate` 仅允许缺席或 null；禁止 formalAcceptancePassed／humanLabels 等声称字段；弃权与候选互斥；候选 why／lexicalEvidence 白名单。CLI `_search_document` 与项目检索落盘前强制校验。新增 `assert_candidate_sources_contract`：无分、时间序、id 唯一，挂在 `candidate_sources` 出口。验证=**pytest + demo-phase0 只读**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、CLI 投影、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／TD 全关

## 白话

检索结果写进 JSON／落盘时，也不能偷偷带上「验收通过」「人标」这类字段，分数照旧不能装成概率；弃权时候选必须是空的。候选清单 candidate_sources 继续保持无分、按时间排、id 不重复。这轮把这两道门钉在出口上。

## Acceptance

- [x] assert_search_document_contract + CLI／项目落盘前强制
- [x] assert_candidate_sources_contract + candidate_sources 出口强制
- [x] fixture＋demo-phase0 只读绿；伪造 formalAcceptance／qualityGate 拒绝
- [ ] 已推送 `origin/main`（SHA 待填）
