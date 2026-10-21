# Sprint：单任务／项目检索 embedding 元数据 + topK 加深

**状态（2026-10-22）：已推送 origin/main 7aad0df（docs 记录提交另记）。** 新增 `_assert_retrieval_embedding_metadata`：lexical 不得带 `embedding`；hybrid／semantic 须有对象且 `provider`／`requested_model`／`actual_model`／`schema_version` 非空，且 actual＝requested。挂入 `assert_run_search_document_contract`（另：`elapsedMs`≥0、`minSimilarity` 数值、`minSemanticMargin` 数值或 null）与 `assert_project_search_document_contract`（另：`len(candidates)≤topK`）。pytest + demo-phase0 runs/*/searches（204）与 project-searches 只读。验证＝**pytest + 只读 JSON／SQLite**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；不改写 artifacts；RETRIEVAL_VERSION 仍 `bm25-e5-rrf-v7`；攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、run／project 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 JSON、声称 F006／TD 全关

## 白话

上一轮钉了 SQLite 信封上的 parameters／embeddingSpace。这轮把落盘的**单任务搜索 JSON**和**项目联合搜索 JSON**里的 embedding 执行元数据也钉死：纯词法搜索不准塞 embedding；混合／语义搜索必须有供应商、请求模型、实际模型（两者一致）和 schema 版本；项目搜索候选数不能超过 topK。本机旧文件只读核对，不改磁盘、不宣称关单。

## Acceptance

- [x] 共享 embedding 元数据门闩按 mode
- [x] run-search：elapsed／阈值；project：candidates≤topK
- [x] demo-phase0 只读绿；伪造拒绝绿
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_run_search_local_readonly.py \
  tests/test_project_search_local_readonly.py \
  tests/test_retrieval_sqlite_local_readonly.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不改写 artifacts。
