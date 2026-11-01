# 多工具开发与交接协议

适用于 Codex、Claude Code、Grok Build 及以后接入的开发 Agent。本文只管交接、并行和费用边界；与根目录 `STATUS.md`、`AGENTS.md` 冲突时以它们为准。

## 共享记录

默认只读；只有出现里程碑、阻断或人工事项变化时，才写对应文件。

| 记录 | 用途 | 何时写 |
| --- | --- | --- |
| `STATUS.md` | 唯一当前状态与主指标 | 里程碑或会话结束时更新一次 |
| `HANDOFF.md` | ≤5KB 覆盖式接手摘要 | 会话结束时覆盖，不堆历史 |
| `docs/exec-plans/journeys.json` | 端到端流程（主指标） | 真实跑通或你亲自试过之后 |
| `feature_list.json` | 功能 ID 与验收 | 集成负责人在有证据后更新；harness 工作不翻转 `passes` |
| `docs/exec-plans/progress-board.md` | 51 项看板 | 仅计数变化时；数字取自 `python -B scripts/status.py` |
| `docs/exec-plans/human-inputs.md` | 需要用户操作的事项 | 新触发或状态变化时 |
| `docs/exec-plans/tech-debt.md` | 技术债 | 新债或状态变化时 |
| `docs/exec-plans/sprint-*.md` | 里程碑或跨会话任务的计划与证据 | 只用于里程碑、阻断或跨会话工作 |
| `docs/exec-plans/assignments.md` | 并行任务归属 | 仅在多个写者并行时 |
| `progress.md`、`docs/archive/` | 历史 | 只读，不追加 |

不要：每次改动都同步多份文档；为记录提交号或推送结果单独开文档提交；用文档数量代替功能进展。

## 开始一个会话

1. 确认仓库或分配的 worktree，看 `git status` 和最近几条提交。
2. 读 `STATUS.md`，再读 `HANDOFF.md`；需要时再按 ID 查 `feature_list.json` 或点名的 sprint。不默认打开 progress、assignments 或归档。
3. 需要环境时跑 `./scripts/init.ps1 -CheckOnly`。
4. 直接做已授权的本地任务；不自动重启历史上暂停、未授权、付费或待标注的工作。

## 测试分层

1. 迭代：`./scripts/test-affected.ps1`，只跑受影响的测试；默认排除 browser 和 local_data 标记，改了 UI 会自动带上 browser。
2. 里程碑结束或合入前：`./scripts/verify.ps1`，跑全量。
3. 分发前：`./scripts/verify.ps1 -Release`，额外做两次可复现 wheel 构建。

已知失败用 `@pytest.mark.xfail(strict=False, reason="TDxxx")` 隔离，并登记技术债；不要靠人工每次比对“是不是还是那几个旧失败”。

## 向用户汇报

- 仅当 `STATUS.md` 主指标相对上次汇报有变化时才汇报：中文不超过 150 字，附一个可以打开的产物路径。
- 需要用户标注、授权或手工操作时，立即用通俗语言提醒，并记入 `human-inputs.md`；同一待办不反复催。

## 停止与落盘

- 会话或里程碑结束时更新 `STATUS.md`；需要接手时覆盖 `HANDOFF.md`。
- 记录写在提交信息里：改了什么行为、用什么验证。未验收的功能保持 `passes: false`。
- 推送失败时如实说明本地提交未同步。

## 并行开发

- 只有同时写入时才建 worktree，放在 `.worktrees/` 下，同时活跃的写者不超过 3 个。串行工作复用当前树。
- 集成后执行 `git worktree remove`。删除前先移除 `.tools` junction，不要把整棵树当备份。
- 只读借用主树 Python 时，加载主树的 `env.ps1`，不要执行 `uv sync`；要写入时用该 worktree 自己的 `env.ps1`。

## 费用与边界

- 每月 ¥50 预授权，只用于你指定的素材；超出部分每次单独询问。
- 硬发送门禁保留；证据和账本不可修改；不自动重付，不自动重标。
- 冻结项、解冻条件和各项状态，以 `STATUS.md` 为准。
