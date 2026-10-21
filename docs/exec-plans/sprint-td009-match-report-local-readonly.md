# Sprint：TD009 本机 match-report-v1 只读对照

**状态（2026-10-22）：已推送 origin/main 4aa5571。** 新增 `match_report_contract_gaps`：对磁盘上的旧 `actor-detail-match-report-v1`／`actor-detail-matcher-v1` 报告给出稳定缺口码（schema／缺 constraintHash／inertContract／independentStaticClothingIndex／matcher 版本等）；`assert_match_report_contract` 仍拒绝。pytest 只读打开 `artifacts/demo-phase0/**/matches/*-actor-detail-matcher-*.json`；现行 v1.1 fixture 缺口为空。验证=**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006/F009/F010 true；**不宣称 TD009／人评关单**。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、本机只读对照测试、本 sprint、交接 docs
- 不做：DeepSeek／launcher、改 feature_list、代选 A／B／D、声称 F010／人评通过、独立静态衣着索引、改写旧 match JSON

## 白话

本机 demo-phase0 里还躺着几份旧的匹配报告（报告合同 v1、matcher v1）。现行合同已经升到 match-report v1.1＋matcher v1.2，缺约束哈希、惰性合同、禁静态索引字段。这轮加了只读对照：打开这些旧文件，明确列出缺口，并确认现行校验会打回；同时确认它们没有伪造「人评通过」。这是对照，不是关单。

## Acceptance

- [x] `match_report_contract_gaps` 稳定缺口码
- [x] demo-phase0 旧 v1 报告：assert 拒绝＋缺口含 schema／缺字段／matcher
- [x] 现行 v1.1 fixture 缺口为空；伪造 humanLabels／qualityGate 可检出
- [ ] 已推送 `origin/main`（SHA 待填）
