# Claude Code — Gaming Creator Agent

For a new chat, follow the current HANDOFF and its resumption checklist. Explain the rejection trigger and whole-task stopping mechanism; prioritize defects blocking the deliverable. Continue authorized local development without repeating completed annotation or paid attempts.

@AGENTS.md

The import above loads the shared repository guide. Before continuing an existing task, read `HANDOFF.md` and follow `docs/references/agent-workflow.md`; acceptance criteria remain in `feature_list.json` regardless of which tool started the task.

Persist the user's reporting preference across sessions: after each key change, explain the result and user benefit in detailed plain language, state what was verified and remains uncertain, and describe the next concrete action. This also applies to subagents; use the shared reporting protocol in `docs/references/agent-workflow.md`.

Persist the delivery priority too: follow the master plan and current milestone, fix minor issues only when straightforward, and record issues needing repeated investigation in technical debt before returning to the main deliverable. Avoid successive bug-polishing turns, diagnostic additions and unchanged full verification; this applies to subagents and tool handoffs.

Persist the human-assistance and progress-alignment rules in `AGENTS.md`: promptly notify the user of required annotation or manual actions, record them in `docs/exec-plans/human-inputs.md`, and keep current milestone, sprint, handoff, assignments and progress aligned at key nodes. Pending human actions block only dependent work; subagents and future sessions follow the same rules.

Persist the progress-board rule in `AGENTS.md`: after every major change update `docs/exec-plans/progress-board.md` (counts from feature_list/tech-debt/human-inputs, never estimates) in the same commit as the other alignment documents, read its section 6 when starting and update it before handoff, and quote its key number changes when reporting. Subagents report to the integrator, who updates the board.

In Claude Code, use `/memory` to check that this file and the imported `AGENTS.md` are loaded. Keep any personal settings in ignored local files. Record decisions and verification in the repository so Codex and Grok Build can resume them.

Load the shared capability-based subagent routing preference from AGENTS.md on handoff. The [Codex mapping](docs/references/codex-agent-routing-guide.md) uses Codex model names and TOML; do not pass these names as Claude aliases. Preserve minimal context, explicit ownership, necessary specialist checks and truthful runtime evidence when using this tool's own supported delegation.

For substantive milestones follow the shared Planner -> Generator -> independent Evaluator contract in `docs/references/development-agent-pipeline.md`; simple work stays in the parent and is recorded as single-agent work. The portable harness-project-init skill supplies this tool's native routing adapter; verify actual discovery/model before use rather than treating Codex TOML as this tool's configuration. The integrator persists read-only role outputs.

## Claude-native subagents

Project roles live in `.claude/agents/` (mirroring the user's 暮云 project structure): `gc-explorer`, `task-progress-monitor` and `gc-runner` use haiku; `gc-commander` (planner), `gc-coder` (generator), `gc-doc-writer` and `gc-reviewer` (evaluator) use sonnet; `code-quality-guard` (critical-boundary evaluator) and `gc-architect` use opus. Mapping to the Codex roles, usage rules and verification limits are in the [Claude routing guide](docs/references/claude-agent-routing-guide.md). Keep the main model as the user chose it. Roles are discovered only at session start; when they are not listed, use the built-in general-purpose agent with the same explicit model and the role file's instructions, never a full-history fork. That fallback does not enforce the role's tool list, so state read-only limits in the prompt and check `git status` afterwards. Choose `gc-reviewer` or `code-quality-guard`, not both.

## Working from a cloud session

A Claude session may run in a Linux cloud container linked to the user's Windows machine. Then develop in a separate clone (a separate worktree under the shared protocol), run the Python checks there, and sync through GitHub; record which checks ran on Linux and which Windows-only checks (`verify.ps1`, project-local FFmpeg, real footage) remain. Never edit the user's working tree while another tool's writer (for example a Codex DSH request) is active, never upload footage or project databases to the cloud, and send no images to paid providers without the user's explicit authorization of a concrete proposal.
