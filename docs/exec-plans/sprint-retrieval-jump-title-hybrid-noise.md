# Sprint：JUMP 标题品牌噪声在 hybrid／semantic 通道排除（TD004）

**状态（2026-10-22）：代码已落地，待推送。** 在 lexical 中性化之外，增加 `_title_brand_action_noise_documents`：当 query 动作仅因冻结标题品牌出现在 `positive_text`、中性化后消失时，将该文档并入检索排除集，防止 adversarial／E5 semantic 通道把标题卡重新抬进 jump 结果。验证=**pytest（含 EqualSimilarity hybrid）+ demo-phase0 只读 DB**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／人评关单。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、action-aliases／local-completed 测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／TD004 全关

## 白话

上一轮 lexical 已经把 JUMP 标题卡打掉了，但如果走 hybrid／语义，向量仍可能因为正文里有 JUMP 把片头抬回来。这一轮加了一道排除：只要「跳跃」这个词只来自冻结标题品牌、抠掉标题后正文里没了，就不许进结果。真跳跃镜头不受影响。

## Acceptance

- [x] `_title_brand_action_noise_documents` 并入 denied／排除集
- [x] hybrid + EqualSimilarity fixture：仅真实跳跃命中
- [x] demo-phase0 hybrid 只读：标题事件与 jump hits 不相交
- [ ] 已推送 `origin/main`（推送后勾）
