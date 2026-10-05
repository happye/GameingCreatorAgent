# Errors

## 2026-10-06: GitHub推送连接失败

用户已授权推送codex/visual-details；3b09081正常push在GitHub443连接阶段超时，未成功更新远端。保留23d8422/3b09081本地检查点和任务交接，不将本地提交称为已同步；完成离线开发后用命令级HTTP/1.1正常重试并独立核对refs，不改全局网络配置或强推。

本轮apply_patch多次因末尾混入未核对的占位上下文被原子拒绝，无文件改写。修正为只提交已读取的具体上下文；追加新记录先读取标题，不在批量补丁中保留待填写的hunk。

## 2026-10-05: 组合本地提交与远端push被自动审批拒绝

自动审核明确允许范围清晰的本地提交，但拒绝同一命令向尚未由可信用户内容明确授权的origin推送；整个命令未执行。继续单独保存本地检查点并报告远端未同步，最终请求具体分支/目标授权。不得通过工具切换或间接执行绕过外传拒绝。

后续用户明确允许仅推送codex/visual-details到GitHub既有仓库，普通push成功上传00f2796；紧随ls-remote再次出现443连接超时，推送确认与独立查询结果需分别记录，不把查询失败误报为推送未成功。

## 2026-10-05: 交接哈希应与已保存源码和真实对象复算

生产读取断言沿用旧sprint的requestHash `6e9ee8...` 后失败。只读加载同一个V6事件，用继承检查点16f727f的精分析模块和当前模块分别计算，canonical request逐字段相同，两者hash均为 `229a8bcb9bee1f017854108751d89840f458040fd14cdd3490e5c2fd56d00279`；旧文档值无法复现。修正文档/断言，不改源事件或hash算法。比较证据保存在ignored artifacts/detail-inspection-validation/request-identity-comparison.json。

## 2026-10-05: 精分析的窄身份合同不能破坏旧检查数据

本轮首个检查集成回归出现 19 failed/69 passed/1权限skip（18.42s）：新 fixture 使用 schema1，SQLite 按旧合同省略 base prompt hash，不能假设其会持久化；旧检查 fixture 的事件/证据短 ID 也不符合 actor-details-v1 的局部身份格式。修复方向是新侧车 fixture 显式 schema2/价格身份，旧数据缺精分析身份时返回 unsupported/unverified，保留原展示/检索/篮子，不能改写旧 ID 或放松 domain 合同。后续复测结果见 sprint-detail-inspection。

## 2026-10-05: 沙箱里的 asyncio 回环初始化可能挂起

本轮定向 pytest 在第三项停住，`faulthandler_timeout=20` 定位到 `socket._fallback_socketpair -> accept -> asyncio.ProactorEventLoop`，尚未执行检索逻辑。中断本工具启动的两次测试后，允许本机回环的升级调用 15 passed/0skip（0.75s）；没有真实 Provider 请求。后续 HTTP/浏览器/asyncio 验证使用相同授权，不能通过改产品事件循环或放松测试绕过。初始源码定位沿用 docs 中 `ui/` 简写造成路径缺失；实际路径为 `src/gamingcreator/ui/`，应先用 `rg --files` 定位后读取。

## 2026-10-05: Wait for the selected run, and preserve the workspace CSP

The first real V6 browser report captured the loading option as defaultRunId because it only waited for a nonempty select. The validator now waits for an enabled run/search and populated timeline; the repeated report and fresh production browser both confirmed the V6 default. An ad hoc diagnostic used Playwright wait_for_function and hit unsafe-eval CSP rejection; use the established debugger-evaluate polling helper rather than weakening CSP. Launching the user's browser from the filesystem sandbox failed with Access denied; the authorized escalated Start-Workspace.cmd reused the same owned local service and succeeded. GitHub push still timed out after21s; save local commits and record pending remote synchronization.

## 2026-10-05: Persist worker state before usage exhaustion and distinguish valid segments

