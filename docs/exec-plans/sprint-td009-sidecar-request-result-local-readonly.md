# Sprint：TD009 sidecar request／result 本机只读对照

**状态（2026-10-22）：待推送 origin/main。** 新增 `assert_refinement_request_document_contract`／`assert_refinement_result_document_contract`／`assert_refinement_sidecar_pair_contract`／`refinement_sidecar_contract_gaps`：钉死 requestHash＝SHA256(canonicalJson)、指纹／runId 对齐、result schema／payloadHash、禁止 humanLabels／qualityGate／formalAcceptance 等验收声称。`freeze_request` 落盘前、`_publish` 落盘前、`reuse_or_refuse`／`_published` 读回时强制。pytest 只读扫 `artifacts/demo-phase0/**/detail-refinements/*/request.json`（及成对 result）。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006/F009/F010 true；不宣称 TD009／人评关单；不改写旧 sidecar JSON。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_refinement_budget.py`、`detail_refinement_sidecar.py`、本机只读测试、本 sprint、交接 docs
- 不做：DeepSeek／launcher、改 feature_list、代选 A／B／D、改写旧 request／result、声称 F010／TD009 全关

## 白话

demo-phase0 里已经存了若干细节精分析侧车：每个目录一份 `request.json`，有的还有 `result.json`。这轮给它们加上只读对照——请求哈希必须对得上规范 JSON，结果载荷哈希不能假，请求和结果要挂同一条指纹／任务，谁也不能在侧车里冒充人评通过。落盘和读盘出口都卡同一道门。这是离线合同，不是人评关单。

## Acceptance

- [x] request／result／pair 合同 + gaps
- [x] freeze／publish／reuse／_published 强制
- [x] demo-phase0 全部 sidecar 只读绿；哈希漂移／验收声称／错配 pair 拒绝
- [ ] 已推送 `origin/main`（SHA 待填）