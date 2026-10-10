# 通用模型分工技能与三角色落地

2026-10-11，用户追加配置任务，root负责技能增量合并、本机副本、项目三角色配置及公共记录。录像项目继续暂停；不修改产品范围、人工验收、费用或素材。

合同：回答当前会话是否生效；将按能力选模型整理为可跨项目／工具复用的skill，增量合入用户的my-skills/harness-project-init；核实最初Planner→Generator→Evaluator为何未落地，并补运行配置和真实验收机制。保留远端v2.0记忆与门禁，不以Markdown或自称型号代替执行证据。

分工：Luna/high只读历史定位、Sol/medium一次独立审查；均fresh最小上下文，不给子任务复制整段聊天、不递归、不分配写者。实际模型由SQLite线程记录核实：历史定位01a126ba-9386-7600-bbf3-588252c63d44、审查01a126c7-9e54-7861-8a11-6297c4fe6356。root独占写入并汇总；评估发现有复现证据才修，不跑无关完整游戏测试。

已交付：保留harness-project-init统一入口，新增“只配置已有项目模型分工”和“协作落地审查”模式；Python标准库安装器、可调整型号预设、Codex／Claude／Grok真实角色适配及逐层验证。简单工作由主控直接完成；重大交付依合同规划→实现→独立评估，不强制三模型同时跑。只读角色返回草案，root保存合同／评审。去掉固定200+配额／无条件重置，修正Codex config.json与CODEX.md原生发现表述。

远端实际合并：原main82a90fc→e3ae40ad3303251476f71dc7a6034658e7701443，正常fast-forward／force=false；14个文件修改／新增，原Stage7／Stage8字节保持、其他仓库文件Git树读回不变。github.com Git传输仍不可达，但api.github.com可达且现有凭据有push权；本次仅对用户明确要求的技能仓库用官方Git Data接口提交及读回，不重写录像仓库历史，不展示凭据。远端合并与验证证据见[开发协作指南](../references/development-agent-pipeline.md)。

本机同步：Codex／Claude／Grok用户skills副本全部29源文件一致，48个文件复制，旧副本完整备份在.cache/harness-routing-upgrade/installed-copy-backups/；未改任何工具全局主模型／provider／权限。zip SHA1b8065497d1c3b1227ed3e637e082428f44c4313c304ffe0a7141f984d54cdaa。本项目补三个harness_*原生TOML，既有六task_*、父设置及旧安装脚本保持；共享指南／工具入口持续加载这一流程。

验证：13离线行为项／12passed／1 Windows符号链接权限skip；Skill校验、格式lint通过；Codex0.162.0-alpha.17.2隔离strict-config读取默认并保留父模型，Grok1.0.50真实inspect发现九个具名角色，Claude2.1.177兼容frontmatter核对。本轮未对Claude／Grok或三个新harness_*发推理；不声称全角色执行、自动热加载或省额比例。运行时配置与新skill发现分层说明，当前聊天仍可用明确spawn型号立即工作。项目三个新TOML／18个示例Markdown frontmatter及UI YAML解析通过；911旧项目文件／39外部保护逐字节核对通过，F006／F009／F010false保持。

独立审查修正：旧并发cap保护；第二工具追加；CRLF重复安装；并发删除后的失败回滚；只读角色持久化归属。最终限范围复核无新发现。中间Windows默认GBK检查失败改UTF-8运行；fixture项目未受信任按运行时说明在隔离HOME核对标准路径，不改真实信任；GitHub文本传输将CRLF规范为LF，读回按实际上传内容核实，没有重复发布。

通俗汇报见[本次报告](report-2026-10-11-harness-routing-skill.md)。当前无新人工操作／标注需求，0 DeepSeek、真实画面发送、新费用预留或业务数据更改。下一步：以后其他项目调用统一skill安装并核对自己工具可用型号；录像主线等用户恢复后按原计划接续，关键交付按新协作流程、小任务直接完成。录像分支之前待普通push状态单独保留；技能仓库已合并不表示录像分支已发布。
