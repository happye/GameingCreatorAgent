# Sprint：TD009 match-report↔sidecar actorId 唯一／usage.cost 对齐

**状态（2026-10-22）：已推送 origin/main b710ec1（docs 记录提交另记）。** 加深 `assert_match_report_sidecar_binding_contract`：每行 `actorId`／`shotId` 非空；`actorId` 在报告内唯一；有 result 时 `metadata.usage` 为对象，`usage.cost_cny`＝`costCny`（合法十进制），`original_cost` 若有则合法且与 `cost_cny` 一致；`currency`／`cost_status` 若有则非空串；token 字段若有则 `int≥0`。gaps 映射同步。pytest + demo-phase0 legacy 只读。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写旧 artifacts。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、TD009 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 artifacts、声称 F006／TD009 全关

## 白话

匹配报告里每个演员号不能空、也不能在同一份报告里重复；镜头号也要有。侧车结果的 usage 账单里的 cost_cny 必须和顶层 costCny 对得上，token 数不能是负数。旧三份只读仍过。不改磁盘、不宣称关单。

## Acceptance

- [x] actorId 唯一／非空；shotId 非空
- [x] usage.cost_cny 对齐 costCny；token／currency／status 护栏
- [x] legacy 绿；伪造拒绝绿
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_detail_match_report_local_readonly_td009.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD009／F010／人评关单；不改写 artifacts。
