# Codex 子 Agent 分工

项目配置：`.codex/config.toml`（最多 3 个并行子 Agent，未指定时用 Luna／medium）和 `.codex/agents/*.toml`（每个角色一份，只有这一套）。在其他机器上，用 `./scripts/install-codex-agents.ps1` 安装到个人目录；目标已有不一致的配置时，脚本拒绝覆盖。

| 任务 | 角色 | 模型／推理 | 边界 |
| --- | --- | --- | --- |
| 查文件、入口、调用链 | task_explorer | gpt-6-luna／high | 只读，返回短结论和文件位置 |
| 看长任务进度 | task_progress_monitor | gpt-6-luna／low | 只读日志和句柄，不重启 |
| 落实已确认的方案 | task_developer | gpt-6.1-sol／medium | 写明文件归属，只跑相关测试 |
| 一般代码审查 | task_reviewer | gpt-6.1-sol／medium | 只读，有证据才报问题 |
| 费用、持久化、并发等关键审查 | task_quality_guard | gpt-6.1-sol／high | 和一般审查二选一 |
| 跨模块设计 | task_architect | gpt-6-astra／low | 只读，已有方案不重新设计 |
| 里程碑合同、实施、评估 | harness_planner／generator／evaluator | gpt-6.1-sol／medium | 只用于里程碑（`development-agent-pipeline.md`） |

规则：
- 简单的一步操作由主 Agent 自己做；多开 Agent 会多花 token，不要为了并行而拆任务。
- 委派时写明：目标、允许改的文件、验收命令，并告知对方“你不是唯一的开发者”。
- 说某个模型跑过之前，先核实执行元数据；角色文件写好后，要新开会话才会加载。
- Codex 的模型名不是 Claude 的别名。Claude 的角色在 `.claude/agents/`，对应关系见 `claude-agent-routing-guide.md`。
- 2026-10 的安装和验证记录已移到 `docs/archive/`，默认不读。
