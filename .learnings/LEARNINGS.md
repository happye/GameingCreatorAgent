# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20261004-001] best_practice

**Logged**: 2026-10-04T05:30:00+08:00
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Do not merge native stderr when calling `scripts/verify.ps1` from Windows PowerShell 5.1.

### Details
`uv.exe` writes progress such as `Resolved 38 packages` to stderr. The script sets `$ErrorActionPreference = 'Stop'`. Redirecting the script with `*>` turns that stderr line into a `NativeCommandError` and stops the script before Ruff. Run the script directly, or record it with `Start-Transcript`. The receipt check and pytest are unrelated to that failure.

### Suggested Action
Call `./scripts/verify.ps1` without `*>` or `2>&1` when the caller needs the real exit code.

### Metadata
- Source: error
- Related Files: scripts/verify.ps1
- Tags: powershell, verify
- See Also: ERR-20261004-003

---
