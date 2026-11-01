# One-click workspace launcher

Owner: workspace_launcher; isolated worktree `.worktrees/workspace-launcher`, branch `codex/workspace-launcher`. Other agents own server/health and shared records. Only `Start-Workspace.cmd`, `scripts/start-workspace.ps1`, `tests/test_workspace_launcher.py` and this sprint belong to this worker.

## Scope and status

2026-10-04: implemented process-only PowerShell policy, isolated environment, hidden Python HTTP helper, browser opening, local unique logs and PID state, 15-second readiness, loopback requests without proxies, repository identity checks, and a mutex to serialize simultaneous launches. Unrelated listeners are reported and never stopped. Launching the UI does not analyze footage or call a model.

Root added `/api/health` with `application`, `repository`, `pid`, `parentPid`, `apiVersion`. No dependencies or global configuration changed.

First real lifecycle run: 1 passed, 3 failed. Foreign listeners stayed alive. The isolated Windows Python executable is a venv redirector, so its PID differs from the interpreter serving health. Corrected readiness to verify the live interpreter's `parentPid` against the owned helper, recording both PIDs. Retain the process handle so quick startup failures expose their exit code. A copied local venv redirector in a temporary repository with spaces exercises actual quoted startup failure, without installing anything.

Second run: 2 passed, 2 failed. Capturing a background Windows process through stdout/stderr pipes can leave `communicate()` waiting after the launcher exits; test capture now uses unique files and bounded process waits. An intermediate WMI parent query was removed so readiness uses the application endpoint and no external process inventory. The test-only service on port 5776 was stopped after validating its live application/repository and matching worker log. Old tests completed and cleaned their server; no unrelated process was stopped.

Third run: **4 passed in 19.89s**. Fourth run also invokes the actual CMD wrapper from a different directory: **4 passed in 19.87s**. Covers proxy-free health, repeat/concurrent reuse of one service, foreign repository listener survival, and controlled exit-code-7 startup failure with a spaced repository path. Ruff format/check passed. Browser-opening itself is disabled with `-NoBrowser` for tests.

Timeout regression found native `taskkill /T` was denied by the sandbox and left the test-owned sleeping child alive; that command was removed. Failure cleanup now uses built-in `Add-Type` and Windows ToolHelp32 parent IDs, only for children of the still-live helper whose process handle this launch holds. No WMI, cached PID cleanup, package install or unrelated process kill is used. Killing a venv child can also exit its redirector; this race is handled without replacing the original startup error. The dedicated 15-second unresponsive-helper regression passed in **19.02s**, confirming the child was no longer alive and no ready state was written.

Final command: root `.venv/Scripts/python.exe -B -m pytest tests/test_workspace_launcher.py -W error --basetemp=<root>/.cache/pytest-runs/workspace-launcher-worker-final8 -o cache_dir=<root>/.cache/pytest-runs/workspace-launcher-worker-cache8` from the worker directory — **5 passed in 40.31s**. Ruff formatting and lint passed. All five scenarios use real Windows PowerShell 5.1 processes; first startup goes through CMD. The 15-second readiness deadline excludes foreground setup and failure cleanup (measured total timeout failure below 25 seconds). Project logs/PID state stay under `.cache/workspace`; paid API calls: zero.

## Acceptance

- Double-click CMD from any current directory opens the existing workspace.
- `-NoBrowser -Port <free-port>` starts one healthy matching repository server; repeated/concurrent launch returns the same PID.
- A foreign listener causes a visible actionable failure and remains alive.
- Startup failure refers to project-local logs; only a helper spawned by the failing invocation may be stopped.

## Resume

Worker implementation and owned verification are complete. Commit only the four owned paths, then freeze this worktree. Root integrates the change and updates shared handoff/feature evidence. The default CMD launch opens the browser; `-NoBrowser`, `-Port` and optional `-Repository` support bounded local validation. Missing `.venv` requires the documented isolated setup first; this launcher intentionally does not install dependencies or run analysis. The integrated server must include the health endpoint with parentPid; an older listener on the same port is reported without being stopped.
