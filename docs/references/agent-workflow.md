# 多工具开发与交接协议

适用工具：Codex、Claude Code、Grok Build 及以后接入的开发 Agent。项目范围、技术决策与验收标准以仓库文件为准。

**冲突优先级（硬规则）**：根目录 STATUS.md 与 AGENTS.md **高于**本文。若本文与 STATUS／AGENTS 不一致（尤其汇报长度、是否齐刷文档），以 STATUS／AGENTS 为准。

## 共享记录及职责

默认：**只读**。仅在有写入权且出现阻断／里程碑／人工事项变化时才改对应文件。

| 记录 | 用途 | 默认 | 何时写 |
| --- | --- | --- | --- |
| STATUS.md | 唯一当前状态／主指标 | 读 | 里程碑或会话结束更新一次 |
| HANDOFF.md | ≤5KB 覆盖接手摘要 | 读 | 会话结束可覆盖；勿堆历史 |
| AGENTS.md、docs/ | 共享规则与规格 | 读 | 规则／规格 owner 才改 |
| eature_list.json | 特性 ID 与验收 | 读 | 集成负责人在有证据后更新；harness 勿翻转 passes |
| docs/exec-plans/progress-board.md | 51 项量化看板 | 读 | **仅数字有变**由集成负责人更新 |
| docs/exec-plans/human-inputs.md | 需用户操作的事项 | 读 | 新触发／状态变化时记一条 |
| docs/exec-plans/tech-debt.md | 债务 | 读 | 新债或状态变化时 |
| docs/exec-plans/sprint-*.md | 单任务计划／证据 | 按需 | 有 owner 的里程碑或阻断时 |
| docs/exec-plans/assignments.md | 并行任务归属 | 按需 | **仅并行写者**需要时 |
| progress.md | 历史流水 | 只读历史 | **日常勿追加**；当前态见 STATUS |

禁止：每次改动七份齐刷；为 tip SHA／推送结果另开文档提交；用文档数量代替功能进展。

## 开始一个会话

1. 在正确仓库或分配的 worktree 启动；看 git status、分支、最近提交。
2. 先读 STATUS.md，再读短 HANDOFF.md；需要时再读 AGENTS.md／eature_list.json／自己的 sprint。勿默认打开 progress／assignments 全文。
3. 需要环境时再跑 ./scripts/init.ps1 -CheckOnly；旧交接里的环境结果不替代当前检查。
4. 直接做已授权本地任务；不从历史「暂停／未授权／待标注」自动重启。

离线主指标：python -B scripts/status.py。

## 向用户汇报（与 STATUS 对齐）

- **仅当 STATUS「主指标」相对上次汇报有变化时**才向用户做进度汇报。
- 格式：**≤150 字中文** + **一个**可打开产物路径。不要把 tip SHA／推送当进度。
- 指标未变：会话内可短确认「无主指标变化」，不要展开成验收长文。
- 需要用户标注／授权时立刻通俗提醒，并写入 human-inputs.md；同一待办不每轮催。

（可选，仅 worker→主控内部提纲，不对用户照搬成长文：现在能做什么／帮助／验证界限／下一步。）

## 主线交付优先

按总方案与当前里程碑推进。小 bug 能直修就修；需多轮试错的记入 	ech-debt.md 后回到主线。勿用连续微修、诊断堆砌或无变化的完整回归冒充进展。费用、发送门禁、冻结（P046–P051／P038，解锁人评为玩法展示）见 STATUS。

## 子 Agent 与模型路由

关键里程碑可用 Planner→Generator→Evaluator（见 development-agent-pipeline.md）；简单工作单 Agent。按能力选模型见 codex-agent-routing-guide.md／claude-agent-routing-guide.md。只读角色不改仓库、不付费、不上传。不递归委派；主控持久化只读产出。

## 停止与落盘

- 默认：会话或里程碑结束更新 STATUS.md；需要接手时覆盖短 HANDOFF.md。
- 有阻断性失败、依赖变更或明确里程碑时，才写／更新对应 sprint。
- 未验收功能保持 passes: false。远端推送失败时说明本地提交与补推，不把未推送说成已同步。

## 并行开发

仅同时写入才建独立 worktree（.worktrees/，勿放 .cache/），≤3 个活跃写者。串行复用当前树；只读不建副本。并行时才维护 ssignments.md。集成后 git worktree remove；整树不当备份。只读借用主树 Python 时加载主树 env.ps1 且勿 uv sync；写入前必须用该 worktree 自己的 env.ps1（见 .learnings/ERRORS.md）。

## 结束与验收

记录验证命令、结果、产物路径与未验证项。换工具不改范围、不降 Phase 0 门槛。F006 固定十槽与人评仍独立；工具通过≠内容理解通过。
