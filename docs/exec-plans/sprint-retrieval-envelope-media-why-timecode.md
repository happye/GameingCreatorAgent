# Sprint：检索信封／单任务投影 media／why／timecode 加深

**状态（2026-10-22）：已推送 origin/main 1b885d1。** 加深 `assert_run_search_document_contract`：候选 `eventId` 须为 `{runId}:{mediaId}:…`（裸合成 id 仍允许）、`why` 须含 inert「ranking signal／not probability」、`startTimecode`／`endTimecode` 非空。加深 `assert_persisted_retrieval_contract`：信封 `mediaId` 有效且与每个候选 `mediaId` 对齐。pytest 只读扫 demo-phase0 `retrieval_runs`（217）与 `runs/*/searches`（~204）。验证＝**pytest + 只读 SQLite／JSON**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不改写 DB／旧 JSON。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 合同加深、只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关、改写 artifacts

## 白话

检索落盘和 SQLite 读回以前已经核对名次、分数、证据和时间范围。这轮再钉三件事：候选必须挂对媒体 id、为什么命中的说明里必须写明「不是概率」、起止时间码不能空；信封上的媒体 id 还要和每个候选对得上。旧库旧 JSON 没改，只是读的时候卡更紧。

## Acceptance

- [x] run-search：media／event 前缀、why inert、timecode
- [x] persisted：信封 mediaId↔候选；漂移拒绝
- [x] demo-phase0 retrieval_runs + runs/*/searches 只读绿
- [ ] 已推送 `origin/main`（SHA 待填）
