# Claude子Agent按能力分工

2026-10-24由Claude云端会话接入（会话配置型号claude-opus-5-5）。依据用户要求：照搬用户另一项目“暮云思辨投资助手”的`.claude/agents`九角色结构，按本项目事实改写；并与用户可移植技能harness-project-init的Claude预设（定位／进度haiku、开发／审查／规划sonnet、关键边界与复杂设计opus）一致。共享规则仍在`AGENTS.md`与[多工具协议](agent-workflow.md)；Codex型号与TOML见[Codex指南](codex-agent-routing-guide.md)，两边名字不能互相传递。

## 角色、型号与Codex对应

| Claude角色（`.claude/agents/`） | 型号 | 职责边界 | 对应Codex角色 |
| --- | --- | --- | --- |
| `gc-explorer` | haiku | 只读定位代码／文档／进度，返回file:line | task_explorer |
| `task-progress-monitor` | haiku | 只读跟踪后台长任务，不重启／不重投 | task_progress_monitor |
| `gc-runner` | haiku | 按工单跑测试／检查命令并压缩结果，不改源码 | （新增，Codex由主控直接执行） |
| `gc-commander` | sonnet | 只读：写sprint合同与工单，交主控持久化并派发 | harness_planner |
| `gc-coder` | sonnet | 在明确文件归属内实现并跑定向测试，不提交 | task_developer／harness_generator |
| `gc-doc-writer` | sonnet | 按工单更新sprint／交接／指南／人工待办 | （新增，Codex由主控直接写） |
| `gc-reviewer` | sonnet | 普通diff审查与合同评估，给PASS／FAIL／UNVERIFIED | task_reviewer／harness_evaluator |
| `code-quality-guard` | opus | 费用／授权／持久化／并发／身份／源时钟等关键边界的唯一评估者 | task_quality_guard |
| `gc-architect` | opus | 只读复杂设计与权衡，已有方案不重设计 | task_architect |

主模型保持用户在客户端的选择，不写入项目设置；项目不提交`.claude/settings.json`。个人覆盖放在被忽略的`.claude/settings.local.json`。

## 使用规则

- 简单步骤由主控直接做并记为单Agent；只有能减少主上下文或需要独立验证时才委派。最多同时3个子Agent，不递归派单，不重复审查（gc-reviewer与code-quality-guard二选一）。
- 关键里程碑仍按[Planner→Generator→Evaluator](development-agent-pipeline.md)：gc-commander（或主控）写合同 → 主控派gc-coder在归属文件实现 → 主控派gc-reviewer或code-quality-guard独立评估 → 主控持久化报告、同步HANDOFF／progress／assignments并提交。子Agent不再派子Agent，与暮云原版commander可派单不同，这里与Codex harness_planner保持只读一致。
- 写任务必须给出文件归属并声明“你不是唯一开发者”；其他工具（如Codex原生DSH）有活跃写者时，不派重叠文件，不在同一工作目录并行写。
- 任何子Agent都不得发送真实录像／图片、调用付费Provider、预留预算或代填人工判断，除非工单附带用户对具体提案的明确授权。

## 当前会话如何立即使用

Claude Code只在会话启动时发现`.claude/agents/`；文件写入后不会热刷新当前会话的角色清单。会话未识别这些角色时（例如云端会话的工作目录不是本仓库根），使用内置`general-purpose`类型并**显式传入同表型号**（haiku／sonnet／opus），把对应角色文件正文和最小任务上下文（目标、文件、约束、验收命令）放进提示词；不fork整段历史。新会话从仓库根启动后可直接按角色名委派，例如“用gc-explorer定位源时钟换算入口”。

这种回退**不执行角色文件的tools白名单**：general-purpose可写文件、可跑命令。只读角色必须在提示词写明“只读、不改任何文件”，并要求末行回报`ROLE-CHECK`；主控在子Agent结束后用`git status`核对确未写入。

只有实际执行记录能证明型号。Agent工具的返回结果不直接显示型号；用该子Agent运行转录里的`model`字段核对（只grep该字段并计数，不整文件读取以免撑爆上下文），未能核实时如实记为“请求了X型号，执行记录未核实”，不按子Agent自报判断。

## 本次验证

- 配置：九个frontmatter由主控用临时Python脚本解析（不入库）：name等于文件名且为小写连字符，model∈{haiku,sonnet,opus}，只读角色无Edit／Write。
- 实际执行（2026-10-24云端会话，general-purpose回退＋显式型号）：一次gc-explorer只读定位任务，转录记录26条回复均为`claude-haiku-5-5`；一次gc-reviewer只读评估，23条回复均为`claude-sonnet-5-5`。两者结束后`git status`显示无子Agent写入。型号取自运行转录的model字段，不是子Agent自报。
- 评估发现的8项（CLAUDE.md删句、commander可派子Agent、回退不执行白名单、角色缺先读AGENTS.md、monitor默认长轮询等）已在同一轮修正，详见[接入sprint](../exec-plans/sprint-claude-harness-adapter.md)。
- 未验证：opus角色尚未实际派发；Windows本机Claude Code按角色名的原生发现尚未实测，首次使用时用`/agents`确认列表后补记。配置选择不代表节省比例或内容质量通过。
- 2026-10-24本机Windows Code会话：角色提交合入main（cherry-pick为e8a0b07之后），本会话启动时工作树尚无`.claude/agents/`，可用类型列表未出现gc-*角色，符合“只在启动时发现”；下次从仓库根新开会话后用`/agents`确认九个角色并补记结果。
