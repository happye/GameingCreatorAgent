# Active assignments

协调规则见 `docs/references/agent-workflow.md`。2026-10-04本轮所有worker已冻结并由root整合；无活动并行写入。root后续接手时仍须先查分支与未提交状态。

| Feature | Owner / tool-session | Branch | Scope | State | Evidence |
| --- | --- | --- | --- | --- | --- |
| Demo / F003 / F005 | Codex root | `codex/phase0-demo` | 全链路、配置/恢复/预算、CLI、SQL3、隔离依赖及共享记录 | accepted / ready-for-handoff | `sprint-demo.md` |
| Pricing / vision / docs | Codex demo_pricing | 独立worker与root整合记录 | 价格/诊断/v2提示、README/AGENTS/规格/quickstart | frozen / integrated | `sprint-demo.md` |
| Local retrieval | Codex demo_retrieval | `codex/demo-retrieval`，checkpoint `4b692d8` | E5/batch1/cache、BM25/cosine/hybrid与固定fixture | frozen / integrated | `sprint-F005-worker.md` |
| F006 runner / SQL3 | Codex demo_benchmark | `codex/demo-benchmark` | 标签评分、schema3/向量/检索持久化、legacy测试修复 | frozen / integrated | `sprint-F006-worker.md`, `sprint-F005-persistence-worker.md` |

F000–F005技术合同已验收，整体557passed/0skip、Ruff/mypy/离线wheel通过。F006工具有合同测试，独立人工quality gate仍未通过。英文实视频漏召回、puresemantic负例误召回和小时级资源边界为接续优先项，见TD004/TD005。新owner需登记接手，不重复初始化或重做已完成模型/CLI。

当前本地/远端提交以HANDOFF和git为准。旧Grok/F003 scratch worktrees保留历史，已冻结；不要从旧分支覆盖当前源码。
