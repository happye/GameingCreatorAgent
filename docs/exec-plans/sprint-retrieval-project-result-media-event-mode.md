# Sprint：项目联合检索内存结果 media／event／mode 加深

**状态（2026-10-22）：已推送 origin/main 7d2696d（docs 记录提交另记）。** 加深 `assert_project_search_result_contract`：与落盘 JSON 合同对齐——`mode`∈RETRIEVAL_MODES、`query` 为 str；源运行 `media_id`／`sha256` 不得重复；候选 `media_id` 须等于所属源 `asset.media_id`；转录允许 `event_id=None`（空串仍拒）；带冒号的 `event_id` 须归属源 `run_id`；时间范围 `start_us < end_us`。既有 inert／scoreKind／lexicalEvidence／弃权门闩保留。pytest 覆盖接受路径＋伪造 mode／媒体漂移／外来 event／重复源媒体。验证＝**pytest**（无付费／无 Playwright）。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD009／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 项目结果合同、pytest、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关、改写 artifacts

## 白话

上一轮把项目联合检索**落盘 JSON**卡紧了（媒体指纹、时间码、事件归属）。这轮把同一套规矩补到**内存里的联合检索结果**上：源任务不能共用同一段录像指纹、候选挂的媒体必须跟源任务对上、没有事件号的旁白命中继续放行、假 mode 和串门事件号照旧拒绝。落盘和内存两边口径一致，避免一边绿一边漏。

## Acceptance

- [x] project result：mode／query、源 media／sha 唯一、候选 media 对齐、eventId None／owned、时间范围
- [x] 既有 inert／弃权／外来 run 拒绝仍绿；CLI 联合三源仍绿
- [x] 已推送 `origin/main`（feature `7d2696d`；docs 记录另提交）

## Verification

```text
pytest tests/test_project_retrieval.py tests/test_project_search_local_readonly.py \
  tests/test_run_search_local_readonly.py tests/test_retrieval_sqlite_local_readonly.py \
  tests/test_retrieval_action_aliases.py tests/test_retrieval_local_completed_td010.py \
  tests/test_retrieval.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改 `RETRIEVAL_VERSION`；攻击 tag-only 与转录 `eventId=None` 合同保留。
