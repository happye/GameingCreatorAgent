# 按任务选择子Agent模型

2026-10-11，用户收尾期间明确追加的配置任务；root owns .codex/agents、子Agent默认配置、分工协议和实际验证，不恢复录像项目新开发。前一交付已保存de4f15a，尚待最终普通push。

参考用户指定的两处Claude配置：个人架构／开发／审查／Explore及投资项目质量监督／进度监督。仅移植职责、只读边界与证据汇报，不复制Claude模型别名或投资项目专属规则。

按已打开的[官方子Agent说明](https://learn.chatgpt.com/docs/agent-configuration/subagents)使用独立TOML，name／description／developer_instructions及model／model_reasoning_effort；按[官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)设置agents默认及并发上限。当前本机codex-cli 0.162.0-alpha.17.2，模型缓存与本会话可用列表均含gpt-6-luna／gpt-6.1-sol／gpt-6-astra；缓存仅作候选，实际启动才证明可用。

主要交付：轻任务Luna、实施／审查Sol、复杂设计Astra，六种角色独立职责。新子Agent最小上下文；单步／重复状态不派子Agent，必要时明确升级，不静默借用第三方旧角色。当前会话用明确spawn模型立即执行；本机配置以原生读取／实际运行验证，不靠agent自称型号。新默认只影响以后创建的子Agent，已有角色不热切换。

实现后记录TOML／原生读取、真实子任务及模型执行证据；同步AGENTS／共享协议／工具入口／HANDOFF／分工／progress，保留前一完整检查和费用边界，不重跑无关pytest或发DeepSeek请求。任务结束完成收尾并暂停，等待用户恢复。

已实现／当前验证：个人和项目六角色、默认Luna/medium／并发3、主模型保持；安装脚本保留原config备份和既有角色，重复安装不改已一致文件，追加个人AGENTS规则即时被当前上下文加载。原生strict-config读取默认正确；三实际子任务Luna/high、Sol/medium、Astra/low全部完成，SQLite和turn_context一致且无重路由。当前自定义agent_type首次unknown保留，改明确model/fork none成功；新会话CLI仅启动一次，transport自行断流重试后创建／完成task_progress_monitor并exit0，session1701终结，没有另起进程。CLI ephemeral不存子任务型号，三种型号的执行记录验证来自当前聊天。debug prompt-input未含自定义角色不能证明注册，失败保留。无DeepSeek／新视觉／搜索／费用预留／人评。新增安装验证：首次安装、再执行字节一致、冲突默认拒绝且零写入、个人父配置除agents外等原备份、六副本一致及911旧项目／39保护保持均通过；PowerShell语法通过。接下来仅保存／普通push并按原收尾要求暂停。

发布／收尾节点：源码de4f15a与分工63534d1已本地提交；一次授权普通push于21.121秒连接github.com:443失败／exit128，日志.cache/codex-agent-routing-push.log保留，未重试／远端读取，最后确认远端b232013，本轮待网络恢复后补推。不影响个人／项目配置本机生效。当前功能、验证和人工边界已通俗汇报并同步HANDOFF／assignments／progress；完成本地记录后最后暂停持续开发，不自动继续。

后续2026-10-11用户另行要求跨工具skill及初始化架构核对，已完成[sprint-harness-routing-skill](sprint-harness-routing-skill.md)：技能仓库独立正常合入e3ae40a、本机三技能副本同步，项目补三harness_*角色；上述原六角色与已验证执行事实保持。录像主线仍暂停，原分支发布待办不因另一仓库合并而改写。
