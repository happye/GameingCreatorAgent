# Claude Code — Gaming Creator Agent

For a new chat, read root [`STATUS.md`](STATUS.md) then the short [`HANDOFF.md`](HANDOFF.md). Explain rejection triggers and whole-task stopping; prioritize defects that block the deliverable. Continue authorized local development without repeating completed annotation or paid attempts.

@AGENTS.md

The import loads the shared repository guide. Follow `docs/references/agent-workflow.md` for assignments and transfers. Acceptance criteria remain in `feature_list.json` regardless of which tool started the task.

**STATUS-first:** update `STATUS.md` once at milestone or session end; update `docs/exec-plans/progress-board.md` only when counts change. Do not sync seven docs on every change, and do not open a docs commit solely to record tip SHA or push status.

Persist shared preferences from `AGENTS.md`: plain-language reporting after key changes; milestone delivery over bug-polishing loops; prompt human-input notices into `docs/exec-plans/human-inputs.md`; fees (¥50 monthly preauth) and freeze of P046–P051 / P038 until first mode is human-evaluated.

In Claude Code, use `/memory` to confirm this file and imported `AGENTS.md` are loaded. Keep personal settings in ignored local files. Record decisions and verification in the repository so Codex and Grok can resume them.

Capability-based routing: see [Claude routing guide](docs/references/claude-agent-routing-guide.md). Do not pass Codex model names as Claude aliases. For substantive milestones use Planner → Generator → independent Evaluator (`docs/references/development-agent-pipeline.md`); simple work stays single-agent. Verify discovery/model before claiming routing succeeded.

## Claude-native subagents

Roles in `.claude/agents/`: `gc-explorer`, `task-progress-monitor`, `gc-runner` (haiku); `gc-commander`, `gc-coder`, `gc-doc-writer`, `gc-reviewer` (sonnet); `code-quality-guard`, `gc-architect` (opus). Mapping and limits: Claude routing guide. Keep the main model as the user chose. Roles load at session start only; if missing, use general-purpose with the role file's instructions and explicit model — state read-only limits in the prompt and check `git status` afterwards. Choose `gc-reviewer` or `code-quality-guard`, not both.

## Working from a cloud session

A Claude session may run in a Linux cloud container linked to the user's Windows machine. Develop in a separate clone/worktree, run Python checks there, sync through GitHub; record which checks ran on Linux and which Windows-only checks (`verify.ps1`, project-local FFmpeg, real footage) remain. Never edit the user's working tree while another tool's writer is active, never upload footage or project databases to the cloud, and send no images to paid providers without explicit authorization of a concrete proposal.
