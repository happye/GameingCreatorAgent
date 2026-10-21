# Sprint：acceptance-readiness 嵌入 inertContract 机读护栏

**状态（2026-10-22）：已交付（待推送）。** 在只读就绪报告中嵌入 inertContract（cceptance-readiness-inert-v1），列出禁止状态／标签、必为 false 的标志与跨面 JS 护栏；ssert_acceptance_readiness_inert 校验该块与源常量一致。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评／验收通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：main
- Owned：cceptance_readiness.py、相关 pytest、本 sprint、交接顶栏
- 不做：付费视觉、标 F006 true、代选 A／B／D、声称验收通过、清除覆盖缺口

## 白话

把「什么叫不能写成已通过」写进就绪 JSON 本身，CLI／API／以后的页面都能读到同一份规则，而不是只靠散落的硬编码。

## Acceptance

- [x] uild_inert_contract + 报告内 inertContract 字段
- [x] inert 断言校验合同与常量一致
- [x] pytest 覆盖嵌入与篡改拒绝
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 已推送 origin/main（推送后勾）
