# Sprint：SQLite 持久化检索信封 mode／rank／elapsed／时间窗加深

**状态（2026-10-22）：已推送 origin/main 8396c5a（docs 记录提交另记）。** 加深 `assert_persisted_retrieval_contract`：`result.mode`∈RETRIEVAL_MODES；信封与 `result.elapsedMs` 一致（两者都在时）；hits／candidates 的 `rank` 必须为 `1..n` 连续；命中 `start_us < end_us` 且与候选 us 对齐。既有 score／evidence／media 对齐保留。pytest 只读扫 demo-phase0 `timeline.sqlite3` retrieval_runs（217）。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不改写 DB。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。既有排除合同保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 持久化合同、sqlite 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 SQLite、声称 F006／TD 全关

## 白话

SQLite 里存的检索信封以前已经核对「命中行和结果 JSON 的分数、证据、媒体对得上」。这轮再钉：检索模式必须是 lexical／semantic／hybrid 之一、名次必须从 1 排到 n 不能跳号、耗时字段两边要一致、命中时间窗不能是空的。旧库没改，只是读回时卡更紧。

## Acceptance

- [x] mode／elapsedMs／连续 rank／非空时间窗
- [x] demo-phase0 217 retrieval_runs 只读绿；伪造拒绝
- [x] 已推送 `origin/main`（feature `8396c5a`；docs 记录另提交）

## Verification

```text
pytest tests/test_retrieval_sqlite_local_readonly.py tests/test_run_search_local_readonly.py \
  tests/test_project_retrieval.py tests/test_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改写 artifacts／DB。
