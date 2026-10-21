# Sprint：TD009 match-report↔sidecar settings／cost／metadata 时间加深

**状态（2026-10-22）：已推送 origin/main FEATURE_SHA（docs 记录提交另记）。** 加深 `assert_match_report_sidecar_binding_contract`：request／canonical schemaVersion；promptHash／basePromptHash／basePromptVersion；canonical `settings`（version／imageDetail／五项正整数）；result `notes` 全字符串；match `conflicts`／`missing` 若存在须为列表；result schemaVersion／costCny；metadata attempt≥1、elapsed_ms≥0、schema_version＝canonical。`match_report_sidecar_binding_gaps` 映射同步。pytest + demo-phase0 legacy 只读。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD009／F010 关单**；不改写旧 artifacts。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`detail_query.py`、TD009 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写旧 artifacts、声称 F006／TD009 全关

## 白话

匹配报告挂侧车时，除了证据和模型，还要把规范载荷里的 **settings**（图宽、张数、超时等）、prompt 哈希／版本、结果 **costCny**、metadata 的 attempt／耗时／schema 也对齐。旧三份只读仍过；伪造会拒并吐软缺口码。不改磁盘、不宣称关单。

## Acceptance

- [x] settings／schema／prompt／cost／metadata 时间字段
- [x] notes／conflicts／missing 形态；gaps 新码
- [x] legacy 绿；伪造拒绝绿
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_detail_match_report_local_readonly_td009.py \
  tests/test_detail_refinement_sidecar_local_readonly_td009.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD009／F010／人评关单；不改写 artifacts。
