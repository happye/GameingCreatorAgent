# 当前交接：优先修复长钟馗分析中断

2026-10-11。用户将在同一工作区新开对话，要求直接接手。**下一开发为TD007/P1长录像可靠性缺陷；功能尚未修复。** 先读AGENTS.md，再按[接手清单](docs/exec-plans/resume-long-zhongkui-20261011.md)与[开发合同](docs/exec-plans/sprint-long-analysis-reliability.md)直接离线实现，不要求重复批准开发或重新标注。

**停止原因已确认**：第22组第三条事件把起止选成同一源帧，违反多帧动作合同；解析拒绝该事件、窗口返回provider.schema，application/analysis.py将窗口失败抛为AppError并把整任务置failed，CLI退出4。拒绝这条事件是合理保护，局部不合格返回中断整片是必须优先修复的流程缺陷。不是预算用尽；停止后未重试。该问题不能按普通小bug延期。

| 当前事实 | 已核对结果 |
| --- | --- |
| 阶段／分支 | Phase 0，codex/visual-details；F006/F009/F010false |
| 分析项目／run | artifacts/independent-footage-20261011／5c7894aa10e94b8aa82533bd77f9871e |
| 长钟馗来源 | 952.101688秒，source SHA7437abfab778b0f0b6d67efec5f8f80a61e28f9d5bd4ba681908c5f44b9890ac |
| 已保留媒体／分析 | 1903注册图及音轨；21／272窗口完成、1失败、250未执行；19观察／0转录 |
| 执行／费用 | 76.05772秒，22请求／198帧次，全attempt1；估算¥0.10848724含失败¥0.00612692，0新unknown／未结预留 |
| 真人样例 | 10个：boss1／连招5／剧情4；两剑特写已排除、老者理由改正，原根目录JSON保留 |
| 另两录像 | pending／0调用；具体run与源路径见接手清单 |

**下一实际动作**：确认版本化窗口失败策略并实现局部拒绝的隔离／覆盖记录／任务资格；多帧动作保护继续，预算／认证／存储／身份问题继续停止。离线验证前后窗口、费用与unknown、恢复不重发成功窗口、并发及缺口不能冒充Completed。主控持公共记录，落实源码owner后按既定三角色流程作唯一关键边界评估；不用重复评审／无变化完整测试／只改提示词付费试错代替实现。

**仍继续同一长钟馗**：修好后保留原run、媒体、21成功窗口、费用与参考，准备具体续分析方案。新策略若与保存身份不兼容，显式设计关联延续版本，不硬改SQLite配置／旧提示词身份。满足Completed条件后才绑定冻结三查询、生成固定结果并即时提醒真人评分。当前不需补标／评分；样例非全片穷尽，未填及“似乎没有”不当负例，全片Recall未验证，调优后正式验收换独立材料。

**权限与恢复红线**：已批准v2 SHA f608c4dedac69ee261ac56ba110c8446e808bfc533ed26116b568c95fe8c6f6f、最高新增¥5的方案已执行并按失败停止；新策略／付费续跑先有具体新提案，不重提旧批准或把余额当重跑许可。所有旧unknown及已追加账单确认保留。禁止再执行execute-authorized-analysis.py、已完成抽帧／导入／冻结或exclusive检查助手。

**证据与已结束进程**：artifacts/human-reference-pilot-20261011保存授权／启动／终态、execution-outcome-v1、evaluation-execution-final、delivery-execution-report及原日志；原同一guard实际边界PASS只证明授权／费用／身份，分析本身failed。四项边界检查通过不是修复完成。第22原始响应未保存，不猜其余事件有效。句柄91845已结束，PID35160为历史，无后台分析要等，不据旧PID操作进程。

**本轮交接与发布**：本轮只整理记忆／文档，0新模型／代码／测试／Git网络动作。最新HEAD由git读取，最后确认远端f5a3a69898747917d6477d6985efc2593bb14421，本地待普通补推codex/visual-details，不动main／强推；回执.cache/independent-footage-publication.json。当前入口已同步AGENTS、CODEX、CLAUDE、Grok规则及里程碑／进度／人工待办。用户要求关键节点通俗详细汇报、及时提醒人工帮助、持续对齐文档和按能力选择子Agent。

旧完整交接保存在[历史快照](docs/exec-plans/handoff-history-2026-10-11-long-analysis.md)，其中路径按原仓库根目录解释；不按历史“暂停／未授权／待标注”恢复。执行说明见[通俗报告](docs/exec-plans/report-2026-10-11-human-reference-pilot.md)与[原试验sprint](docs/exec-plans/sprint-human-reference-pilot.md)。
