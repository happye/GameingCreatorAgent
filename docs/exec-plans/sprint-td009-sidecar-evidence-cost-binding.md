# Sprint：TD009 sidecar evidence 行／cost／pair 证据绑定加深

**状态（2026-10-22）：已推送 origin/main 06cddd8（docs 记录提交另记）。** 加深 `assert_refinement_request_document_contract`：每条 evidence 须有非空唯一 `evidenceId`（带冒号时归属 `runId:mediaSha256:`）、64-hex `sha256`、`durationUs` 与 interval 一致、`sourceUs`∈`[startUs,endUs)`。加深 `assert_refinement_result_document_contract`：`costCny` 须为十进制数字字符串；`actualModel` 非空空白。加深 `assert_refinement_sidecar_pair_contract`：结果 `detail.evidence` 的 id 序列须与请求 evidence 完全一致。pytest 只读扫 demo-phase0 detail-refinements。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写 sidecar。复合人评／静态索引仍 open。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_refinement_budget.py`、TD009 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 sidecar、声称 F006／TD009 全关

## 白话

精分析侧车以前已经核对请求哈希、时间窗、提示词指纹。这轮再钉证据帧：每张图的 evidenceId 必须挂对任务和媒体指纹、时间点不能跑出区间、结果里的证据列表要和请求一字不差对上；费用字段只能是纯数字字符串，模型名不能是空白。旧 JSON 没改，只是读的时候卡更紧。

## Acceptance

- [x] request evidence 行：归属／sha／sourceUs／duration／去重
- [x] result costCny 十进制；actualModel 非空白
- [x] pair evidence id 序列一致
- [x] demo-phase0 detail-refinements 只读绿
- [x] 已推送 `origin/main`（feature `06cddd8`；docs 记录另提交）

## Verification

```text
pytest tests/test_detail_refinement_sidecar_local_readonly_td009.py \
  tests/test_detail_match_report_local_readonly_td009.py \
  tests/test_detail_match_report_contract.py tests/test_detail_refinement.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD007／TD009／TD010 关单或三缺口清除；不发明 Boss／射击语料；不改写 artifacts。
