# Sprint：单任务检索落盘 JSON 本机只读归属合同

**状态（2026-10-22）：已推送 origin/main 54303a2。** 新增 `assert_run_search_document_contract`：在 `assert_search_document_contract` 之上钉死 `schemaVersion=1`、runId、retrievalVersion 前缀 `bm25-e5-rrf-v*`、mode、可选 retrievalId 形状、scoreKind∈SCORE_KINDS、候选 eventId 不得挂到外来 run（`:` 前缀归属）。CLI `_search_document` 落盘前强制。pytest 只读扫 `artifacts/demo-phase0/runs/*/searches/*.json`（204 份）。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不改写旧 search JSON。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、CLI `_search_document`、本机只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 searches JSON、声称 F006／TD 全关

## 白话

demo-phase0 每个任务目录下已经存了两百多份单任务检索结果 JSON。这轮给它们加上只读归属合同：任务号要对、版本号得是 bm25-e5-rrf 这一族、打分种类合法、候选事件不能偷偷挂到别人的任务上，也不能冒充验收通过。CLI 落盘前卡同一道门。没改旧文件。

## Acceptance

- [x] assert_run_search_document_contract + RETRIEVAL_MODES／VERSION_PREFIX
- [x] CLI `_search_document` 强制
- [x] demo-phase0 全部 runs/*/searches 只读绿；外来 event／错 run／假验收／非法 scoreKind 拒绝
- [ ] 已推送 `origin/main`（SHA 待填）