# Sprint：TD009 matcher 同居 UNCERTAIN 阻断 OBSERVED FULL

**状态（2026-10-22）：已推送 origin/main `8aac1d2`。** `_part_conditions`：同一 part 上同 kind／value 若同时存在 OBSERVED 与 UNCERTAIN，不得把 OBSERVED 记为 satisfied／FULL；改记 uncertain。`MATCHER_VERSION` → `actor-detail-matcher-v1.1`。验证=**pytest**（`test_actor_detail_matching`／`test_actor_details`）。0 付费；不代选 A／B／D；不标 F006/F009/F010 true；不宣称 TD009／人评关单。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`actor_detail_matching.py`、`actor_details.py`（版本钉）、matcher 测试、本 sprint、交接 docs
- 不做：DeepSeek／launcher、改 feature_list、代选 A／B／D、声称 F010／人评通过

## 白话

细节匹配里，如果同一持有物既被标成「已观察到的武器」，又被标成「不确定是不是武器」，以前「已观察」会直接算满分命中。现在只要旁边还有同值的不确定记录，就不能算满分，只能停在不确定／部分命中；形状这类没被怀疑的条件仍可满分。这是离线合同加固，不是 TD009 验收通过。

## Acceptance

- [x] 同居 UNCERTAIN 阻断同值 OBSERVED → satisfied
- [x] MATCHER_VERSION v1.1
- [x] fixture pytest 绿（含 shape 仍 FULL、combined PARTIAL）
- [x] 已推送 `origin/main`（`8aac1d2`）
