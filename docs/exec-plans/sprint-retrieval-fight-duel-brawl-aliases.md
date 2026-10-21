# Sprint：检索 fight 别名扩至打架／对战／团战（离线）

**状态（2026-10-22）：已推送 origin/main 1e87a86。** `_ACTION_TERMS["fight"]` 增补中文别名 `打架`／`对战`／`团战`：词法查询经既有 `_lexical_query` 交叉扩展；tag-only 噪声排除与 `no_positive_action_evidence` 弃权同步认这批词。pytest 覆盖别名正例／裸标签噪声／demo-phase0 Completed 只读。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。攻击 tag-only 召回仍按 TD010 保留。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 动作别名、别名／本机只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

本机 demo-phase0 完成片里，很多片段只打了「对战」「团战」这类标签，正文未必写「战斗」。用户搜「打架／对战／团战」时，以前几乎对不上。这轮把这几个词收进战斗别名：正文里真有对战描写的能搜到；只靠标签刷屏的仍当噪声扔掉。没改检索版本号，也没动攻击只靠标签还能召回的旧约定。

## Acceptance

- [x] fight 别名含 打架／对战／团战
- [x] 别名正例＋tag-only 噪声＋弃权 pytest 绿
- [x] demo-phase0 Completed 只读对照绿；攻击 tag-only 仍可达
- [ ] 已推送 `origin/main`（SHA 待填）