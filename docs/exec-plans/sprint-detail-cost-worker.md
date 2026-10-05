# 精分析只读费用历史

Owner：Codex detail_cost_history；2026-10-06；独立工作树 `.worktrees/detail-cost-history` / `codex/detail-cost-history`。

独占文件：`infrastructure/detail_cost_history.py`、`tests/test_detail_cost_history.py`、本文。root 负责服务、HTTP、页面和公共交接；其他工作树冻结，未回写。

## 实现与接口

`refinement_cost_history(project: Path, run_id: str) -> dict[str, object]` 读取已保存精分析尝试和同项目共享预算，不访问 Provider、网络、SQLite，也不创建目录或锁，不执行恢复、结算或发布。

输出 `schemaVersion=detail-refinement-cost-history-v1`、`runId`、`currency=CNY`、`summary`、`sharedCommitment`、`attempts`、`totalAttemptCount`、`attemptsTruncated`。两个摘要都包含 `knownEstimatedCostCny`、`unknownCostCount`、`unknownReservedCny`、`commitmentCny` 和 `attemptCount`；共享摘要增加 `scope=project-detail-refinements`、`runCount`、`budgetCount`。这里只统计精分析，不混合基础 vision 或跨项目费用，不宣称账单已确认。

按已有 `_charges` 的全部预算目录和全部 run 恢复只读承诺；同一次 planned/settled 只计一次，合法相同重复不多计，重复归属或结算冲突明确拒绝。planned 已写而 ledger 未写仍保留 unknown。result 已写但 ledger 未结算时，v2 metadata 可显示记录的估价，`settlementPending=true`，摘要继续保留 unknown 预留，读取不会修复账本。legacy 保留缺失 metadata 为 null；legacy 未结算保留预留，不生成 usage、模型或 request ID。缺少旧预算归属保留 `budget.interrupted`，不能当零。

attempt 白名单为请求哈希、attemptNo、budgetId、status、errorCode、reservationCny、estimatedCostCny、settlementPending、legacy 和 metadata。metadata 仅包括 Provider/模型/版本、request ID、usage、elapsedMs、受控价格时段和合法 UTC 请求时间。原始 execution_details、响应、提示词、payload 和任意模型文本均不输出。

请求 canonical 不含 eventId，因此只直接核验已冻结 candidate、interval、evidence、配置与 prompt 身份，不重建缺失 ID，也不发明新的 canonical。沿用 `_loads`/`_strict_json`/`_confined` 的 JSON、文件大小和边界检查。所有损坏和路径错误均只读失败。最多显示 200 次尝试；两个摘要始终覆盖全部记录，明确给出总数和截断标记。响应最多 1MiB，尝试数量与金额表示均有边界。

## 验证

先 `scripts/init.ps1 -CheckOnly`：11 项 scaffold 通过。工具仅复用 root `.venv/Scripts/python.exe -B`，进程 `PYTHONPATH` 指向 own `src`；pytest、Ruff、mypy 缓存和 basetemp 位于 own `.cache`，无安装和配置修改。

最终联合命令：

```powershell
G:\Tools\ChatGPTRepo\GameingCreatorAgent\.venv\Scripts\python.exe -B -m pytest tests/test_detail_cost_history.py tests/test_detail_budget_sidecar.py tests/test_detail_recovery.py tests/test_architecture.py --basetemp=.cache/cost-history-regression -o cache_dir=.cache/cost-history-pytest-cache --tb=short
```

结果 **71 passed / 0 skip，7.75s**，其中新增 40 项。覆盖 unknown/已知零、失败与取消、planned 无 ledger 崩溃、result 未 settle、跨 run/多预算与重复结算去重、legacy 不完整、截断完整汇总、所有成功/失败读取零写入、损坏 JSON/身份/费用/载荷、非法 run 和真实 Windows junction 拒绝。Ruff 格式和 lint 两个 own Python 文件通过，模块 strict mypy 通过。

真实只读检查：`artifacts/demo-phase0` 的两个授权历史 run 分别返回精分析估价 `0.008513`、`0.00999312`；同项目共享估价 `0.01850612`、unknown 0、2 attempts / 2 runs / 1 budget。读取前后 **15 个侧车/账本文件 SHA-256 相同，新增 Provider 调用 0**。这些是模型费用估价，旧漫画基础 vision 未知预留仍由原账本独立保留。

首次回归正常请求读取失败于误用不存在的 canonical eventId；已按直接身份校验修复并完成上方最终回归，没有补写真实记录。根服务/HTTP/浏览器与完整 verify 由 root 集成后执行；本文不能替代人评质量门槛，F006/F009/F010 仍未通过。
