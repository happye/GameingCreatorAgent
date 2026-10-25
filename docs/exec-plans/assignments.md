# 当前分工与恢复入口

最新：固定28.5秒单帧已按新¥0.50许可唯一发送并发布，估算¥0.001492，922旧文件不变；本地resume零发送、查询正例1／跨衣物负例0，原Sol/high最终PASS。见[sprint-static-observation-pilot.md](sprint-static-observation-pilot.md)。TD006自动映射已由同一workspace的原DSH会话完成并验收；原Luna/high地图与Sol/high合同审阅完成，Codex合同／公共文档及正式检查，DSH唯一源码写者，无新录像请求。

更新：2026-10-24，main。[本轮生成sprint](sprint-static-observation-generation.md)已离线交付；[HANDOFF](../../HANDOFF.md)是最新恢复入口。旧阶段见[接续清单](report-2026-10-24-dsh-resumption.md)及[历史分工](assignments-history-2026-10-22.md)。

发布节点：TD006源码／报告c8b9667已普通push成功，远端e9361e2→c8b9667；真实试验报告9e8e525和发布记录0790976亦已同步，旧网络失败不再阻塞。12个已验源码／测试blob与提交一致；当前无DSH watcher或产品源码写者。下一优先工作台已复现可靠性边界，再回真实质量路径。

后续文档23a812e及本发布记录本地保存：第二次普通push连接GitHub:443失败，远端源码已确认c8b9667，不循环重试，后续实质交付时补推文档。

| 工作 | 负责人／范围 | 当前状态 |
| --- | --- | --- |
| TD005详情提速第A步 | 设计工作流（3方案／2评审／综合）；Claude Code主控实现与测量；code-quality-guard（opus）审查 | 2026-10-25完成（dae34f4）：哈希3→1次，15分钟打开约1.7→1.0秒；见sprint-inspect-integrity-single-pass.md |
| MKV目录扫描、容器时钟测试、TD011、报告改写、TD013续跑 | Claude Code主控实现；工作流：后续工作扫描排名（sonnet×3＋排名）、TD013 code-quality-guard（opus）对抗审查 | 2026-10-25完成并分别提交（fd23ce3／e2bc6b5／4268c7b及TD013提交）；见tech-debt TD002／TD006／TD011／TD012／TD013 |
| TD012并发路径解析与POST重置 | Claude Code主控实现；工作流：4扫查＋每候选3票核实、code-quality-guard／gc-reviewer独立审查两轮（opus／sonnet） | 2026-10-25：389项387passed／2skip；两P1已修；见tech-debt TD012 2026-10-25段 |
| TD002 MKV／WebM逐包补探测；TD005真实长素材实测 | Claude Code主控实现／实测；code-quality-guard（opus）只读评估 | 2026-10-25完成：94passed、评估PASS（两P2已修）；见tech-debt TD002／TD005及media-processing.md |
| TD012媒体准备路径误拒（并发删除时路径解析） | Claude Code主控单Agent | 2026-10-25完成：稳定复现＋`lstat`修复，22passed；见tech-debt TD012 2026-10-25段 |
| 正式检查门禁恢复（TD015／TD016） | Claude Code主控单Agent | 2026-10-24完成：静态门禁通过，全量3440 passed不再挂起；联合检索回归修复并实跑；见sprint-verify-gate-restore.md |
| 验收流程浏览器走查与提示改进 | Claude Code主控单Agent | 2026-10-25完成：八步走通，关联原因与阻断中文化；相关测试通过 |
| 冻结时自动盘点 | gc-coder（sonnet）隔离worktree实现、gc-reviewer（sonnet）只读评估；主控合入／小修／真实验证／提交 | 2026-10-24完成：214＋40passed、评估PASS；见sprint-freeze-auto-inventory.md |
| 盘点识别黑边与镜像（source-inventory-v2） | gc-coder（sonnet，86条回复核实）实现；gc-reviewer（sonnet，42条）只读评估；主控真实验证／文档／提交 | 2026-10-24完成：214passed、评估PASS；见sprint-inventory-crop-mirror.md |
| 冻结计划绑定素材盘点（freeze-v2） | gc-architect（opus）设计、gc-coder（sonnet，转录核实）实现、code-quality-guard（opus）评估；主控真实试跑／文档／提交 | 2026-10-24完成：326passed，评估PASS；见sprint-freeze-source-inventory.md |
| 素材来源盘点与共用画面检测 | 主控合同／真实运行／文档／提交；gc-coder（sonnet，转录核实）写三源码＋CLI子命令＋测试＋脚本＋指南；gc-reviewer（sonnet）只读评估 | 2026-10-24完成：52passed、实跑17素材、评估PASS；见sprint-source-footage-overlap.md |
| 工作台状态文件并发替换修复（TD012子项） | Claude Code主控单Agent写两源码／三测试；code-quality-guard（请求opus）独立评估、替换站点扫描（请求sonnet）均只读 | 2026-10-24完成：扩展129passed，评估PASS；见sprint-workbench-status-replace-race.md |
| 单注册帧生成、专属授权、一次发送与本地恢复 | DSH唯一写六源码／三测试；Codex合同／正式检查／docs／Git | 两请求COMPLETED；159passed／1权限skip、静态、包通过，无活跃源码写者 |
| 接口定位 | task_explorer，gpt-6-luna/high，只读 | 已完成，实际型号核实，未重复委派 |
| 合同及费用／持久化／并发／部件语义评估 | 唯一task_quality_guard，gpt-6.1-sol/high | 五项首轮FAIL后同角色复核PASS；不叠普通reviewer |
| 真实单帧试验 | Codex唯一生产执行；原Sol/high同一评估者 | 一次／一帧完成，估算¥0.001492；本地恢复／另进程查询PASS，额度次数已用尽 |
| TD006特殊源时钟自动映射 | DSH唯一源码写者；Codex验收／docs／Git；原Luna/high只读与同Sol/high独评 | 四请求COMPLETED；256passed／0skip、静态／原包复用与R1–R8 PASS；无watcher／源码写者，无新录像API |
| 已有人工参考与已存候选来源对齐 | 原Luna/high只读、Codex持久结果 | 10有效参考只对应钟馗failed run；32旧排名均异源，无同源Completed可作覆盖投影，不放宽资格 |
| 独立静态声明导入／检索 | 前轮DSH、Codex及唯一评估 | 81216a5已交付；202passed／1skip；本轮旧store／matcher保持 |
| TD014／TD006／已有细节排名 | 原DSH与Codex | 各已交付；TD006实证Chromium／MP4非零／异步自动映射亦通过，广泛兼容仍待验 |
| 长钟馗与已存人评／素材 | 原工程结果与用户既有输入 | 269成功／3缺口、469观察及费用保存；12标注／纠正、6新增素材保留，不重做 |
| F006/F009/F010真实质量 | Codex协调；真人真实判断 | 尚未通过；旧待核画面不催，依赖只阻断相应质量步骤 |

同workspace f4395711-a8fb-49a3-ad95-7305ce9ea1e8；当前已交付task gamingcreator-static-generation-20261024／session codex-d988fa9d-3d21-4604-b2f2-26c5b46d9d90。旧静态task STOP_PENDING保留，当前无轮次／队列，不重投或再次cancel；其它历史任务不恢复成新写者。工程DSH模型用量关联partial，费用未知，与录像API旧账分开。

真实试验已完成，不重发同proposal，不借¥0.50剩余额度追加请求。TD006实证切片已交付，下一回原真实质量路径；F006/F009/F010保持false，原人工质量待办仅阻断依赖步骤。
