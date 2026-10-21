# Sprint：检索动作证据通道 lexicalEvidence（离线质量）

**状态（2026-10-22）：已推送 origin/main 17bd9a2。** 新增 `_action_lexical_evidence` 与 `CandidateClip.lexical_evidence`：对含已知动作的 query，标注命中证据来自 `positive_text`／`mechanic_tags`／`mixed`，并写入 `why` 的 `lexicalEvidence=`。不改分数；攻击 tag-only 仍可达（TD010）并标为 `mechanic_tags`；fight／move／interact 裸标签仍先排除，命中不得为纯 `mechanic_tags`。CLI／inspection／diagnostics／service 重建投影同步字段。验证=**pytest + demo-phase0 只读**。0 付费；不代选 A／B／D；不标 F006 true；不宣称 TD004／TD010／人评关单。`RETRIEVAL_VERSION` 仍为 `bm25-e5-rrf-v7`。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、CLI／inspection／diagnostics／service 投影、测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／TD 全关、Boss／射击假语料

## 白话

搜「攻击」时，有的镜头正文根本没写攻击，只是贴了攻击标签——以前照样能搜到（这是故意留的），但看结果分不清靠的是正文还是标签。这轮给每条命中打上证据通道：正文／标签／两者都有。分数不变，只是把来源写清楚；战斗／移动／交互该排除的裸标签仍然排除。

## Acceptance

- [x] `_action_lexical_evidence` + `CandidateClip.lexical_evidence` + why 信号
- [x] 攻击 tag-only => mechanic_tags；fight 事实命中 => positive_text／mixed
- [x] 非动作 query => lexical_evidence is None
- [x] demo-phase0 只读通道对照；攻击召回不破
- [x] CLI／inspection／diagnostics／service 投影
- [ ] 已推送 `origin/main`（SHA 待填）
