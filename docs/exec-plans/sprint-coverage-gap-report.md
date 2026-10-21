# Sprint：离线 coverage-gap-report 产品能力

**状态（2026-10-22）：已交付（待推送）。** 新增只读 coverage-gap-report（application + CLI）：从任务快照列出覆盖缺口 run，若有 nalysis_coverage.json 则汇总拒窗 ID／计数；恒 coverageGapsCleared=false、optionChosen=null；附草稿提示且声明草稿≠选 B。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评／验收通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：main
- Owned：coverage_gap_report.py、CLI、pytest、本 sprint、交接顶栏／human-inputs 提示
- 不做：付费视觉、选 B 发送、标 F006 true、代选 A／B／D、声称验收通过、清除覆盖缺口

## 白话

用户不用再翻一堆 JSON 才知道三缺口在哪：一条本机命令就能列出缺口 run 和拒窗，并提醒下一步仍要你自己选 A／B／D；命令本身绝不代选、不花钱、不宣称已修好。

## Acceptance

- [x] uild_coverage_gap_report + inert 断言
- [x] CLI coverage-gap-report（--project／可选 --coverage／--output）
- [x] pytest：任务行、覆盖清单、coverage-only、篡改拒绝、CLI 只读
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 已推送 origin/main（推送后勾）
