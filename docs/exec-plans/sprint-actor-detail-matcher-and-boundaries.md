# Sprint：TD009 matcher 正向 AND 边界加固（v1.2）

**状态（2026-10-22）：代码已落地，待推送。** `_full` 明确要求：全部条件 satisfied、无 uncertain／missing／opposed、非空 shared evidence、无冲突、同一 `part_group` 只落在一个 `part_id`。`MATCHER_VERSION` → `actor-detail-matcher-v1.2`。回归：持有物 shape／class 分落不同 part 不得 FULL；AND 条件证据帧不相交不得 FULL；`match_report` 露出 v1.2 与同居 demotion。验证=**pytest**。0 付费；不代选 A／B／D；不标 F006/F009/F010 true；不宣称 TD009／人评关单。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`actor_detail_matching.py`、`actor_details.py`、matcher 测试、本 sprint、交接 docs
- 不做：DeepSeek／launcher、改 feature_list、代选 A／B／D、声称 F010 通过

## 白话

复合条件要「同一零件 + 同一帧」一起站住才能算满分。这一轮把满分门槛写死：不能一边还残留不确定／缺失，也不能把「扁平物」和「武器」安在两个不同零件上凑满分，更不能头发在第 0 帧、外套在第 2 帧这种对不上的证据硬拼。报告里也能看到 matcher v1.2。这是离线 AND 合同，不是人评通过。

## Acceptance

- [x] `_full` AND 门槛（含 part_group 单 part）
- [x] MATCHER_VERSION v1.2
- [x] 分 part held AND／不相交帧 AND／match_report 回归绿
- [ ] 已推送 `origin/main`（推送后勾）
