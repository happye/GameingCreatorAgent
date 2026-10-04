# Errors

Command failures and integration errors.

---

## [ERR-20261004-001] pytest_cache_winerror_5

**Logged**: 2026-10-04T02:49:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: tests

### Summary
Default pytest cache directory `.cache/pytest` fails with WinError 5 on this machine.

### Error
```
PermissionError: [WinError 5] 拒绝访问。: .cache/pytest/v/cache
FileExistsError: [WinError 183] when creating that directory
```
With `pytest -W error`, the cache warning becomes a session error and hides real results.

### Context
- Command: `python -m pytest -W error` using `cache_dir` from `pyproject.toml`
- Happened twice on 2026-10-04 while running ASR and vision tests
- Workaround that passed: `-p no:cacheprovider --override-ini=addopts= --basetemp=.cache/pytest-grok-tmp` plus `-W "ignore:Unknown config option:pytest.PytestConfigWarning"`

### Suggested Fix
Keep using the cache-disabled command until `.cache/pytest` can be removed by a process that is not holding it. Do not treat the cache error as a product test failure.

### Metadata
- Reproducible: yes
- Related Files: pyproject.toml
- See Also: ERR-20261004-003

### Resolution
- **Resolved**: 2026-10-04T05:10:00+08:00
- **Commit/PR**: uncommitted
- **Notes**: `cache_dir` is `.cache/pytest-cache`. The locked `.cache/pytest` tree was not deleted. Official `./scripts/verify.ps1` then passed with the cache plugin enabled. Not promoted to AGENTS.md; the machine-specific warning is in HANDOFF.md item 4.

---

## [ERR-20261004-002] toolchain_pyc_receipt

**Logged**: 2026-10-04T03:40:00+08:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
`./scripts/verify.ps1` stopped before tests because 135 pinned stdlib `.pyc` files no longer matched `.tools/toolchain-receipt.json`.

### Error
```
Project Python runtime hash differs from the installation receipt.
```
All 135 mismatches were `__pycache__/*.pyc`. No `.py`, `.exe`, or `.dll` differed.

### Context
- `scripts/env.ps1` sets `PYTHONPYCACHEPREFIX` so project scripts write bytecode under `.cache/pycache`.
- Running `.venv\Scripts\python.exe` without that variable rewrites `.pyc` files inside `.tools/python` and breaks the next receipt check.
- Restored the drifted files from `.cache/uv/downloads/cpython-3.13.16-20261001-windows-x64.tar.gz` after checking its SHA256 against `toolchain.json`. The receipt was not edited.

### Suggested Fix
`scripts/env.ps1` now sets `PYTHONDONTWRITEBYTECODE=1` for project scripts. `PYTHONPYCACHEPREFIX` alone still left the pinned `.pyc` files writable. Do not update the receipt. Direct `.venv\Scripts\python.exe` without `env.ps1` can drift them again; restore from the pinned archive.

### Metadata
- Reproducible: yes
- Related Files: scripts/env.ps1, scripts/toolchain.ps1, .tools/toolchain-receipt.json
- See Also: ERR-20261004-001

### Resolution
- **Resolved**: 2026-10-04T05:10:00+08:00
- **Commit/PR**: uncommitted
- **Notes**: `scripts/env.ps1` sets `PYTHONDONTWRITEBYTECODE=1`. `./scripts/verify.ps1` passed its receipt check on 2026-10-04. The receipt file was not edited.

---

## [ERR-20261004-003] pytest_basetemp_winerror_5

**Logged**: 2026-10-04T04:20:00+08:00
**Priority**: high
**Status**: resolved
**Area**: tests

### Summary
`./scripts/verify.ps1` passed Ruff and mypy, then pytest `-W error` failed while removing `.cache/pytest-tmp`.

### Error
```
117 passed, 211 errors in 19.42s
PermissionError: [WinError 5] 拒绝访问。: '\\?\G:\Tools\ChatGPTRepo\GameingCreatorAgent\.cache\pytest-tmp'
Project check failed: -m pytest -W error
```

### Context
- `pyproject.toml` `addopts` used `--basetemp=.cache/pytest-tmp`.
- `Get-Item` can see the directory. `Get-ChildItem` and `Remove-Item` are access denied. The current user is not an administrator, so takeown was not retried.
- A sibling `.cache/pytest-tmp-run` was created, written, and deleted by the same user.
- Offline wheel builds did not run. This is the same permission family as ERR-20261004-001, on a different path.

### Suggested Fix
Point `--basetemp` at `.cache/pytest-tmp-run`. Do not point it back at `.cache/pytest-tmp`. Rerun `./scripts/verify.ps1` from the repository root after `scripts/env.ps1` is loaded. Do not edit the toolchain receipt.

### Metadata
- Reproducible: yes
- Related Files: pyproject.toml, scripts/verify.ps1
- See Also: ERR-20261004-001

### Resolution
- **Resolved**: 2026-10-04T05:10:00+08:00
- **Commit/PR**: uncommitted
- **Notes**: `addopts` now uses `--basetemp=.cache/pytest-tmp-run`. That directory can be created and deleted by the current user. `./scripts/verify.ps1` then exited 0. `.cache/pytest-tmp` remains locked. Not promoted to AGENTS.md.

---
