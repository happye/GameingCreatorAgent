# Sprint：战斗／combat 裸 mechanicTag 噪声排除（检索离线质量）

**状态（2026-10-22）：已推送 origin/main 0896740。** 增加 _tag_only_action_noise_documents：当 query 动作为 fight／combat／战斗／打斗，且文档 positive_text 不含该动作词、仅靠 mechanicTags（如裸「战斗」）撑起 BM25 时，并入检索排除集。攻击（攻击／attack）的 tag-only 召回按 TD010 保留。验证=**pytest（fixture + EqualSimilarity hybrid）+ demo-phase0 只读 DB**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。RETRIEVAL_VERSION 仍为 m25-e5-rrf-v7（避免无谓产物 churn）。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：main
- Owned：
etrieval.py、action-aliases／local-completed 测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／TD 全关、独立静态衣着索引、Boss／射击假语料

## 白话

搜「战斗／fight／combat」时，以前会把一堆只贴了「战斗」标签、正文其实只是伤害数字／特效飘字的镜头顶上来，把真的「战斗界面／交战」压下去。这一轮规定：问战斗类问题时，正文里必须真有战斗字样；光靠标签不算。问「攻击」时仍允许只用标签召回（TD010 已钉死），互不影响。

## Acceptance

- [x] _TAG_ONLY_NOISE_ACTIONS={"fight"} + _tag_only_action_noise_documents 并入 denied／排除集
- [x] fixture：tag-only 战斗噪声不进结果；真实战斗事实保留；攻击 tag-only 仍可达
- [x] demo-phase0 lexical 只读：fight／combat／战斗／打斗 hits 的 positive_text 均含战斗用语；攻击 tag-only 回归仍过
- [x] 已推送 origin/main（0896740）
