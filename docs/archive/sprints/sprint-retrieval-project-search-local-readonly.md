# Sprint：项目联合检索落盘结果本机只读对照

**状态（2026-10-22）：已推送 origin/main a62690e。** 新增 `assert_project_search_document_contract`：在 `assert_search_document_contract` 之上钉死 `project-search-v1`、searchId／scopeId、项目检索版本前缀、sources 归属、`modelAnalysisCalls=0`／`newReservations=0`。CLI 落盘前与 `read_project_search` 读回时强制校验。pytest 只读扫 `artifacts/demo-phase0/project-searches/*/result.json`＋receipt 联动。验证=**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、CLI／project_search_files、本机只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 project-search JSON、声称 F006／TD 全关

## 白话

demo-phase0 里已经存了几十份项目联合检索结果。这轮给它们加上只读对照：分数不能装概率、不能声称新做了模型分析、候选必须挂在源任务列表里、读回时还要和 receipt 对得上。落盘／读盘出口都卡同一道门。

## Acceptance

- [x] assert_project_search_document_contract
- [x] CLI 落盘前 + read_project_search 读回强制
- [x] demo-phase0 全部 project-searches 只读绿；伪造外来 runId／付费声称拒绝
- [ ] 已推送 `origin/main`（SHA 待填）
