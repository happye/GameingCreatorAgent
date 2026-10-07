# Claude Code — Gaming Creator Agent

@AGENTS.md

The import above loads the shared repository guide. Before continuing an existing task, read `HANDOFF.md` and follow `docs/references/agent-workflow.md`; acceptance criteria remain in `feature_list.json` regardless of which tool started the task.

Persist the user's reporting preference across sessions: after each key change, explain the result and user benefit in detailed plain language, state what was verified and remains uncertain, and describe the next concrete action. This also applies to subagents; use the shared reporting protocol in `docs/references/agent-workflow.md`.

Persist the delivery priority too: follow the master plan and current milestone, fix minor issues only when straightforward, and record issues needing repeated investigation in technical debt before returning to the main deliverable. Avoid successive bug-polishing turns, diagnostic additions and unchanged full verification; this applies to subagents and tool handoffs.

Persist the human-assistance and progress-alignment rules in `AGENTS.md`: promptly notify the user of required annotation or manual actions, record them in `docs/exec-plans/human-inputs.md`, and keep current milestone, sprint, handoff, assignments and progress aligned at key nodes. Pending human actions block only dependent work; subagents and future sessions follow the same rules.

In Claude Code, use `/memory` to check that this file and the imported `AGENTS.md` are loaded. Keep any personal settings in ignored local files. Record decisions and verification in the repository so Codex and Grok Build can resume them.
