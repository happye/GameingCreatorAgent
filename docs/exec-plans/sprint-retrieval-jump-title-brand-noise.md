# Sprint：检索忽略 JUMP 标题品牌噪声（TD004 离线）

**状态（2026-10-22）：代码已落地，待推送。** 对冻结的游戏标题品牌短语（`JUMP ASSEMBLE`／`JUMP明星大乱斗`／`少年JUMP正版授权`）在 lexical 打分与否定扫描前中性化，避免标题卡被当成跳跃玩法证据。验证=**pytest + 本机 demo-phase0 只读 DB**。0 付费；不代选 A／B／D；不标 F006 true；不宣称人评／验收通过；不声称 TD004／TD007／TD009 关单。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、action-aliases／local-completed 测试、本 sprint、tech-debt／交接顶栏
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／人评通过、大范围改 RETRIEVAL_VERSION 文物

## 白话

搜「jump」时，片头「JUMP明星大乱斗／JUMP ASSEMBLE」以前会被当成跳跃命中。现在只把这几条冻结标题品牌从检索／否定扫描正文里换成中性占位，真正的「角色跳跃」仍可命中。这是离线检索质量护栏，不是 TD004 全量验收。

## Acceptance

- [x] `_neutralize_title_brands` 用于 lexical 与 denial 扫描
- [x] fixture：标题卡不进 jump／JUMP hits，真实跳跃仍进
- [x] demo-phase0 Completed 只读：标题事件与 jump hits 不相交
- [ ] 已推送 `origin/main`（推送后勾）
