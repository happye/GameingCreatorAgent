# Sprint：TD009 match-report↔sidecar binding gaps 对齐 + baseRun／model 加深

**状态（2026-10-22）：已推送 origin/main bd6b081（docs 记录提交另记）。** 新增 `match_report_sidecar_binding_gaps(report, request, result?)`：稳定 soft gap 码对齐 `assert_match_report_sidecar_binding_contract`（空元组＝可通过绑定断言）。绑定断言加深：`canonical.baseRunId`＝`runId`；`canonical.eventFingerprint`＝报告指纹；`refinementProfile` 若非 null 须非空串；`result.status`／`result.constraintHash`（64-hex）；有 result 侧车时 `actualModel` 非空且＝`requestedModel`。pytest：legacy 三份 gaps==()；伪造外证／逃逸／media／payload／baseRun／model 码对齐。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写旧 match／sidecar。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、TD009 match-report 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 artifacts、声称 F006／TD009 全关

## 白话

上一轮已经用硬断言把匹配报告和精分析侧车钉死。这轮补上软对照：同一套绑定规则能吐出稳定的缺口码（证据不在侧车、时间窗逃逸、media 对不上、payload 漂了、baseRun 漂了、实际模型对不上请求模型），旧三份报告软对照是空列表。顺带把规范载荷里的 baseRun／事件指纹、结果状态／约束哈希、侧车实际模型也挂进硬断言。不改磁盘、不宣称关单。

## Acceptance

- [x] `match_report_sidecar_binding_gaps` 对齐 binding assert
- [x] binding 加深 baseRun／fingerprint／status／constraintHash／actualModel
- [x] legacy gaps 空；伪造码绿；v1.1 夹具仍绿
- [x] 已推送 `origin/main`（feature `bd6b081`；docs 记录另提交）

## Verification

```text
pytest tests/test_detail_match_report_local_readonly_td009.py \
  tests/test_detail_match_report_contract.py \
  tests/test_detail_refinement_sidecar_local_readonly_td009.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD009／F010／人评关单或 gaps 已清；不改写 artifacts。
