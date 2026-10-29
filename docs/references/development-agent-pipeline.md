# 开发 Agent 的规划、生成与评估

2026-10-11补齐初始化缺口；此为开发协作，区别于产品后续的 Creative Planner。
本文件开篇记录当时的模型分工配置补齐；“录像项目暂停”属于该历史节点。当前开发状态以HANDOFF及其接手清单为准，不据历史暂停停止已授权工作。

## 为什么原来没有固定三 Agent

初始化提交 `fdf19d3` 创建了规格、进度和 sprint 模板，但没有原生 Agent 配置；当时
Codex 工作流明确允许单会话分开规划与检查、无需多 Agent。之后的分工／独立审查属于
按任务委派，不是固定 Planner → Generator → Evaluator 链路。2026-10-11提交
`63534d1` 才增加真实六个任务角色及模型分工。因此原技能的 Stage 3 在本项目只落实
成流程，未完整落实原生三角色；Git 不能证明当时隐藏的取舍原因，不能笼统说技能完全失效。

原模板要求200+特性，与本项目冻结 Phase 0 范围冲突；这需要裁剪模板，不构成省略开发
三角色配置的理由。2026-10-30用户已明确批准全产品并行开发，Creative Planner等实现按ADR-003推进；质量门只约束对应验收/发布。

## 本次补齐与运行规则

新增项目原生 `.codex/agents/harness_planner.toml`、`harness_generator.toml`、
`harness_evaluator.toml`，均 Sol/medium。既有六角色、默认 Luna/medium、并发上限、
父模型和费用状态保持。普通规划使用平衡模型；复杂设计才按已验证路由使用 Architect。

关键交付按依赖执行：
1. 主控或 Planner 形成已有 sprint 合同：范围、owner、可验证效果和依赖。
2. 一个独立 Evaluator 对齐验收；同一角色可随后评估，不追加重复 reviewer。
3. Generator 在分配文件实现，按项目规则验证；并行写者使用独立 worktree。
4. Evaluator 对照合同给出通过／失败／未验证，主控持久化并同步进度／交接。

Planner／Evaluator 是只读角色，返回的合同／报告由主控保存。数据／费用／持久化／并发／
身份边界由 `task_quality_guard` **作为本轮评估角色**，不再叠加另一个普通评估者。
简单改动由主控直接完成规划、实现、检查，明确记为单 Agent 工作，避免每轮强启三人。
可复用 task_developer／task_reviewer 承载生成／评估，但记录实际 owner 与型号。

这些文件可供新会话发现，不是常驻服务或自动调度器。当前会话不识别新角色名称时，
使用已支持 default／worker + 明确 Sol/medium + 最小角色任务，按本工具用
`fork_turns="none"`。既有 children 不会自动切换；权限运行时覆盖不能当作沙箱保证。
三新命名角色本轮未执行，不把配置静态验证称为三 Agent 已跑完。当前按任务选模型
已经有效，Luna／Sol／Astra此前均由实际执行记录核实；本轮历史定位与独立审查的型号
亦由本机元数据核实为 Luna/high 和 Sol/medium。

## 通用技能与本轮验证

用户仓库 [harness-project-init](https://github.com/happye/my-skills/tree/main/harness-project-init)
已在远端v2.0上增量合入 [e3ae40a](https://github.com/happye/my-skills/commit/e3ae40ad3303251476f71dc7a6034658e7701443)。
14个文件修改／新增，Stage 7记忆与Stage 8门禁字节保持，仓库其他文件由Git树读回确认不变。
新增已有项目配置模式、自包含Python安装器、跨工具原生适配、真实加载／执行分层验收；
保留主模型和已有设置，拒绝冲突，支持追加工具与原字节备份。技能三份已同步至本机
Codex／Claude／Grok的用户skills目录；不重写三个工具全局模型设置。

13项隔离测试：12通过、1 Windows符号链接权限skip；覆盖重复安装／冲突／备份／失败
回滚／并发变更／CRLF／旧并发cap／追加工具。Skill验证及格式lint通过。隔离Codex
strict-config读取通过并保留父模型；Grok1.0.50真实inspect发现九个具名角色；
Claude2.1.177仅兼容字段检查，未启动Claude或Grok模型任务。新配置的调用可用性仍按
用户账号和实际工具版本核对；不声称实测节省比例。

本机证据在 `.cache/harness-routing-upgrade/`：`publication.json`、`installation.json`、
`client-report.json`、`source-change-manifest.json`及原技能备份；可移植zip同目录。
当前无新素材标注或人工操作需求。后续项目调用“使用 harness-project-init，只配置按
任务能力选择子Agent模型，保留现有规则并验证加载”；持续录像开发仍等用户恢复。
