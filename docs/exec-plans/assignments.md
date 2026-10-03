# Active assignments

Use `docs/references/agent-workflow.md` for assignment and transfer rules. This table records coordination, not automated locks. A designated coordinator reconciles it before parallel work starts; workers keep detailed evidence in their own sprint record.

| Feature | Owner / tool-session | Branch | Owned paths | State | Sprint record |
| --- | --- | --- | --- | --- | --- |

F001/F002/F004 are accepted. F004 worker code and tests are integrated, reviewed and verified in root; scratch worktrees are frozen. GitHub sync is pending after connection failures, see HANDOFF. F003 readiness research is read-only; no ASR packages/models have been installed. No active writer remains; root will register F003 before implementation.

Suggested states: `active`, `ready-for-handoff`, `blocked`, `ready-for-review`. Remove finished assignments after recording their result in `progress.md` and `feature_list.json`.
