# Learnings

## 2026-10-04: 工作台必须验证完整交互路径

用户反馈：上轮功能测试通过，但时间轴在预览和片段篮下方，选片需反复滚页面，篮子保留点击顺序导致乱序。仅验证按钮/播放/导出不足以证明工作台可用；桌面验收应同时检查三者在常见视口内可见、面板独立滚动和选择后的滚动保持，篮子及导出应明确排序合同。F006检索质量与UI可用性分别记录，不能相互替代。相关文件：ui/static、scripts/validate-inspection-ui.py、sprint-workspace-usability.md。

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

## 2026-10-04: Switch forwarding and durable inference identity

PowerShell script switches must be forwarded as named typed values (for example -Offline:$Offline), not strings in an argument array. The latter lost offline mode and attempted a package-index request; corrected setup-demo passed entirely offline in project-local directories.

Known model revision and pricing pins belong in the presend fixture metadata. Strict finish_invocation correctly rejected fixtures that changed them after sending. For -I Windows child tests, use explicit -X utf8 rather than assuming PYTHONUTF8 is honored; never hide a decode error with ignore. Keep normal finally-close and intentional os._exit crash behavior distinct.

Parallel follow-up workers must remain in separate worktrees. Preserve newly integrated root edits by giving workers the current checkpoint and copying only owned file diffs back; do not solve ownership conflicts by moving active writers into root.
