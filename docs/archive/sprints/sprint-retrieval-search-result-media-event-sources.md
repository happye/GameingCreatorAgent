# Sprint：内存检索结果／候选清单 media／event／sources 加深

**状态（2026-10-22）：已推送 origin/main 5e236d1（docs 记录提交另记）。** 加深 `assert_search_result_contract`：与落盘 search-document 对齐——`mode`／`query`／`run_id`；候选 `candidate_id` 唯一非空、`media_id` 非空、`source_range` 非空、`evidence_ids` 合法；转录允许 `event_id=None`；带冒号 eventId 在非 `project-` scope 下须归属 `run_id`（联合检索中间结果的 `run_id=project-…` 放行源任务 event）。加深 `assert_candidate_sources_contract`：media／时间窗／event／evidence。pytest 覆盖伪造＋demo-phase0。验证＝**pytest**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD 关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。既有排除合同保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 内存结果／清单合同、pytest、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

落盘 JSON 刚卡过名次和媒体。这轮把同一套规矩补到**内存里的单任务检索结果**和**候选清单**：候选 id 不能空或重复、媒体和时间窗要齐、旁白命中可以没有事件号、单任务时事件号必须挂对任务；项目联合检索用 project- 作用域时不误杀各源任务自己的事件号。候选清单也不能塞空媒体或空事件号字符串。

## Acceptance

- [x] search_result：mode／media／unique id／event None／project-scope 例外
- [x] candidate_sources：media／span／event／evidence
- [x] demo-phase0／联合检索回归绿
- [x] 已推送 `origin/main`（feature `5e236d1`；docs 记录另提交）

## Verification

```text
pytest tests/test_retrieval_action_aliases.py tests/test_retrieval_local_completed_td010.py \
  tests/test_retrieval.py tests/test_project_retrieval.py tests/test_run_search_local_readonly.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改 `RETRIEVAL_VERSION`。
