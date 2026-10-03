# Active assignments

Use `docs/references/agent-workflow.md` for assignment and transfer rules. This table records coordination, not automated locks. A designated coordinator reconciles it before parallel work starts; workers keep detailed evidence in their own sprint record.

| Feature | Owner / tool-session | Branch | Owned paths | State | Sprint record |
| --- | --- | --- | --- | --- | --- |
| F003 | Codex root | `codex/F003-models` | shared ports, optional dependencies/tooling, native/model preparation, validation and docs | active | `sprint-F003.md` |
| F003 ASR | Codex root (worker delivery integrated) | `codex/F003-models` | local ASR worker/facade, actual runtime validation and tests | active | `sprint-F003.md` |
| F003 SQLite v2 | Codex root (worker delivery integrated) | `codex/F003-models` | uncertainty migration and integration verification | active | `sprint-F003.md` |
| F003 Vision | Codex `f003_vision_review` | `codex/F003-vision` / `.worktrees/f003-vision` | vision adapter, budget and HTTP transport, their tests | active | root consolidates into `sprint-F003.md` |
| F003 compatibility | Codex `f003_av_compat` | read-only | official PyAV/faster-whisper compatibility metadata | active | root consolidates into `sprint-F003.md` |

F001/F002/F004 are accepted. F004 worker code and tests are integrated, reviewed and verified in root; scratch worktrees are frozen. Local main is `ca0394e`; origin/main remains `754125f` after another connection failure. F003 preparation/ASR now active; runtime install/inference evidence must be recorded separately from prior read-only metadata research.

Suggested states: `active`, `ready-for-handoff`, `blocked`, `ready-for-review`. Remove finished assignments after recording their result in `progress.md` and `feature_list.json`.
