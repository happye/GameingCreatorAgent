# Sprint：检索 cast／skill 别名 + explode 跨语言（真实语料）

**状态（2026-10-22）：已推送 origin/main 5cbfb4f。** 基于 demo-phase0 Completed 真实正文／标签频次（技能≈47、释放≈14、爆炸≈6）：新增动作 `cast`（释放／施放／施法／技能 + cast／skill 英文）；`_TAG_ONLY_NOISE_ACTIONS` 纳入 cast，裸「技能释放／技能特效」无正文证据不算命中；`_CROSS_LINGUAL_TERMS` 补 cast／skill→释放／技能、explode／explosion→爆炸。pytest + demo-phase0 只读。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料；不改写 DB。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` cast／skill／explode 别名与 tag-only、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

本机完成片里大量写着「释放技能」「技能特效」「爆炸」，但英文搜 skill／cast／explode 以前对不上。这轮把释放／技能收成施法类动作，英文会交叉扩到中文；只有标签写了技能、正文没有的片段当界面噪声扔掉。爆炸走跨语言扩展，不新开动作弃权。没改版本号，攻击只靠标签还能召回的约定没动，也没编 Boss／射击假片。

## Acceptance

- [x] cast／skill 动作别名；tag-only 技能* 噪声排除；explode→爆炸
- [x] 非动作词（skillful／forecast 等）不误扩
- [x] demo-phase0 Completed：skill／cast／explode 只读绿
- [ ] 已推送 `origin/main`（SHA 待填）
