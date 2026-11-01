# Sprint：项目联合检索 startedAt／sourceValidationMs／信封加深

**状态（2026-10-22）：已推送 origin/main b07867f（docs 记录提交另记）。** 加深 `assert_project_search_document_contract`：`startedAt` 须为带时区 ISO-8601（`Z` 可）；`sourceValidationMs`／`elapsedMs` 为 `int≥0`；`factsProjectionVersion` 非空；`qualityGate` 必须为 null；`recordPath` 非空且包含 `searchId`。pytest + demo-phase0 project-searches 只读（32）。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；不改写 artifacts；`RETRIEVAL_VERSION` 仍 `bm25-e5-rrf-v7`；攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、project 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 JSON、声称 F006／TD 全关

## 白话

项目联合检索落盘结果上的 **startedAt** 必须带时区，**sourceValidationMs**／**elapsedMs** 不能是负数，facts 投影版本号要有，不能假装过了 qualityGate，recordPath 里还得能看到本次 searchId。本机 32 份只读全过。

## Acceptance

- [x] startedAt 时区；sourceValidationMs／elapsedMs≥0
- [x] factsProjectionVersion／qualityGate null／recordPath⊇searchId
- [x] demo-phase0 只读绿；伪造拒绝绿
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_project_search_local_readonly.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不改写 artifacts。
