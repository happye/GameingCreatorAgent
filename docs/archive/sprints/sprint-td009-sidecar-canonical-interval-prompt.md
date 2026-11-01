# Sprint：TD009 sidecar 规范载荷／pair 时间与 prompt 加深

**状态（2026-10-22）：已推送 origin/main 3889b45。** 加深 `assert_refinement_request_document_contract`：canonical 须含有效 `candidateId`／`mediaSha256`／`configurationHash`、合法 `interval`（start＜end≤duration）、非空 `evidence`；规范载荷同样禁止验收声称字段。加深 `assert_refinement_sidecar_pair_contract`：结果 `source_range` 对齐请求 interval；`basePromptHash`／`basePromptVersion` 与请求一致；带冒号的 `eventId` 须挂 `{runId}:{mediaId}:`。pytest 只读扫 demo-phase0 detail-refinements（6 request／3 result）+ 既有 sidecar 单测。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006/F009/F010 true；**不宣称 TD009／人评关单**；不改写旧 sidecar。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_refinement_budget.py` 合同加深、只读测试、本 sprint、交接 docs
- 不做：DeepSeek／launcher、改 feature_list、代选 A／B／D、改写旧 request／result、声称 F010／TD009 全关

## 白话

精分析侧车以前主要核哈希和指纹。这轮把请求规范 JSON 再钉死：候选／媒体哈希／配置哈希要在、时间片要合理、证据列表不能空，载荷里也不能偷塞「人评通过」。有结果的成对文件还要核对：结果时间范围跟请求 interval 一致，提示词版本／哈希跟请求一致。旧文件没改，只是读的时候卡更紧。这不是人评关单。

## Acceptance

- [x] request canonical 身份／interval／evidence／禁声称
- [x] pair：interval↔source_range、basePrompt 对齐、event 媒体归属
- [x] demo-phase0 sidecar 只读绿；漂移拒绝
- [ ] 已推送 `origin/main`（SHA 待填）
