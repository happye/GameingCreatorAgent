# Active assignments

协调规则见 `docs/references/agent-workflow.md`。2026-10-04本轮所有worker已冻结并由root整合；无活动并行写入。root后续接手时仍须先查分支与未提交状态。

| Feature | Owner / tool-session | Branch | Scope | State | Evidence |
| --- | --- | --- | --- | --- | --- |
| Demo / F003 / F005 | Codex root | `main`（代码检查点19cfe58；origin/codex/phase0-demo备份） | 全链路、配置/恢复/预算、CLI、SQL3、隔离依赖及共享记录 | accepted / ready-for-handoff | `sprint-demo.md` |
| Pricing / vision / docs | Codex demo_pricing | 独立worker与root整合记录 | 价格/诊断/v2提示、README/AGENTS/规格/quickstart | frozen / integrated | `sprint-demo.md` |
| Local retrieval | Codex demo_retrieval | `codex/demo-retrieval`，checkpoint `4b692d8` | E5/batch1/cache、BM25/cosine/hybrid与固定fixture | frozen / integrated | `sprint-F005-worker.md` |
| F006 runner / SQL3 | Codex demo_benchmark | `codex/demo-benchmark` | 标签评分、schema3/向量/检索持久化、legacy测试修复 | frozen / integrated | `sprint-F006-worker.md`, `sprint-F005-persistence-worker.md` |

F000–F005技术合同已验收。F006工具有合同测试，独立人工 quality gate 仍未通过。2026-10-04 起 Demo 可用性由 Grok Build 在 G: 根目录的 `main` 接手；不要从已冻结 worker 覆盖源码。

2026-10-04 用户重新指定 Codex 接续基础功能；Grok 留下的未提交源码全部保留，基线完整verify561passed/0skip。Codex root负责检查工作台后端/集成/共享记录，只读 ui_review负责风险复核。页面静态资源若另派worker，先建立独立worktree并冻结API；旧worktrees不能覆盖本轮。任务见 `sprint-inspection-workspace.md`。

当前本地/远端提交以HANDOFF和git为准。旧Grok/F003 scratch worktrees保留历史，已冻结；不要从旧分支覆盖当前源码。

## 检查工作台本轮归属

| Owner | Branch/worktree | Owned files | State |
| --- | --- | --- | --- |
| Codex root | `codex/inspection-workspace`，root | ui/server.py、ui/service.py、ui/media.py、tests/test_inspection_http.py及共享文档 | implementing；Grok基线checkpoint32d5a3b |
| Codex inspection_frontend | `codex/inspection-frontend`，`.worktrees/inspection-frontend` | ui/static/{index.html,app.js,style.css}、sprint-inspection-frontend.md | implementing；API合同已冻结 |
| Codex ui_review | 只读root | HTTP错误/注入/状态与范围审查 | done；发现已纳入root修复 |

前后端按 `docs/design-docs/inspection-workspace-api.md` 集成。worker只提交拥有文件，公共记录由root更新；不得从旧scratch覆盖当前源码。
