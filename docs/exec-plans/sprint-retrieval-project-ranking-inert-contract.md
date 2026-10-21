# Sprint：项目联合检索打分 inert 合同

**状态（2026-10-22）：已推送 origin/main 549adfc。** 新增 `assert_project_search_result_contract`：`score_is_probability=False`；`retrieval_version` 须为 `PROJECT_RETRIEVAL_VERSION` （或 `-saved-details-*` 后缀）；`scope_id` 以 `project-` 开头；弃权原因白名单；弃权与候选互斥；候选 `run_id` 必须落在 sources；候选 id 不重复；沿用 score_kind／why／lexicalEvidence 白名单。`search_timelines` 出口强制校验并显式传递 `score_is_probability`。验证=**pytest + demo-phase0 只读**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、project／local-completed 测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／TD 全关

## 白话

单任务检索已经钉死「分不是概率」。项目里一次搜多个录像时，还要保证：每条命中能追溯到所选源任务、scope 标识合法、版本是项目检索合同、空动作召回的弃权原因仍然清楚。这轮在联合检索出口加上同样的 inert 校验，乱挂别的 run_id 或把分标成概率会直接打回。

## Acceptance

- [x] `assert_project_search_result_contract` + `search_timelines` 出口强制
- [x] fixture：命中／jump 弃权／空查询；拒绝概率旗与外来 run_id
- [x] demo-phase0 只读联合检索合同绿
- [ ] 已推送 `origin/main`（SHA 待填）
