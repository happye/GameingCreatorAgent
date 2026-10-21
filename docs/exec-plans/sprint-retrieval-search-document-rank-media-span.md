# Sprint：检索 JSON 投影 rank／media／时间窗加深

**状态（2026-10-22）：已推送 origin/main e0e54d7（docs 记录提交另记）。** 加深共享 `assert_search_document_contract`：候选 `rank` 必须为 `1..n` 连续；`candidateId`／`mediaId` 非空；`scoreKind`∈SCORE_KINDS；`startUs < endUs`；`startTimecode`／`endTimecode` 非空。既有 inert why／lexicalEvidence／弃权／禁声称保留。单任务与项目投影均经此门闩。pytest 只读扫 demo-phase0 runs/*/searches 与 project-searches。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不改写旧 JSON。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。既有排除合同保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 共享投影合同、只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 artifacts、声称 F006／TD 全关

## 白话

单任务和项目检索落盘 JSON 共用一道门。以前这道门主要防「把分数装成概率、乱写弃权、偷偷声称验收」。这轮再钉：名次必须从 1 排到 n、每条候选要有媒体 id、时间窗不能空、打分种类必须是认识的那几种。旧 JSON 没改，读的时候卡更紧。

## Acceptance

- [x] search-document：连续 rank／mediaId／scoreKind／us 与 timecode
- [x] run-search／project-search／sqlite 组合回归绿
- [x] 已推送 `origin/main`（feature `e0e54d7`；docs 记录另提交）

## Verification

```text
pytest tests/test_run_search_local_readonly.py tests/test_project_search_local_readonly.py \
  tests/test_retrieval_sqlite_local_readonly.py tests/test_project_retrieval.py \
  tests/test_retrieval_action_aliases.py tests/test_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改写 artifacts。
