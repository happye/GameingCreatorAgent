# Sprint：素材任务行嵌入覆盖缺口拒窗摘要

**状态（2026-10-22）：已交付（待推送）。** `material-tasks-v2` 对 `analysis_coverage_gap` 任务附加只读 `coverageGapSummary`（拒窗 ID／计数；恒未清除、未选 B）；工作台任务卡展示摘要。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评／验收通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`tasks.py`、工作台任务卡 JS、相关 pytest、本 sprint、交接顶栏
- 不做：付费视觉、选 B、标 F006 true、代选 A／B／D、声称验收通过、清除覆盖缺口

## 白话

看素材任务列表时，有覆盖缺口的任务会直接写出拒了哪些窗（若本地有 analysis_coverage.json），不用先开另一个对话框；仍然提醒你自己选 A／B／D，系统不代选、不宣称已修好。

## Acceptance

- [x] `coverageGapSummary` 仅挂在 coverage_gap 任务上且 inert
- [x] 工作台任务卡展示拒窗／未加载提示
- [x] pytest 覆盖有／无 coverage 文件与静态字符串
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [ ] 已推送 `origin/main`（推送后勾）
