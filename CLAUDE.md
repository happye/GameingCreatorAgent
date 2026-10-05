# Claude Code — Gaming Creator Agent

@AGENTS.md

The import above loads the shared repository guide. Before continuing an existing task, read `HANDOFF.md` and follow `docs/references/agent-workflow.md`; acceptance criteria remain in `feature_list.json` regardless of which tool started the task.

Persist the user's reporting preference across sessions: after each key change, explain the result and user benefit in detailed plain language, state what was verified and remains uncertain, and describe the next concrete action. This also applies to subagents; use the shared reporting protocol in `docs/references/agent-workflow.md`.

In Claude Code, use `/memory` to check that this file and the imported `AGENTS.md` are loaded. Keep any personal settings in ignored local files. Record decisions and verification in the repository so Codex and Grok Build can resume them.