The V6 worker exhausted its usage allowance before sending a final report/commit. Its isolated worktree already contained implementation, tests and a sprint note; a fresh worker can continue those exact files rather than restarting. Root checkpoints must include resumable unfinished changes and a concise current HANDOFF, not stacks of contradictory current-status paragraphs. Real V5 twice produced identical start/end clocks in window31.5–35.5; strict rejection is correct. Do not relax the parser or repeatedly spend on the same frozen prompt; qualify multi-frame actions before adding visual detail in a separately fingerprinted revision.

## 2026-10-05: Windows port zero may allocate a browser-restricted port

Merged browser regression failed at page.goto with ERR_UNSAFE_PORT on127.0.0.1:1723; no application JavaScript ran. The shared test fixture now directly reserves a random free port in20000–59999, with bounded collision retries, instead of relying on port0. This only changes isolated test listeners, not Windows configuration. Root verification must rerun; do not claim the initial170passed/1skip/1failure as complete. GitHub push also failed with443connection timeout; local commits are durable, remote synchronization requires a later retry.

## 2026-10-04: Prepare nested pytest directories and deterministic stat fixtures

Resumption targeted pytest used a new nested basetemp whose parent did not exist; create the task-specific parent before running, without deleting another session's cache. A pre-existing same-size mutation test also retained identical mtime on this filesystem; explicitly change only the fixture's mtime to test stat invalidation. Production media cache intentionally relies on stat changes; unchanged metadata is a known limit, not proof of immutable bytes. Grok's v3 schema failure has no raw response, so exact malformed boundary remains unknown; use new versioned frame-alias boundaries and limited numeric diagnostics rather than inventing a cause.

## 2026-10-04: Temporal configuration must be accepted consistently

Initial temporal resumption test failed at storage.invalid_config: the input reader allowed nine-frame v3 but SQLite's independent typed allowlist still limited five and required a prompt hash. Aligned only the new version's constraints and supplied the fixture identity; 39 targeted tests then passed. Use unique pytest cache as well as basetemp to avoid other Windows sessions' locked cache. Diagnostic JPEG extraction also requires explicit full-range pixel format; use the existing media service for production rather than ad hoc FFmpeg flags. No global cache/permissions changes were made.

## 2026-10-04: 排序验收绑定错误的播放片段（已修复）

新增源时间排序后，英文浏览器测试仍把JSON导出第一条当作刚播放的检索第一名，区间断言失败。两种排序是不同合同；测试改为找到实际rank1，保持JSON/CSV的源时间升序断言，随后中英文均通过。暂停待完成play会触发AbortError，UI忽略这种主动中断，避免假故障提示。相关文件：scripts/validate-inspection-ui.py、ui/static/app.js；证据sprint-workspace-usability.md。多文件patch须匹配当前整行文本，不能沿用旧CSS/段落上下文；失败时先确认未部分写入再修补。

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

## [ERR-20261004-004] embedding_cache_replace_winerror_5

**Logged**: 2026-10-04T12:50:00+08:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
Hybrid demo search failed with `embedding.response_invalid` because replacing a stale `.cache/embeddings/*.json` raised WinError 5.

### Error
```
PermissionError: [WinError 5] 拒绝访问。
.cache/embeddings/write-*/vector.json -> .cache/embeddings/<hash>.json
```

### Context
- The computed vector was valid. The failure happened only while writing the cache.
- Same permission family as ERR-20261004-001. The current user cannot delete the locked file.

### Suggested Fix
Ignore `OSError` from the cache write and return the verified vector. Do not delete the locked file with takeown.

### Metadata
- Reproducible: yes
- Related Files: src/gamingcreator/infrastructure/local_embeddings.py
- See Also: ERR-20261004-001

### Resolution
- **Resolved**: 2026-10-04T13:05:00+08:00
- **Commit/PR**: uncommitted
- **Notes**: `embed` now keeps the vector when the cache file cannot be replaced. The demo search then completed. Not promoted to AGENTS.md.

---
