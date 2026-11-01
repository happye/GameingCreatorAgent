# Repository Guidelines

## Project and source of truth

Gaming Creator Agent turns local game footage and a brief into content. Phase 0 CLI analyzes footage and searches a semantic timeline; human retrieval acceptance remains pending. Read `游戏内容创作与商业化产品总方案 V1.0.txt`, `docs/product-specs/phase-0.md`, and `feature_list.json` before changing scope.

**Current state:** root [`STATUS.md`](STATUS.md) (update once at milestone/session end). Short [`HANDOFF.md`](HANDOFF.md) is an overwrite snapshot (≤5KB). Do **not** sync seven docs on every change or open a docs commit just to record tip SHA / push.

## Repository map

- `src/gamingcreator/{cli,application,domain,infrastructure}/` · `ui/` · `tests/test_*.py`
- `docs/design-docs/` · `docs/product-specs/` · `docs/exec-plans/` · `docs/references/` · `docs/archive/` (dated history)
- `prompts/`, `templates/`, `music/`: future assets. Never commit footage or credentials.
- Tool adapters: `CODEX.md`, `CLAUDE.md`, `.grok/rules/project.md` → shared rules here and in `docs/`.
- `.claude/agents/` / committed `.codex/agents/`: nine roles each; routing guides under `docs/references/`.
- Quantified board: `docs/exec-plans/progress-board.md` — update **only when counts change**.

## Environment and commands

Windows PowerShell. Runtimes in `.tools/`, packages in `.venv/`, caches in `.cache/`; never install globally. Pin via `toolchain.json`. See `docs/references/isolated-environment.md`.

Core scripts (details in `docs/references/` and each script's comment header):

- `./scripts/setup-demo.ps1` · `run-demo.ps1` · `run-ui.ps1` · `Start-Workspace.cmd`
- `./scripts/init.ps1` · `verify.ps1` · `search-project.ps1` · `confirm-detail-billing.ps1`
- Benchmark / inventory / shots / OCR / proxy / desktop / portable app: `prepare-benchmark*.ps1`, `inventory-sources.ps1`, `detect-shots.ps1`, `ocr-frames.ps1`, `make-proxy.ps1`, `build-desktop.ps1`, `build-app.ps1`, `install-app.ps1`
- Offline status dump: `python -B scripts/status.py`

Paid vision starts only from an explicit authorized path (e.g. `run-demo.ps1 -Video`). Workbench acceptance: `/acceptance` — see `benchmark-workspace-guide.md`.

## Architecture and coding

Follow `docs/design-docs/architecture.md`, `phase-0-engineering-spec.md`, ADR-001/002/003. Four-space indent; snake_case / PascalCase; Ruff + mypy. Domain excludes I/O. Preserve local video bytes, source clocks, provider/prompt/embedding identities, and unknown costs. Basket/export order follows source time; retrieval keeps rank.

## Testing and acceptance

pytest `tests/test_*.py`; `docs/references/testing-guide.md` and `phase-0-benchmark.md`. Top-10 Useful Rate: ten fixed slots; missing/duplicate count zero; usable events ≥70% after human judgment. Multi-frame / index hits do not prove action understanding. Mark `passes: true` only with feature evidence. Preparation readiness ≠ F006 acceptance.

## Changes, commits, worktrees

Start from `STATUS.md` then short `HANDOFF.md` and `docs/references/agent-workflow.md`. Simultaneous writers: separate worktrees under `.worktrees/` (not `.cache/`), ≤3 active; retire after integration. Imperative `chore:`/`docs:`/`feat(F002): …`. Never commit secrets, footage, generated media, or databases.

## Cache and media limits

`.cache/` is rebuildable data. One-shot scripts: `.cache/scratch/` (safe to delete). Media intermediates need byte/dir/free-space budgets; FFmpeg `-fs` hit = failed render. Reclaim test fixture media after teardown. Never reclaim models, user creations, original analysis/evidence, billing, labels, or active work. See `cache-maintenance-guide.md`.

## Delivery, reporting, human help (persistent)

- Prefer milestone delivery over polishing one small bug; record hard-to-fix issues in `docs/exec-plans/tech-debt.md` and return to the main line.
- **Primary e2e metrics** (see `STATUS.md` table + `python -B scripts/status.py`): planned51 · first★22 · Phase0 F passes · quality 0/8 real steps · tech-debt · human must/future · freeze set. Tier ✅/🟡/⬜; quality/release separate.
- **Report to the user only when those primary metrics change.** Format: ≤150 Chinese characters + **one** openable artifact path. Protocol details: `agent-workflow.md`. Do not report tip SHA / push as a progress update.
- Need user annotation/manual help → notify promptly and record in `docs/exec-plans/human-inputs.md`; pending human items block only dependent work.
- Subagent routing: `docs/references/codex-agent-routing-guide.md` / `claude-agent-routing-guide.md`. Planner→Generator→Evaluator: `development-agent-pipeline.md`.

## STATUS / fees / freeze

See [`STATUS.md`](STATUS.md). Numbers from `feature_list.json` / `progress-board.md` / `tech-debt.md` / `human-inputs.md` — never invent counts; never flip `passes` or product delivery statuses from harness docs work.

- Monthly preauth **¥50**: user-designated footage analysis only; each overage call needs a fresh ask; hard send gate stays. Zero-charge confirmations: `docs/references/detail-billing-confirmation-guide.md` (do not grant new sends).
- **Frozen until first mode human-evaluated:** P046–P051 and P038 (auto-publish) — no new scope.
- Protections: no secret/media/DB commits; paid calls gated; evidence/ledger immutable; no auto re-pay/re-label; toolchain check may narrow but not remove.

## Accelerated product path

Follow `docs/exec-plans/accelerated-product-roadmap.md` and ADR-003 across all 51 planned items. Quality / implementation / commercial ship statuses stay separate. Do not mark partial or stub APIs as full delivery. Prefer real end-to-end slices.
