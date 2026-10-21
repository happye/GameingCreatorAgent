# Sprint：TD009 匹配报告字段／惰性合同／禁静态衣着索引（v1.1）

**状态（2026-10-22）：代码已落地，待推送。** `MATCH_REPORT_VERSION` → `actor-detail-match-report-v1.1`：强制 `humanLabels`／`qualityGate` 恒 null、`independentStaticClothingIndex=false`、嵌入 `inertContract`、新增 `constraintHash`；`assert_match_report_contract` 在 `match_report`／`match_refinement` 出口校验。验证=**pytest**。0 付费；不代选 A／B／D；不标 F006/F009/F010 true；不宣称 TD009／人评关单。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、`detail_query_sidecar.py`、匹配报告合同测试、本 sprint、交接 docs
- 不做：DeepSeek／launcher、改 feature_list、代选 A／B／D、声称 F010／人评通过、实现独立静态衣着索引

## 白话

匹配报告以前也能看出没打人评勾，但字段合同不够硬。这一轮把报告升级到 v1.1：人标和质量闸必须是空，不能冒充通过；明确「没有独立静态衣着索引」；带上约束哈希和惰性合同；谁把 qualityGate 改成 true 或打开静态索引，校验直接打回。这是离线报告合同，不是人评完成。

## Acceptance

- [x] match-report v1.1 字段与 inertContract
- [x] constraintHash 与 constraintJson 一致
- [x] independentStaticClothingIndex 恒 false
- [x] 篡改人标／闸／静态索引／哈希 → ValueError
- [ ] 已推送 `origin/main`（推送后勾）
