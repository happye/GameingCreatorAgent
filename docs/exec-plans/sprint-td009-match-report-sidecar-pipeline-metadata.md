# Sprint：TD009 match-report↔sidecar pipeline／provider／metadata 绑定加深

**状态（2026-10-22）：已推送 origin/main 0bbab05（docs 记录提交另记）。** 加深 `assert_match_report_sidecar_binding_contract`：canonical `configurationHash`（64-hex）、`pipelineVersion`、`provider`、`requestedModel`、`promptVersion` 非空；有 result 侧车时 `metadata` 为对象，且 `provider`／`requested_model`／`actual_model`／`prompt_version` 分别对齐 canonical／actualModel。`match_report_sidecar_binding_gaps` 映射同步新码。pytest：legacy 三份仍 gaps==()；伪造 config／pipeline／provider／prompt_version 拒绝。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写旧 artifacts。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、TD009 match-report 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 artifacts、声称 F006／TD009 全关

## 白话

匹配报告和侧车已经对过证据、时间窗、模型和 baseRun。这轮再钉规范载荷里的配置哈希、管线版本、供应商，以及结果 metadata 里的 provider／请求模型／实际模型／prompt 版本必须跟请求规范载荷对得上，不能各写各的。旧三份只读仍过；软缺口码一并跟上。不改磁盘、不宣称关单。

## Acceptance

- [x] binding：configurationHash／pipeline／provider／requestedModel／promptVersion
- [x] result metadata 四字段对齐；gaps 新码
- [x] legacy 绿；伪造拒绝绿
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_detail_match_report_local_readonly_td009.py \
  tests/test_detail_match_report_contract.py \
  tests/test_detail_refinement_sidecar_local_readonly_td009.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD009／F010／人评关单；不改写 artifacts。
