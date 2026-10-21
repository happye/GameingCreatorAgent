# Sprint：SQLite retrieval_runs 本机只读信封合同

**状态（2026-10-22）：已推送 origin/main 6e9daa1。** 新增 `assert_persisted_retrieval_contract`：在 run-search 归属合同之上钉死 `load_retrieval` 信封——queryHash＝SHA256(query)、result 与行级 hits 的 rank／candidateId／eventId／score／scoreKind 对齐、version／runId／query 与 result 一致。`SqliteTimelineStore.load_retrieval` 读回强制（底层 `retrieval_persistence.load_retrieval` 仍供窄存储单测用最小 fixture）。pytest 只读扫 demo-phase0 全部 `retrieval_runs`（217）。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不改写 DB。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 信封合同、`sqlite_store.load_retrieval` 门闩、本机只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 timeline.sqlite3、声称 F006／TD 全关

## 白话

demo-phase0 的 SQLite 里已经存了两百多条检索记录：一边是结果 JSON，一边是命中表。这轮给读回加上信封合同——查询哈希要对、JSON 里的候选要和命中表逐行对齐（名次、片段、事件、分数），不能一边改一边装没改。工作台／CLI 走 Store 读回时卡同一道门。没改库里的旧数据。

## Acceptance

- [x] assert_persisted_retrieval_contract
- [x] SqliteTimelineStore.load_retrieval 强制
- [x] demo-phase0 全部 retrieval_runs 只读绿；hits 漂移／假验收／坏 queryHash 拒绝
- [ ] 已推送 `origin/main`（SHA 待填）