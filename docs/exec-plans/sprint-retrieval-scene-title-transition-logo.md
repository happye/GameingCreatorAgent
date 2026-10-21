# Sprint：检索场景跨语言 标题／转场／标志

**状态（2026-10-22）：已推送 origin/main FEATURE_SHA（docs 记录提交另记）。** `_CROSS_LINGUAL_TERMS` 增补：`title(s)`→标题、`transition(s)`→转场、`logo(s)`→标志。语料依据 demo-phase0 真实 tags／facts（标题文字／标题画面／title screen、transition、标志展示／NARUTO标志）。**不加** titled／subtitle／entitle／titlebrand／transitional／transit／logon／logic／catalogue／analog。验证＝**pytest**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；不发明 Boss／射击语料。`RETRIEVAL_VERSION` 仍 `bm25-e5-rrf-v7`；攻击 tag-only 与 JUMP titlebrand 中性化仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py` 跨语言、`test_retrieval_action_aliases.py`、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、发明 Boss／射击语料、声称 F006／TD 全关

## 白话

本机还有「**标题**画面／标题文字」「英文 transition 转场特效」「**标志**展示」。英文 title／transition／logo 以前对不上。这轮接上；subtitle、catalogue、titlebrand（JUMP 中性化占位）等不算命中。

## Acceptance

- [x] CROSS 增补三组别名
- [x] 正向命中；夹心／残词不命中
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_retrieval_action_aliases.py -q -k title_transition
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不发明 Boss／射击语料。
