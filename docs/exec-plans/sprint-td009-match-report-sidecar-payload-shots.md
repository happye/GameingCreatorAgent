# Sprint：TD009 match-report↔sidecar payloadJson 身份／shots 覆盖加深

**状态（2026-10-22）：已推送 origin/main 24f59ec（docs 记录提交另记）。** 加深 `assert_match_report_sidecar_binding_contract`：解析 result `payloadJson`；`runId`／`eventId`／`candidateId`／`eventFingerprint`／`sourceRange` 对齐报告；`mediaSha256`／`configurationHash`／`pipelineVersion`／`basePromptHash`／`basePromptVersion` 对齐 request／canonical；`schemaVersion`／`vocabularyVersion`／`mediaId` 非空；`shots` 非空且 shotId 唯一，shot 区间不逃逸；报告 match `shotId` ⊆ payload shots。gaps 映射同步。pytest + demo-phase0 legacy 只读。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写旧 artifacts。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、TD009 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 artifacts、声称 F006／TD009 全关

## 白话

匹配报告挂侧车时，结果里的 **payloadJson** 主体也要对得上：任务号、事件号、候选号、时间窗、media／配置／管线／prompt 都得和报告／请求一致；里面的镜头列表不能空，报告里用到的 shotId 必须能在 payload 镜头里找到。旧三份只读仍过。不改磁盘、不宣称关单。

## Acceptance

- [x] payloadJson 身份／配置／prompt 对齐
- [x] shots 非空唯一；match shotId ⊆ payload
- [x] legacy 绿；伪造拒绝绿
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_detail_match_report_local_readonly_td009.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD009／F010／人评关单；不改写 artifacts。
