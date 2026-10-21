# Sprint：TD009 sidecar 只读匹配／指纹拒收合同

**状态（2026-10-22）：已推送 origin/main `af939bd`。** `match_refinement`：coverage-gap → `refinement.coverage_gap`；报告 `matcherVersion` 必须等于当前 profile 合同（v1.2／temporal v2）。只读匹配不写盘；保存文件名带 matcher 版本；篡改 match JSON → `refinement.immutable`；事件指纹漂移使旧 sidecar 孤儿化不复用；篡改 request.json 指纹 → `refinement.source_mismatch`。验证=**pytest**。0 付费；不代选 A／B／D；不标 F006/F009/F010 true；不宣称 TD009／人评关单。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query_sidecar.py`、sidecar 合同测试、本 sprint、交接 docs
- 不做：DeepSeek／launcher、改 feature_list、代选 A／B／D、声称 F010 通过

## 白话

细节匹配侧车这一轮把几道门钉死：有覆盖缺口的分析不能拿来做匹配；报告上的 matcher 版本必须对得上；只读匹配不写文件；保存的匹配记录按版本分文件，改坏了不能装新的；源事件事实改了，旧侧车自动失效不会偷用旧结果。这是离线合同，不是人评通过。

## Acceptance

- [x] coverage-gap 拒收
- [x] matcherVersion 自检
- [x] 只读无写／版本化文件名／immutable／指纹漂移与篡改 pytest 绿
- [x] 已推送 `origin/main`（`af939bd`）
