# Claude Code — Gaming Creator Agent

@AGENTS.md

This adapter is for Claude Code only. Read the shared Delivery discipline in `AGENTS.md` before task planning or delegation; keep those principles there rather than copying them into roles or personal memory. Include task-relevant shared constraints when delegating.

New chat: read `STATUS.md`, then `HANDOFF.md`, and continue authorized local work without repeating completed annotation or paid attempts. When a task stops, say what triggered it, how far it affects the whole task, and what was saved; fix defects that block the deliverable first. Use `/memory` to confirm this file and `AGENTS.md` are loaded; keep personal settings in ignored local files.

## Subagents

Roles in `.claude/agents/`: `gc-explorer`, `task-progress-monitor`, `gc-runner` (haiku); `gc-commander`, `gc-coder`, `gc-doc-writer`, `gc-reviewer` (sonnet); `code-quality-guard`, `gc-architect` (opus). Mapping and limits: `docs/references/claude-agent-routing-guide.md` (Codex model names are not Claude aliases). Keep the main model as the user chose. Simple work stays single-agent; use Planner → Generator → Evaluator only for milestones (`development-agent-pipeline.md`). Pick `gc-reviewer` or `code-quality-guard`, not both. Roles load at session start; if missing, use general-purpose with the role file's instructions and an explicit model, state read-only limits, and check `git status` afterwards.

## Cloud sessions

In a Linux cloud container, work in a separate clone or worktree, sync through GitHub, and record which Windows-only checks (`verify.ps1`, project FFmpeg, real footage) remain. Never edit the user's tree while another tool's writer is active, never upload footage or project databases, and send no images to paid providers without explicit authorization of a concrete proposal.

Testing scope and full-rerun limits come from `AGENTS.md` §Testing; apply them after resuming a chat as well.
