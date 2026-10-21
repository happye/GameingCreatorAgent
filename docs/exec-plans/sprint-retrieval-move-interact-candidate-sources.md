# Sprint：move／interact 裸标签噪声 + candidate_sources 合同（检索离线质量）

**状态（2026-10-22）：已推送 origin/main 862dee4。** 将 `_TAG_ONLY_NOISE_ACTIONS` 扩展为 `fight|move|interact`：query 为移动／交互类且 `positive_text` 无对应动作词、仅靠 mechanicTags 时排除。攻击 tag-only 召回仍按 TD010 保留。补强 `candidate_sources` 文档合同：无分／无向量、按时间排序、facts 不含裸标签、与 search hit 身份对齐、coverage-gap 拒投。验证=**pytest（fixture + EqualSimilarity hybrid）+ demo-phase0 只读 DB**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、action-aliases／local-completed 测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／TD 全关、Boss／射击假语料、独立静态衣着索引

## 白话

上一轮已经把「战斗」光靠标签乱飘的镜头摁住了。这轮把同样规矩扩到「移动」和「交互」：正文里没写移动／交互，只贴了标签的，搜 move／interact 时不再进结果。另外把「候选清单」candidate_sources 钉死：不带分数、按时间排、facts 不拿标签冒充、和真正搜出来的 clip id 对得上；覆盖缺口的 run 一样拒绝。

## Acceptance

- [x] `_TAG_ONLY_NOISE_ACTIONS` 含 fight／move／interact；攻击仍不在集合内
- [x] fixture：move／interact tag-only 噪声排除；真实事实保留；攻击 tag-only 回归仍过
- [x] candidate_sources 单元＋demo-phase0：无分、时间序、身份对齐、facts 无裸标签
- [x] demo-phase0 move／移动 hits 的 positive_text 均含移动用语
- [ ] 已推送 `origin/main`（SHA 待填）
