# Sprint：TD009 match-report matches／版本／证据归属加深

**状态（2026-10-22）：已推送 origin/main 3ee0c89（docs 记录提交另记）。** 加深 `assert_match_report_contract`：`constraintJson` 须解析且含 `schemaVersion`／`version`／`vocabularyVersion`；`result.schemaVersion`／`querySchemaVersion`／`queryVersion`／`vocabularyVersion` 钉死现行常量；`notes` 为字符串列表；`matches` 为列表，每行 `actorId`／`shotId` 非空，可选 `sourceRange` 合法，`sharedEvidenceIds` 与 satisfied／opposed／counterEvidence／uncertain 的 `evidenceIds` 带冒号时须归属 `runId`。同步加深 `match_report_contract_gaps` 对应 gap 码。pytest：现行 v1.1 夹具＋伪造拒绝；legacy demo-phase0 只读 gaps。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写旧 match JSON。复合人评／静态索引仍 open。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、TD009 match-report 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 match、声称 F006／TD009 全关

## 白话

匹配报告以前已经核对「不能假装人评通过、事件号挂对任务、约束哈希对得上」。这轮再钉报告里的每一行匹配：演员号和镜头号不能空、证据帧 id 不能串到别人的任务、结果上的查询／词表版本号必须是现在这套；约束 JSON 也得带齐版本字段。旧的 v1 报告照旧只读标 gaps，不改文件、不宣称关单。

## Acceptance

- [x] assert：constraint 字段、result 版本、matches 行、evidence 归属
- [x] gaps：对应 mismatch／invalid 码
- [x] v1.1 夹具绿；legacy 只读 gaps 绿
- [x] 已推送 `origin/main`（feature `3ee0c89`；docs 记录另提交）

## Verification

```text
pytest tests/test_detail_match_report_local_readonly_td009.py \
  tests/test_detail_match_report_contract.py tests/test_actor_detail_matching.py \
  tests/test_detail_refinement_sidecar_local_readonly_td009.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改写 artifacts。
