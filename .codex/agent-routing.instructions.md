## Persistent subagent model routing

User requested capability-based model routing to conserve tokens and quota. Delegate only bounded, independent work when it reduces the main context or provides necessary specialist verification; handle simple steps directly. Do not create duplicate reviewers or continuously poll unchanged progress.

Use personal/project task roles: task_explorer = gpt-6-luna/high; task_progress_monitor = gpt-6-luna/low; task_developer = gpt-6.1-sol/medium; task_reviewer = gpt-6.1-sol/medium; task_quality_guard = gpt-6.1-sol/high; task_architect = gpt-6-astra/low. Use the architect only for genuinely complex design and the quality guard for data, costs, persistence, concurrency or identity risks. Default unnamed subagents use gpt-6-luna/medium. The parent model remains the user's choice.

If the current session cannot recognize a new custom role, use an available default/worker role with an explicit model and reasoning effort from this mapping and put the intended role instructions in the task. Do not use an unavailable agent_type or silently substitute a third-party preset. Model overrides need a fresh task context: use fork_turns="none" when the tool requires it, supplying only the necessary task, paths, constraints and evidence. Full-history forks inherit the parent model in that runtime.

For writes, assign file ownership; tell workers they are not alone and must preserve others' edits. Read-only roles must not mutate files or trigger external actions; parent runtime permission overrides can still supersede a role's sandbox default. Respect each project's AGENTS.md, phase gates, fee authorization and handoff rules. No recursive delegation by default.

Verify models from runtime-supported options and execution metadata, never an agent's self-reported name. Escalate once with evidence if a task exceeds the selected model's capability; avoid repeated low-model attempts followed by repeated heavyweight rechecks. Defaults apply to newly spawned agents, not existing children. Do not claim a fixed percentage of savings without a measured comparison.
