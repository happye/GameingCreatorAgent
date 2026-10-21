# Sprint：项目联合检索 receipt↔resultSha256 绑定加深

**状态（2026-10-22）：feature 待推送（docs 记录提交另记）。** 新增 `assert_project_search_receipt_contract(receipt, *, search_id, result_bytes)`：信封必须精确等于 `project-search-receipt-v1` + searchId + `sha256(result.json 原始字节)` + `modelAnalysisCalls=0` + `newReservations=0`。`read_project_search` 改走该断言（磁盘漂移仍映射为 `storage.project_search`）。pytest + demo-phase0 全部 32 条 project-searches 只读。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；不改写 artifacts；`RETRIEVAL_VERSION` 仍 `bm25-e5-rrf-v7`；攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、`project_search_files.py`、project-search 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 JSON、声称 F006／TD 全关

## 白话

项目联合搜索落盘时会写一张 **receipt.json**，里面记着 result 文件的 sha256。这轮把「收据必须和磁盘上的 result 字节对得上、不能假装打过模型／开过预留」抽成共享合同，读盘和只读测试都走同一套。

## Acceptance

- [x] `assert_project_search_receipt_contract`
- [x] `read_project_search` 接线；漂移仍 `storage.project_search`
- [x] demo-phase0 32 条 receipt 只读绿；伪造 sha／付费／多余键拒绝绿
- [ ] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_project_search_local_readonly.py tests/test_project_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不改写 artifacts。
