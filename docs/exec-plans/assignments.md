# Active assignments

Use `docs/references/agent-workflow.md` for assignment and transfer rules. This table records coordination, not automated locks. A designated coordinator reconciles it before parallel work starts; workers keep detailed evidence in their own sprint record.

| Feature | Owner / tool-session | Branch | Owned paths | State | Sprint record |
| --- | --- | --- | --- | --- | --- |
| F003 integration | Codex root（复核 Grok handoff 后待接力） | `codex/F003-models` | root shared ports, dependencies/tooling, analysis/ASR/vision and docs | ready-for-handoff; F003 false | `sprint-F003.md`, `review-F003-grok-2026-10-04.md` |

F001/F002/F004 are accepted. Grok's ASR/vision/analyze delivery was reviewed by Codex. Scratch worktrees are frozen; root is the source. Local main and origin/main are `ca0394e`; checkpoint `377bb68` is pushed to origin/codex/F003-models. Worker assignments are released; the next owner records takeover here. F003 stays `passes: false`.

下一步按复核记录：价目/费用预留配置、完整滑窗、显式恢复与持久化预算、ASR开始前账本登记及中英参考。然后推进F005/F006，GUI未开始。最新完整verify：332 passed/0skip（20.06s）、Ruff/mypy/CLI及重复wheel通过；技术Demo命令在README。原Grok证据保留在sprint中。

Suggested states: `active`, `ready-for-handoff`, `blocked`, `ready-for-review`. Remove finished assignments after recording their result in `progress.md` and `feature_list.json`.
