# Grok Build — Gaming Creator Agent

Use the root `AGENTS.md` as the shared repository guide. Read `HANDOFF.md` when resuming work and follow `docs/references/agent-workflow.md` for assignments and transfers.

Keep the shared persistent reporting mode on resumption and tool switches: after each key change, give a detailed plain-language report of what the user can now do, the benefit, verified results and remaining limits, and the next concrete action. Workers supply the same information to the integrator; follow the shared reporting protocol.

Keep the shared delivery priority: follow the master plan's current milestone; fix minor issues when straightforward, otherwise record reproduction and impact in technical debt and continue the main deliverable. Do not repeatedly spend time or tokens on one small bug, diagnostic polish or unchanged verification. Apply this to workers and future resumptions.

Run `grok inspect` from the repository root to check discovered instruction paths, including `AGENTS.md` and this rules file. Grok may also discover `CLAUDE.md` for compatibility; all entries point to the same shared rules. Keep Grok session history and credentials local; record project decisions and verification in repository artifacts.
