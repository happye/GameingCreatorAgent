# Sprint：TD004 离线噪声加深（title-brand／tag-only／negative weak-overlap）

**状态（2026-11-01）：已完成（TD004 仍 open，不关单）。**

## 为何选这项（option C）

在 TD004／TD009／TD002 三者中选 **TD004**：

- 进度看板与 tech-debt 标为 **F006 前高优先**（负例误召回）。
- 本地即可加深：标题品牌中性化、裸 mechanicTag 噪声、否定查询弱重叠，**不需**下载／付费视觉／人评。
- TD009 近期已多轮 sidecar／match-report 合同加深；TD002 Matroska 路径与非容器拒收测试已较完整，收益边际更低。

**不宣称** TD004／TD010／F006 关单；不代选 A／B／D；不造伪 demo-phase0 语料。

## 目标

1. 扩展冻结 JUMP 系标题品牌（FORCE／周刊等），继续走 title-brand 排除。
2. 将 **jump／shoot** 纳入 `_TAG_ONLY_NOISE_ACTIONS`（attack 仍保留 TD010）。
3. 否定意图查询：若与候选的词项重叠**仅**落在弱重叠集合（如「存在」来自「不存在」），则排除该候选。

## 非目标

- 不校准阈值、不加人评、不声称 Boss／射击 hybrid 已过 U10
- 不改 F006／F009／F010 passes
- 不下载、不大媒体

## 验收

- [x] sprint 选定理由落盘
- [x] 实现 + 合成夹具合同测试
- [x] tech-debt／HANDOFF／progress／assignments／progress-board 更新；TD004 仍 open


## 结果

- `_TITLE_BRAND_ACTION_NOISE` 扩 JUMP FORCE／PARADE／Weekly／周刊少年JUMP
- `_TAG_ONLY_NOISE_ACTIONS` 增 jump／shoot（attack 仍 TD010 保留）
- `_negative_query_weak_overlap_documents`：仅处理「不存在」类查询与「存在」假友元重叠
- 测试：`test_retrieval_action_aliases.py` 全量通过；不宣称 TD004／F006 关单
