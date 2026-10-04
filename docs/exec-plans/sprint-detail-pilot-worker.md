# F010 detail pilot worker

2026-10-05; owner /root/detail_pilot; branch codex/detail-pilot; base 903c9cc.

## Ownership and design

Only scripts/validate-visual-details.py, tests/test_visual_detail_pilot.py and this record. Other agents own provider, application and shared documents; do not revert their edits. Uses root project .venv Python -B and caches, with this worktree's src on PYTHONPATH. No installation, global configuration or paid requests.

Same four-second source window, nine genuine observations: A=V4/512, B=V5/512, C=V5/1280. Width groups are independently decoded and checked for equal original source clocks and source identity. Distinct preprocessing run IDs distinguish image variants. Static-C explicitly replaces pixels while retaining observation times; reversed-C reverses references and must fail before HTTP. Neither is a human action label.

## Progress and recovery

Worktree created at 903c9cc; reviewed existing temporal pilot, provider JPEG/input contracts and budget recorder. Implemented isolated pilot reusing existing atomic JSON, invocation recorder and cost reporting. Dry preparation is the default; output must be a fresh directory in project artifacts. Report/invocations exist before API work; manifest is frozen before transport creation; each outcome has an atomic case JSON plus cumulative report/cost. Quality gate stays null; source footage, models and generated artifacts remain ignored.

## Verification and handoff

- Project-local Python -B: pytest tests/test_visual_detail_pilot.py: 9 passed in 0.64s. Scratch/output stays root .cache/detail-pilot-worker/pytest-2. Tests use bounded JPEG framing and mocked media/HTTP only, not real visual evidence.
- Ruff check and format passed for both owned Python files; strict mypy with follow-imports=silent passed for both files.
- Tests cover same nine source instants / distinct variants, source or clock mismatch rejection, frozen dimensions/prompt/price hashes, dry transport prohibition, existing/outside output protection, missing auth after freeze, all outcomes durable, reversed input zero HTTP, and unknown costs retaining reservations until budget exhaustion. No external API call occurred.
- Initial fixture response omitted assistant role, correctly failed provider schema checks; fixture corrected without relaxing provider parsing. Final run has no failures.

Root may cherry-pick this worker commit, then run from root after env.ps1:

```powershell
.venv/Scripts/python.exe -B scripts/validate-visual-details.py --video "<local video>" --output artifacts/visual-details-28 --window-start 28
```

Add --execute only for the authorized real experiment in a NEW output directory (dry outputs cannot be reused). Defaults: max-cost-cny=5, request-limit=8 remote attempts, 4096 output tokens, 90s per provider case including retries. Each window has four sendable cases plus one local reversed-input control. Price is pinned to deepseek-flash-cny-2026-10-04, estimate not invoice. Optional additional --window-start values share the same budget; insufficient request/unknown-cost reservations are durable failures rather than unbounded continuation.

Worker frozen after commit. Root owns actual media/API execution, provider integration, shared documentation and human quality acceptance. No real quality improvement or new API cost is claimed here.
