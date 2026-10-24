# Sprint：Claude Code原生子Agent接入与云端会话接手

## Assignment

- Tool/session owner：Claude（主控claude-opus-5-5，云端Linux会话，链接用户Windows机器的文件桥）。单Agent实施；两个只读子Agent用于实际执行验证。
- Branch and worktree：云端独立克隆`claude/harness-adapter`，基线为本机main `0790976`（本机两次未推送提交已按Git对象逐个重建，哈希一致）。不写本机工作树。
- Owned files：`.claude/agents/*.md`（新增9个）、`docs/references/claude-agent-routing-guide.md`（新增）、`CLAUDE.md`、`docs/references/agent-workflow.md`、本sprint。
- Shared files requiring integration：`HANDOFF.md`、`progress.md`、`docs/exec-plans/assignments.md`在本机有Codex TD006进行中的未提交修改，本轮不改，待TD006由集成负责人收口时一并同步。
- Dependencies：无源码依赖。`AGENTS.md`在TD006合同受保护清单内，本轮保持字节不变。

## Proposal

- 用户可见结果：Claude Code在本仓库有与Codex同等职责的九个原生角色，按任务能力选haiku／sonnet／opus；新会话可直接按角色名委派，当前未识别角色时按指南显式传型号。
- 依据：用户要求照搬“暮云思辨投资助手”`.claude/agents`；用户可移植技能harness-project-init的Claude预设（定位／进度haiku，开发／审查／规划sonnet，关键边界／复杂设计opus）。
- 验收：九个frontmatter可解析、name等于文件名且为小写连字符、model∈{haiku,sonnet,opus}、只读角色无Edit／Write；指南给出与Codex角色的对应；规则不与AGENTS.md冲突；无源码变化；实际派发至少一个haiku与一个sonnet只读任务并核对执行记录。

## Review before implementation

- 当前阶段仍为Phase 0；本项属开发协作配置，不改变产品范围、F006门槛或费用授权，不代替主线交付。
- 风险：本机有Codex DSH活跃写者（TD006源时钟自动映射，请求29a141ad仍在写源码与调试文件）；本机Linux工作环境未能启动，无法在本机执行git；GitHub账号未链接到Claude，云端无法推送。
- 决策：proceed，单Agent配置；全部改动只在云端克隆，交付通过GitHub或本机被忽略目录中的bundle，不写本机受跟踪文件。

## Evaluation after implementation

- 配置核对（主控临时脚本，不入库）：9个角色name＝文件名、小写连字符；model为haiku×3（gc-explorer、gc-runner、task-progress-monitor）、sonnet×4（gc-commander、gc-coder、gc-doc-writer、gc-reviewer）、opus×2（gc-architect、code-quality-guard）；只读角色无Edit／Write，gc-commander无Agent工具。
- 实际执行：当前云端会话未发现新角色（启动后写入），按指南用general-purpose＋显式型号派发。gc-explorer只读定位TD006源时钟入口，转录26条回复均`claude-haiku-5-5`，返回的file:line与代码一致；gc-reviewer只读评估本diff，23条回复均`claude-sonnet-5-5`。两次结束后`git status`无子Agent写入。opus角色尚未实际派发。
- 独立评估（gc-reviewer，首轮）：C1 PASS、C2 PASS（P2缺口）、C3 UNVERIFIED、C4 FAIL、C5 UNVERIFIED，共8项。处理：①AGENTS.md不改为有意豁免——它在本机TD006合同`artifacts/dsh-source-clock-mapping-20261024/protected-before.json`的受保护清单内（被忽略目录，仓库内不可见），TD006收口后再加指针；②恢复CLAUDE.md被删的“先核实发现和型号”句；③验证段改为本节实际记录；④gc-commander去掉Agent工具，改为只读返回合同与工单（与Codex harness_planner一致，偏离暮云原版）；⑤指南与CLAUDE.md写明回退不执行tools白名单、须提示词约束并核git status；⑥coder／reviewer／doc-writer加“先读AGENTS.md”，coder补feature_list／人工标签／旧标注保护；⑦task-progress-monitor默认单次检查；⑧本sprint属仓库流程必需文件。修正后未再派第二评估者（配置文档改动，按“不重复审查”）。
- 源码：无变化。功能／质量门：不适用，F006/F009/F010仍false。

## Report to the user after each key change

- 现在能做什么：Claude可以像Codex一样按任务能力分派子Agent——查代码／盯进度／跑命令用便宜的haiku，写代码／写文档／普通审查用sonnet，费用与数据安全等关键审查和复杂设计用opus；角色职责、红线与Codex一一对应，换工具不丢规则。
- 验证程度：配置解析通过；haiku与sonnet各一次真实只读派发，型号由运行记录核实；opus与Windows本机按角色名发现尚未实测。没有改动任何源码或受保护文件。
- 遗留：GitHub账号未链接到Claude，云端暂不能推送；本机Linux工作环境未能启动，暂不能在本机执行git或命令。
- 下一步：推送本分支；TD006请求结束后接手集成（读答复、跑定向测试、独立评估、提交并同步交接文档）。

## Transfer to another tool

- 最后提交：见Git；本分支未合入main前不改变本机工作树。
- 下一步：用户链接GitHub或本机Linux环境可用后推送；TD006请求终态后由集成负责人读取答复、绑定测试计划、独立评估并提交。
