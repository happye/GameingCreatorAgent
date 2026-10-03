# Active assignments

Use `docs/references/agent-workflow.md` for assignment and transfer rules. This table records coordination, not automated locks. A designated coordinator reconciles it before parallel work starts; workers keep detailed evidence in their own sprint record.

| Feature | Owner / tool-session | Branch | Owned paths | State | Sprint record |
| --- | --- | --- | --- | --- | --- |

F001 is accepted; one writer and read-only contract/environment/final documentation reviews completed. Results are in sprint-F001 and feature_list. F002 design is read-only preparation; implementation remains unassigned and F002–F006 unverified.

Suggested states: `active`, `ready-for-handoff`, `blocked`, `ready-for-review`. Remove finished assignments after recording their result in `progress.md` and `feature_list.json`.
