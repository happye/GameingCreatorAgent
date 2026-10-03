# Progress Log

## 2026-10-03 — F001 isolated Python core accepted

- Installed hash-verified portable uv 0.12.22 and standard CPython 3.13.16/build 20261001 exclusively inside `.tools`; created `.venv` without system packages and pinned 17 package entries in `uv.lock`.
- Added installable four-layer package, CLI input/config/resume checks, Int64 source-time records and typed Provider/usage/cancellation contracts. Processing remains explicitly unimplemented; no dummy run or database is created.
- Validation: 50 pytest tests, Ruff formatting/lint, strict mypy for source/Provider fake and import boundaries pass. Two offline wheels have the same SHA256; only package/metadata entries are included. Installed CLI help/version pass.
- Offline setup from another directory preserves caller location and rejects inherited external uv project settings. User/machine environment and three Python registry subtree fingerprints stayed unchanged; this checks those boundaries, not all system activity.
- Fixed isolated Python probes rewriting local bytecode (`-I` ignores cache environment); use `-I -B` and restore from the verified archive. Read-only contract/environment reviewers found remaining pipeline checks belong to later features.
- Shared entry rules, README, architecture, engineering/environment/testing docs and handoff reconciled. Only F000/F001 true; F002 media preprocessing is next. No paid API requests this round.

## 2026-10-03 — Language clarification and Phase 0 baseline v2

- User clarified that C# is optional. A read-only language review selected Python for Phase 0 to directly use local ASR/embedding/evaluation tooling and reduce cross-language IPC; later desktop UI remains undecided. ADR-001 supersedes the initial .NET recommendation, not product scope or acceptance.
- Synchronized: AGENTS/CODEX/README/HANDOFF, architecture/engineering specs, feature/task lists, coding/testing/environment rules and prerequisite scripts. Shared Claude/Grok adapters inherit AGENTS rather than duplicating the language decision.
- Isolation: portable uv and CPython under `.tools`, all packages in `.venv`, project caches/temp; uv Windows registry registration/global links explicitly disabled. F001 pins versions and verifies imports/build; no Python/uv or global packages were installed in this review.
- Version checkpoint: review commit `55d0fb1` and Python decision `c2b7571` pushed to GitHub `main`. Initial HTTPS connection failed; a per-command HTTP/1.1 retry succeeded without changing global Git/network settings. `main` now tracks `origin/main`.
- Acceptance: only F000 true. CLI/ASR/SQLite/search and formal human Top10 benchmark still unimplemented/unverified. Next task is Python F001, not .NET setup; earlier progress entries are historical evidence.
- Verification after alignment: scaffold, PowerShell parsing, process paths and uv registry/link guard checks passed; media and metric smoke reruns passed. Full check correctly exits 1 for missing local uv/CPython venv. The language reviewer found no remaining contract conflict; no paid API rerun.

## 2026-10-03 — F000 review, limited Phase 0 experiments, and engineering baseline

- Delivered: six-axis reverse review, four-project architecture, CLI/time/Provider/SQLite/cost/recovery contracts, fixed-slot benchmark rules, F001–F006 dependencies and explicit ownership. Original product plan unchanged; F000 accepted as a document review only.
- Actual evidence: three short videos totaling 214.862313 seconds; local preprocessing and synthetic audio/no-audio smoke passed. DeepSeek `deepseek-flash` returned valid structured observations for 15 frames across three requests; conservative CNY estimate totals 0.024076, not confirmed billing or a source-hour benchmark.
- Review fixes: integer-only grades with boolean/string/fraction/out-of-range regression; all runtime/package/model/temp caches redirected inside the project; .NET 10-only prerequisite check; complete embedding space identity and run-scoped reuse for unresolved revisions. Three specialist reviews and a final read-only consistency review completed.
- Verification: scaffold, metric regression, media smoke, PowerShell parsing and process environment isolation passed. Full prerequisite check correctly exits 1 for missing project-local .NET 10 SDK. No global packages or system environment changes.
- Version setup: user-designated GitHub repository configured as `origin`; branch renamed to `main`. Raw media, credentials, portable tools, virtual environments, caches and generated evidence remain ignored.
- Remaining: application CLI, local ASR, SQLite, timeline/search, independent human labels, long-video speed, cold per-hour cost and real Top10 quality gate. F001–F006 remain false; no active coding assignment. Resume F001 from `HANDOFF.md`.

## 2026-10-03 — Cross-tool collaboration alignment

- Completed: Claude Code import adapter, Grok project rules adapter, shared task/ownership protocol, root handoff snapshot, assignment register, and sprint transfer fields. Codex guidance and README now refer to the shared protocol.
- Verification: scaffold check and whitespace checks passed; `CLAUDE.md` imports the existing `AGENTS.md`. Local versions: Claude Code 2.1.177 and Grok Build 1.0.46.
- Limitation: `grok inspect --json` reported `projectTrusted: false` and an empty project instruction list. Native loading remains to be checked after first-use repository trust; no Claude/Grok model session was run.
- Active feature: none. Product feature acceptance remains unchanged; F000 is next.
- Resume from: `HANDOFF.md`. For parallel work, assign distinct branches/worktrees and owned files before starting.

## 2026-10-03 — Harness initialization

- Completed: Codex-focused repository scaffold, Phase 0 scope and feature list, documentation map, prerequisite checker, and Git initialization.
- Active feature: none. F000 is next and remains `passes: false`.
- Verification: `./scripts/init.ps1 -CheckOnly` validates the scaffold; a full prerequisite check needs a .NET SDK before implementation can start.
- Next: write the F000 reverse review in `docs/exec-plans/`, then revise provisional scope or architecture as the evidence requires.
