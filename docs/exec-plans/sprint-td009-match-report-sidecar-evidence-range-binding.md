# Sprint：TD009 match-report↔sidecar 证据／区间／media 绑定加深

**状态（2026-10-22）：已推送 origin/main 5d54d0b（docs 记录提交另记）。** 新增 `assert_match_report_sidecar_binding_contract(report, request, result?)`：`refinementRequestHash`／runId／eventFingerprint／candidateId／sourceRange↔sidecar interval 对齐；`eventId` 须挂 `runId:mediaSha256:`；match／bucket `evidenceIds`／`sharedEvidenceIds` ⊆ sidecar evidence 且归属 run；嵌套 `sourceRange` 不得逃出报告区间；可选 result 的 `payloadHash`／`requestHash` 对齐。`assert_match_report_contract` 同步：报告有 `sourceRange` 时 match／bucket 区间不得逃逸（报告 unbound 则跳过）。pytest：demo-phase0 legacy 三份只读绑定；伪造外证／逃逸／media／payload 拒绝；v1.1 夹具仍绿。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写旧 match／sidecar。复合人评／静态索引仍 open。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、TD009 match-report 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 match／sidecar、声称 F006／TD009 全关

## 白话

匹配报告和精分析侧车以前已经对过哈希、候选号、时间窗外壳。这轮再钉死：报告里每一条证据帧 id 必须真的出现在侧车 request 的 evidence 清单里，不能私自塞外证；匹配行／证据桶的时间窗不能比报告／侧车 interval 还宽；事件号中间那段 media 指纹必须跟侧车 `mediaSha256` 一致；有 result 侧车时 payload 哈希也对上。旧 v1 三份报告只读核对通过，不改磁盘、不宣称关单。

## Acceptance

- [x] `assert_match_report_sidecar_binding_contract`：身份／media／证据子集／嵌套区间／payload
- [x] `assert_match_report_contract`：bound sourceRange 下嵌套不逃逸
- [x] legacy demo-phase0 只读绑定绿；伪造拒绝绿；v1.1 夹具绿
- [x] 已推送 `origin/main`（feature `5d54d0b`；docs 记录另提交）

## Verification

```text
pytest tests/test_detail_match_report_local_readonly_td009.py \
  tests/test_detail_match_report_contract.py \
  tests/test_detail_refinement_sidecar_local_readonly_td009.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD009／F010／人评关单或 gaps 已清；不改写 artifacts；RETRIEVAL_VERSION 未动。
