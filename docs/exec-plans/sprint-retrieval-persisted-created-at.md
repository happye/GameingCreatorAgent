# Sprint：持久化检索信封 createdAt 时区加深

**状态（2026-10-22）：已推送 origin/main a4ceb06（docs 记录提交另记）。** 加深 `assert_persisted_retrieval_contract`：`createdAt` 必为非空字符串，`datetime.fromisoformat`（`Z`→`+00:00`）可解析，且必须带时区（拒绝 naive）。pytest + demo-phase0 `timeline.sqlite3` 只读（217 行）。验证＝**pytest + 只读 SQLite**。0 付费；不代选 A／B／D；不标 F006 true；**不宣称 TD004／TD010 关单**；不改写 SQLite；`RETRIEVAL_VERSION` 仍 `bm25-e5-rrf-v7`；攻击 tag-only 仍保留。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、SQLite 只读测试、本 sprint、交接 docs
- 不做：付费视觉、改 feature_list、代选 A／B／D、改写 DB、声称 F006／TD 全关

## 白话

持久化检索信封上的 **createdAt** 以前没卡死。这轮要求必须是带时区的 ISO 时间（例如 `…+00:00` 或 `Z`），缺时区或乱写字符串一律拒绝。本机 217 条只读全过。

## Acceptance

- [x] createdAt 非空、可解析、必须有时区
- [x] demo-phase0 只读绿；伪造 naive／垃圾拒绝；Z 后缀仍接受
- [x] 已推送 `origin/main`（feature／docs SHA 见 HANDOFF）

## Verification

```text
pytest tests/test_retrieval_sqlite_local_readonly.py -q
```

## Non-claims

不标 F006／F009／F010 true；不代选 A／B／D；不宣称 TD004／TD010／人评关单；不改写 artifacts／SQLite。
