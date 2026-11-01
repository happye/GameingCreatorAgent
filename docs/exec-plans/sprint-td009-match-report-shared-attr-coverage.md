# Sprint：TD009 match-report sharedEvidence／payload attribute 覆盖加深

**状态（2026-11-01）：已完成（TD009 仍 open）。**

## 选定

继续 **TD009** 离线合同：`DetailMatch` 要求 `sharedEvidenceIds` 必须落在每条 satisfied 的 `evidenceIds` 内且带 sourceRange；match-report／sidecar 绑定此前未钉。另：satisfied 的 `(partId, kind, value)` 应能在 sidecar payload 同镜头演员的 attributes 上找到。本切片加深 assert／gaps + demo-phase0 legacy 只读，**不关单**。

## 非目标

- 不关 TD009／F010／F006／F009；不付费重发／视觉；不改写 artifacts；不发明人评通过

## 设计

1. `assert_match_report_contract`：shared→satisfied 子集；shared 非空则须有 satisfied + sourceRange
2. `match_report_contract_gaps`：对应软缺口码
3. binding：payload attribute 字段形态（partId／kind／value／status／evidenceIds／range）；satisfied 三元组必须被 attributes 覆盖
4. legacy 三份只读仍零缺口

## 验收

- [x] sprint
- [x] 实现与测试
- [x] 文档；债务仍 open

## 结果

- 伪造 shared 越界／无 satisfied、清空 attributes、空 kind 被拒
- demo-phase0 legacy 绑定仍过
- **不宣称** TD009／F010 关单
