# Sprint：TD009 match-report↔sidecar 证据 partId／condition 加深

**状态（2026-10-22）：feature 待推送（docs 记录提交另记）。** `assert_match_report_sidecar_binding_contract`：证据桶（satisfied／opposed／counterEvidence／uncertain）每条须有非空 `partId`，以及对象 `condition` 且 `kind`／`partGroup`／`value` 均为非空字符串。`match_report_sidecar_binding_gaps` 新码：`match_evidence_part_id_invalid`／`match_evidence_condition_*`。pytest + demo-phase0 legacy matches 只读。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写 artifacts；MATCH_REPORT_VERSION／MATCHER_VERSION 不动。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、TD009 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 JSON、声称 F006／TD 全关

## 白话

匹配报告里每条证据（满意／反对／反证／不确定）都挂着 **部位编号 partId** 和 **条件 condition**（种类／部位组／取值，比如头发颜色＝白）。这轮把这些字段钉进侧车绑定合同：缺了、空了、写成字符串而不是对象，都会拒绝；软缺口码也能指出来。

## Acceptance

- [x] binding 加深 partId／condition.kind／partGroup／value
- [x] gaps 新码
- [x] 只读绿；伪造拒绝绿
- [ ] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_detail_match_report_local_readonly_td009.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD009／人评／静态索引关单；不改写 artifacts。
