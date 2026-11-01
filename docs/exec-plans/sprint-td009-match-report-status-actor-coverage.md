# Sprint：TD009 match-report 状态不变量／sidecar actor 覆盖加深

**状态（2026-11-01）：已完成（TD009 仍 open）。**

## 选定

继续 **TD009** 离线合同：匹配报告 JSON 尚未钉死与 `DetailMatch` 一致的 status↔matches 规则；sidecar `payloadJson` 已核对 shotId，但未要求 match 的 `(shotId, actorId)` 落在 payload actors 上。本切片加深 assert／gaps + demo-phase0 legacy 只读，**不关单**。

## 非目标

- 不关 TD009／F010／F006／F009；不付费重发／视觉；不改写 artifacts；不发明人评通过

## 设计

1. `assert_match_report_contract`：`(shotId, actorId)` 唯一；`full`／`partial`／`no_match` 分别要求完整共享支持／至少一条 satisfied／每行 counterEvidence
2. `match_report_contract_gaps`：对应软缺口码
3. `assert_match_report_sidecar_binding_contract`：payload shot.actors 结构；actor.shotId 与父 shot 一致；match 的 shot/actor 对必须被 payload 覆盖
4. binding gaps 新码；legacy 三份只读仍零缺口

## 验收

- [x] sprint
- [x] 实现与测试
- [x] 文档；债务仍 open

## 结果

- 伪造 full／partial／no_match／重复 shot-actor 被拒
- 伪造未知 actor 或 actor.shotId 漂移被拒；demo-phase0 legacy 绑定仍过
- **不宣称** TD009／F010 关单
