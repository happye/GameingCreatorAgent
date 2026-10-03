# Active assignments

Use `docs/references/agent-workflow.md` for assignment and transfer rules. This table records coordination, not automated locks. A designated coordinator reconciles it before parallel work starts; workers keep detailed evidence in their own sprint record.

| Feature | Owner / tool-session | Branch | Owned paths | State | Sprint record |
| --- | --- | --- | --- | --- | --- |

F001 and F002 are accepted. The Windows Job worker delivered its two files from an isolated worktree and root integrated/reviewed/tested them. No active writer remains; F003/F004 are next. Scratch branch/worktree is not a continuation point.

Suggested states: `active`, `ready-for-handoff`, `blocked`, `ready-for-review`. Remove finished assignments after recording their result in `progress.md` and `feature_list.json`.
