# Sprint：动作空召回／空查询 abstention 说明（检索离线质量）

**状态（2026-10-22）：已推送 origin/main b85b5ef。** 空／空白 query → `abstention_reason=empty_query`；无检索文档 → `no_searchable_documents`；含已知动作且过滤后零命中（标题品牌噪声／裸标签排除／语料无正向证据）→ `no_positive_action_evidence`。否定意图空结果不冒充该原因。不改分数与既有噪声排除。验证=**pytest + demo-phase0 只读**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、action-aliases／local-completed 测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／TD 全关、Boss／射击假语料

## 白话

以前搜「jump／跳跃」如果片库里只有 JUMP 游戏标题卡、没有真跳跃镜头，结果是空的，但也不告诉你为啥空。这轮空查询会标明 `empty_query`；动作词搜完被标题噪声／裸标签规则滤光以后，会标明 `no_positive_action_evidence`——不是搜索坏了，是没有可用的正向动作证据。带「没有／without」这种否定口吻的空结果不套这句，免得说错。

## Acceptance

- [x] empty_query／no_searchable_documents／no_positive_action_evidence
- [x] 否定意图空结果不设 no_positive_action_evidence
- [x] 有真实动作命中时 abstention_reason is None
- [x] demo-phase0 jump／跳跃 标题-only → no_positive_action_evidence；移动／攻击不误伤
- [ ] 已推送 `origin/main`（SHA 待填）
