# Sprint：定向补窗草稿只读写出脚本（ignored artifacts）

**状态（2026-10-21）：已交付并推送 6ab066a。** 在提案草稿模板之上，增加只读写出路径：从真实／夹具 `analysis_coverage.json` 生成未冻结草稿到输出目录（建议 `artifacts/`，仓库已 ignore）。**不代选** A／B／D，0 付费，不启动 launcher，不声称三缺口已清。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`directed_gap_fill.write_directed_gap_fill_proposal_draft`、`scripts/prepare-directed-gap-fill-draft.py`、可选 PS1、相关 pytest、本 sprint、交接文档顶部
- 不做：付费、代选 B、把回执当授权、改 feature_list

## 白话

1. 以前只有「内存里能生成草稿」；现在多一个本机命令，把草稿写到忽略目录，方便你以后若选 B 时打开看。
2. 写出后立刻回读检查：授权／选 B／消缺口必须仍是 false。
3. 目录里有 README 写明「未授权，不能直接发模型」。

## Acceptance

- [x] write helper + CLI／PS1；相关 pytest 绿
- [x] 回读 inert 断言；夹带成功窗拒绝且不落盘草稿
- [x] `.gitignore` 已含 `artifacts/`（本轮确认，无需新规则则不改）
- [x] 0 DeepSeek／0 launcher；F006/F009/F010 仍 false
- [x] 普通提交并推送 `origin/codex/visual-details`

## Stop

- 禁止付费；禁止代选 A／B／D；禁止把草稿目录当批准证据。

## Follow-on

- 同帧诊断证据链接：见 [sprint-coverage-gap-diagnosis-link.md](sprint-coverage-gap-diagnosis-link.md)。
