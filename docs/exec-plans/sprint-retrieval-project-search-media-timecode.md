# Sprint：项目联合检索投影 media／sha／timecode 加深 + 转录 eventId=None

**状态（2026-10-22）：已推送 origin/main 7c857c9（docs 记录提交另记）。** 加深 `assert_project_search_document_contract`：`mode`∈RETRIEVAL_MODES、`query` 为 str、`topK≥1`；每个 source 须有非空 `mediaId` 与 64-hex `sourceSha256`；候选 `mediaId`／`sourceSha256` 须与所属 source 对齐；`startTimecode`／`endTimecode` 非空；有 colon 的 `eventId` 须归属源 `runId`。同时修正 `assert_run_search_document_contract`：转录命中允许 `eventId=None`（空串仍拒），避免联合检索子集路径误杀。pytest 只读扫 demo-phase0 `project-searches`＋`runs/*/searches`；CLI 联合三源（含转录）绿。验证＝**pytest + 只读 JSON／SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD009／TD010／人评关单；不改写 artifacts。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 项目／单任务合同、只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关、改写旧 project-search／run-search JSON

## 白话

项目联合检索落盘以前已经核对「分数不是概率、没偷偷做新模型分析、候选挂在源任务列表里」。这轮再钉几件具体的：每条源任务要带对媒体指纹、候选的媒体和时间码不能空或对不上、带着冒号的事件号必须属于那个任务。另外修了一个坑：只有旁白／字幕、没有事件号的命中（`eventId=None`）以前会被单任务合同误杀，联合检索「建造房屋」三源里那个转录任务会挂；现在明确允许空事件号，空字符串照旧拒绝。

## Acceptance

- [x] project-search：mode／query／topK、source media／sha、候选对齐、owned eventId、timecode
- [x] run-search：允许 eventId=None；空串拒绝；既有 media／why／timecode 不变
- [x] demo-phase0 project-searches + runs/*/searches 只读绿；CLI 联合三源绿
- [x] 已推送 `origin/main`（feature `7c857c9`；docs 记录另提交）

## Verification

```text
pytest tests/test_project_retrieval.py tests/test_project_search_local_readonly.py \
  tests/test_run_search_local_readonly.py tests/test_retrieval_sqlite_local_readonly.py \
  tests/test_retrieval_action_aliases.py tests/test_retrieval_local_completed_td010.py \
  tests/test_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改 `RETRIEVAL_VERSION`；攻击 tag-only 合同保留。
