# Sprint：单任务／项目检索 factsProjectionVersion 白名单加深

**状态（2026-10-22）：已推送 origin/main FEATURE_SHA（docs 记录提交另记）。** 新增 `FACTS_PROJECTION_VERSIONS={legacy-frame-alias-neutral-v1}`。`assert_run_search_document_contract`：若带 `factsProjectionVersion` 则必须∈白名单；`qualityGate` 必须为 null。`assert_project_search_document_contract`：`factsProjectionVersion` 必有且∈同一白名单。pytest + demo-phase0 runs/*/searches（83 有／121 无）与 project-searches 只读。验证＝**pytest + 只读 JSON**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；不改写 artifacts；`RETRIEVAL_VERSION` 仍 `bm25-e5-rrf-v7`；攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、run／project 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 JSON、声称 F006／TD 全关

## 白话

单任务搜索 JSON 里有的带 **factsProjectionVersion**，有的没有。这轮规定：一旦写了，只能是本机已见过的 `legacy-frame-alias-neutral-v1`，乱写版本号不行；也不能假装过了 qualityGate。项目联合检索则必须带且同白名单。

## Acceptance

- [x] FACTS_PROJECTION_VERSIONS 常量
- [x] run：可选但须∈白名单；qualityGate null
- [x] project：必有且∈白名单
- [x] 只读绿；伪造拒绝绿
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_run_search_local_readonly.py tests/test_project_search_local_readonly.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不改写 artifacts。
