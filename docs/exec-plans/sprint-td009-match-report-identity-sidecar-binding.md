# Sprint：TD009 match-report 身份／sidecar 绑定／gaps 加深

**状态（2026-10-22）：待推送 origin/main。** 加深 `assert_match_report_contract`／`match_report_contract_gaps`：`runId`／`eventId` 归属、可选 `eventFingerprint`／refinement 哈希（null 或 sha256）、可选合法 `sourceRange`、`result.status`∈MatchStatus、`result.matcherVersion` 现行版本、`result.constraintHash`＝顶栏 constraintHash、禁止 formalAcceptance／F006 等声称。新增本机只读对照：demo-phase0 旧 v1 match 报告的 `refinementRequestHash`／`payloadHash` 必须对上真实 detail-refinements 侧车（run／指纹／candidate／interval）。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／人评关单**；不改写旧 match JSON。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py` 合同加深、只读测试、本 sprint、交接 docs
- 不做：DeepSeek／launcher、改 feature_list、代选 A／B／D、改写旧 match／sidecar、声称 F010／TD009 全关

## 白话

匹配报告以前主要卡「不能写人评通过」和 inert 字段。这轮再钉：事件号要挂对任务、时间片要合理、结果状态／matcher 版本要合法，结果里的约束哈希要和报告顶栏一致。顺手对照本机那几份旧 v1 报告——它们引用的精分析 request／result 侧车还在，哈希、指纹、候选、时间片对得上。旧文件没改。这是对照加严，不是关单。

## Acceptance

- [x] assert／gaps：身份／range／status／matcher／constraint／禁声称
- [x] demo-phase0 旧 match↔sidecar 绑定只读绿
- [x] 现行 v1.1 fixture 仍零缺口；漂移拒绝
- [ ] 已推送 `origin/main`（SHA 待填）
