# Live pitfalls (≤15 entries, ≤3 lines each)

Rules for this file:
- Add an entry only when a problem recurs, and only if no script, test or lint rule can prevent it. When it happens a second time, turn it into a mechanism and delete the entry here.
- The full October log (28 errors, 7 learnings) is archived in `docs/archive/history/learnings-2026-10/`.

## Windows and tools

1. **PowerShell double-quoted strings eat backticks.** `` `a `` `` `f `` `` `t `` become control characters; this broke `agent-workflow.md` and 11 other files. Write files with the editor tool, a single-quoted here-string, or Python. CI rejects control characters in docs.
2. **Native stderr under `$ErrorActionPreference='Stop'`.** In Windows PowerShell 5.1, redirecting a native tool's stderr (`2>$null`, `*>`) turns normal output into a terminating error. Redirect inside `cmd /c "... 2>nul"`, or run scripts as `powershell -File script.ps1 > log 2>&1`.
3. **Folders owned by the Codex sandbox account cannot be deleted** by the main user (WinError 5). Do not reuse them; skip them silently. Only the owner, with admin rights, may take ownership of those exact folders. Never reset ACLs on all of `.cache`.
4. **Junctions.** Before deleting a worktree, remove its `.tools` junction. Delete trees with `cmd /c rmdir /s /q`, which does not follow junctions.
5. **Environment.** Dot-source `./scripts/env.ps1` and run from the repo root; otherwise browser tests fail on missing Chromium and static-file tests fail on relative paths. Push through Clash `127.0.0.1:7890` with HTTP/1.1.

## Editing discipline

6. **Read before patching.** 18 October incidents came from guessed paths, anchors or file names. Open the file, or `rg` for the exact text, before editing; never patch from memory.
7. **Run the format, lint and type gates before committing.** On 2026-11-01, minute-by-minute commits left 27 unformatted files, 6 mypy errors and one red test on `main`. `test-affected.ps1` plus `ruff`/`mypy` take about 2 minutes.

## Product truths (verified the hard way)

8. A keyword hit is not an action; read the whole observation text before counting a candidate.
9. Several frames in one window are not multi-frame evidence for a candidate action; temporal claims need ordered evidence.
10. An object held in close-up is not a character; check actor/part bindings.
11. When real-footage retrieval misses, check what the database actually contains before tuning ranking.
12. Strict rejection of identical start/end clocks is correct. Do not relax the parser or pay again for the same frozen prompt.
13. The long Zhongkui run is finished (269 succeeded, 3 rejected). Do not rerun its launchers.

14. **角色重复先核客户端导入记录。** 2026-11-04确认gc-*来自Codex external_agent_config_imports的Claude SUBAGENTS迁移，不凭文件出现就归因模型/提示词；不转换角色，gitignore不能阻止再次导入。

15. **共享venv不改变editable install目标。** 子工作树跑测试必须显式设置PYTHONPATH为自己的src；否则共享.venv会导入主树源码，不能把误跑结果当该树验证。
    `env.ps1`/`test-affected.ps1`也会重设路径；在加载env后再设工作树src，并核对实际导入位置。受影响脚本无法保留该路径时，按其选出的同一清单直接运行pytest，明确记录此差异。

16. **生产 CSP 保持开启。** 2026-11-07真实工作台诊断中，Playwright的字符串 `wait_for_function` 触发unsafe-eval拒绝；改用locator断言等待和CDP函数体读取，不能关闭应用CSP来让诊断通过。测试端口需独占绑定，同一工作树pytest严格串行。

17. **Playwright同步fixture仍运行事件循环。** 测试内不要直接调用内部使用asyncio.run的CreationJobs.edit；通过实际HTTP读取。不能用threading.Event.wait等待依赖route回调的事件，会阻断Playwright分发；用页面/locator的异步等待让事件循环前进。重载测试的localStorage种子仅在key不存在时写入，否则每次reload会覆盖用户刚保存的版本，制造假回归。
