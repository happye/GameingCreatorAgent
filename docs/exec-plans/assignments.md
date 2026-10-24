# 当前分工与恢复入口

更新：2026-10-24，main。[本轮生成sprint](sprint-static-observation-generation.md)已离线交付；[HANDOFF](../../HANDOFF.md)是最新恢复入口。旧阶段见[接续清单](report-2026-10-24-dsh-resumption.md)及[历史分工](assignments-history-2026-10-22.md)。

| 工作 | 负责人／范围 | 当前状态 |
| --- | --- | --- |
| 单注册帧生成、专属授权、一次发送与本地恢复 | DSH唯一写六源码／三测试；Codex合同／正式检查／docs／Git | 两请求COMPLETED；159passed／1权限skip、静态、包通过，无活跃源码写者 |
| 接口定位 | task_explorer，gpt-6-luna/high，只读 | 已完成，实际型号核实，未重复委派 |
| 合同及费用／持久化／并发／部件语义评估 | 唯一task_quality_guard，gpt-6.1-sol/high | 五项首轮FAIL后同角色复核PASS；不叠普通reviewer |
| 真实单帧试验 | Codex本地prepare；用户决定具体新费用许可 | 28.5秒单帧proposal已冻结，零发送；未授权，不重跑旧任务 |
| 独立静态声明导入／检索 | 前轮DSH、Codex及唯一评估 | 81216a5已交付；202passed／1skip；本轮旧store／matcher保持 |
| TD014／TD006／已有细节排名 | 原DSH与Codex | 各已交付，报告和验证保留；特殊源时钟非零自动映射仍后续 |
| 长钟馗与已存人评／素材 | 原工程结果与用户既有输入 | 269成功／3缺口、469观察及费用保存；12标注／纠正、6新增素材保留，不重做 |
| F006/F009/F010真实质量 | Codex协调；真人真实判断 | 尚未通过；旧待核画面不催，依赖只阻断相应质量步骤 |

同workspace f4395711-a8fb-49a3-ad95-7305ce9ea1e8；当前已交付task gamingcreator-static-generation-20261024／session codex-d988fa9d-3d21-4604-b2f2-26c5b46d9d90。旧静态task STOP_PENDING保留，当前无轮次／队列，不重投或再次cancel；其它历史任务不恢复成新写者。工程DSH模型用量关联partial，费用未知，与录像API旧账分开。

下一按[单帧提案](../../artifacts/dsh-static-generation-20261024/real-single-frame-proposal.json)的具体新授权决定是否做一次真实接受性验证；未批准前不发图、不修改真实静态账本。现有授权内独立离线工作可继续，F006/F009/F010保持false。
