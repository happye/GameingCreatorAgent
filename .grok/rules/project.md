# Grok Build — Gaming Creator Agent

Use the root `AGENTS.md` as the shared repository guide. Read `HANDOFF.md` when resuming work and follow `docs/references/agent-workflow.md` for assignments and transfers.

Keep the shared persistent reporting mode on resumption and tool switches: after each key change, give a detailed plain-language report of what the user can now do, the benefit, verified results and remaining limits, and the next concrete action. Workers supply the same information to the integrator; follow the shared reporting protocol.

Keep the shared delivery priority: follow the master plan's current milestone; fix minor issues when straightforward, otherwise record reproduction and impact in technical debt and continue the main deliverable. Do not repeatedly spend time or tokens on one small bug, diagnostic polish or unchanged verification. Apply this to workers and future resumptions.

Keep the shared human-assistance and progress-alignment rules: notify the user promptly when annotation or manual actions are needed, record them in docs/exec-plans/human-inputs.md, and align current milestone, sprint, handoff, assignments and progress at key nodes. Pending human actions block only dependent work. Apply this to workers and future resumptions.

Run `grok inspect` from the repository root to check discovered instruction paths, including `AGENTS.md` and this rules file. Grok may also discover `CLAUDE.md` for compatibility; all entries point to the same shared rules. Keep Grok session history and credentials local; record project decisions and verification in repository artifacts.

Load the shared capability-based subagent routing preference. The [Codex mapping](../../docs/references/codex-agent-routing-guide.md) is specific to Codex models and configuration; do not claim those names work in Grok. Use this tool's actual supported models, bounded context and explicit ownership, and verify execution before claiming routing succeeded.

For substantive milestones follow the shared Planner -> Generator -> independent Evaluator contract in `docs/references/development-agent-pipeline.md`; simple work stays in the parent and is recorded as single-agent work. The portable harness-project-init skill now supplies this tool's native routing adapter; verify actual discovery/model before use rather than treating Codex TOML as this tool's configuration. The integrator persists read-only role outputs.
