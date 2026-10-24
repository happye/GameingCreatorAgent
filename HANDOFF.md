# 当前交接：验收流程端到端可用，等待用户确认分组与补素材

更新：2026-10-24，Phase 0，main。新准备的两种验收页面，对已验证Chromium／MP4非零PTS及异步音视频可自动换算、取时、定位同规范区间并末停；未知／不支持仍手填。旧页面包、原12标注及纠正保持，不要求重标。见[报告](docs/exec-plans/report-2026-10-24-source-clock-mapping.md)、[sprint](docs/exec-plans/sprint-source-clock-mapping.md)及[当前里程碑](docs/exec-plans/current-status.md)。

## 已交付与验收

- TD006：正式256passed／0skip、九文件Ruff／格式／五源码mypy／三JS语法通过，原Sol/high R1–R8 PASS。实际旧编辑包＋10有效参考经生产CLI复用成功，37保护／922原项目SHA不变。12源码／测试SHA与Git blob前后相同。仅实证范围通过，不是逐帧裁切或通用编码兼容。
- 单注册帧真实试验已结束：原28.5秒图＋parts-v2唯一一次HTTP200，1主体／7typed属性，另进程正例1／跨衣物负例0，本地resume零发送。估算¥0.001492（1016输入／119输出tokens，未核账单）；¥0.50许可的一次额度已用尽，剩余钱不允许追加。run f601fb9b3e734d5ea188fc15c790acbb，attempt205f8efdee85311c7190dfc57bfb4a13。见[试验报告](docs/exec-plans/report-2026-10-24-static-observation-pilot.md)。
- 静态声明导入／parts查询、单帧prepare／具体授权／一次发送／本地resume，以及TD014状态可靠性均已交付；历史证据沿原报告保留。F006／F009／F010仍false，真人准确性未通过。

工作台扩展组原2项失败已修复（2026-10-24 Claude Code）：根因是Windows替换正被读取的状态文件会被拒绝（WinError5），验收流程status.json与素材批量state.json现由进程内锁串行；同组还更新了一条与ce934e0免责文字不符的过时断言。扩展10文件129项全部通过，独立code-quality-guard PASS；整仓verify未重跑，跨进程占用仍归TD012。见[sprint](docs/exec-plans/sprint-workbench-status-replace-race.md)。Claude原生九角色已合入（`.claude/agents/`，见[Claude分工指南](docs/references/claude-agent-routing-guide.md)），新会话需用`/agents`确认发现。

## 2026-10-25验收流程浏览器走查与提示改进（最新，本会话收尾）

内置浏览器用真实素材完整走通`/acceptance`八步（流程“Claude 冒烟测试 2026-10-24（可删除）”）。修复：关联步骤选错用途时原因被吞成“读取失败”（现显示具体原因）；冻结阻断、就绪阻断和“仍待你决定”代码改为通俗中文说明（代码保留括号内）。相关测试通过；就绪中文说明已在主工作台“验收就绪”对话框实际复核显示正确。

**下一会话恢复顺序**：①用户若已确认分组或补了原始游玩录像，先用工作台冻结（默认自动盘点）核对；②否则按technical debt继续离线项（TD012偶发、TD005长素材资源）；③新付费分析须先给具体提案。新会话从仓库根启动后用`/agents`确认9个gc-*角色并补记[Claude分工指南](docs/references/claude-agent-routing-guide.md)。

## 2026-10-24冻结时自动盘点

工作台冻结步骤默认勾选“冻结时自动盘点登记的录像”，CLI为`freeze-benchmark --auto-inventory`／`prepare-benchmark.ps1 -AutoInventory`：不必先单独运行盘点命令，冻结时本机自动比对计划内来源并打包报告，异组共用画面直接给出阻断。真实Atom异组计划12秒被拦；浏览器端到端走查通过，阻断改为通俗中文说明。完整verify 3517 passed（1项TD012偶发）。见[sprint](docs/exec-plans/sprint-freeze-auto-inventory.md)。

## 2026-10-24盘点识别黑边与镜像

`inventory-sources`报告升级为`source-inventory-v2`：自动裁掉均匀黑边再比对，并额外比较左右镜像；冻结同时接受v1与v2报告。真实验证中加黑边与镜像的同源片段由“认不出”变为在正确偏移报告；17素材重跑无新增误报（仍仅Atom PV／实机）。见[sprint](docs/exec-plans/sprint-inventory-crop-mirror.md)。新报告`artifacts/source-inventory-20261024/report-v2.json`。

## 2026-10-24冻结计划绑定素材盘点

新冻结一律为`benchmark-freeze-v2`：`freeze-benchmark --inventory <盘点报告>`（工作台冻结步骤可上传）把报告原样打包并核对每个来源；缺盘点、来源缺失／失败／无法比较、共用画面分到不同组或跨开发／测试都会阻断就绪。v1保持字节不变但不再能给出独立测试集。真实反例（Atom PV／实机异组）被拦下。326定向测试通过、code-quality-guard PASS。见[sprint](docs/exec-plans/sprint-freeze-source-inventory.md)。下一步仍待用户确认分组与是否补原始录像；离线可继续的是F009／F010等不依赖人工的改进。

## 2026-10-24正式检查门禁恢复

`verify.ps1`静态门禁恢复通过；全量不再在20%处挂起（3440 passed，余3项为TD012高负载偶发、单独通过）。修复了已交付功能回归TD016：多录像联合检索hybrid／semantic（含“已有细节”）保存失败，真实数据实跑恢复；三个中文PowerShell脚本加BOM后可在用户本机PowerShell 5.1运行。见[sprint](docs/exec-plans/sprint-verify-gate-restore.md)。下一主线：按[freeze-v2合同](docs/exec-plans/sprint-freeze-source-inventory.md)让冻结计划绑定素材盘点。

## 2026-10-24素材来源盘点

新增只读命令`./scripts/inventory-sources.ps1`：本地探测时长／编码／SHA并检测不同文件间共用画面，不分组、不调用模型。实跑17素材：代号：Atom的PV与实机共用画面（PV晚10秒），Atom录音275秒画面全黑只有声音，新增6个TapTap文件均30–128秒短展示片；可用长录像仅钟馗两段。见[盘点结果](docs/exec-plans/source-inventory-2026-10-24.md)与[sprint](docs/exec-plans/sprint-source-footage-overlap.md)；52项定向测试通过、gc-reviewer PASS。已在[人工清单](docs/exec-plans/human-inputs.md)请用户确认分组、是否补原始游玩录像。另发现main静态门禁失败（TD015），下一步先机械修复并跑一次完整verify。

## DSH恢复入口与加载

- 配置：个人Skill codex-dsh-collab（本轮核最新版SHA c36cc6c2…854a），toolRoot G:/Tools/ChatGPTRepo/codex-dsh-双端联通，stateDir C:/Users/Crux/.codex/codex-dsh-state，native http://127.0.0.1:3080，workspace f4395711-a8fb-49a3-ad95-7305ce9ea1e8。
- TD006 task gamingcreator-source-clock-mapping-20261024／session codex-94269cc4-7c00-4bbe-917e-bdd6205a1a9f。四请求29a141ad／87da2a18／b90f9594／93834a15全部COMPLETED，完整终态报告各按hash读一次；当前无watcher、无源码写者，**不重投**。最终合同v6 `1155ea481af6e9e3507250ddb5b56c8a6b660d87b7ef485dadd4fd512b3c7311`。结果、回执与源码证据在ignored artifacts/dsh-source-clock-mapping-20261024/。
- v2漏登记27个ignored只读条目形成的scope阻断已恢复。隔离工具分支codex/contract-enrollment-20261024提交51f42dd；一次显式baseline-supplement只追加27项，原654条目和Git身份不变，旧资产保留，configured原CLI已正常bind/run。主工具安装仍fc47d97；不手改旧ledger、不移动材料、不另建任务绕门。
- 旧静态task gamingcreator-static-observations-20261023／session codex-35d31548-8d46-4f1b-b8dc-1886e7f8f355：本轮已核running=false、queue0、三请求COMPLETED；STOP_PENDING／STOP_ACTIVITY_UNRESOLVED继续保留。不再cancel、杀共享Host、归档或重发。Skill／手册更新已由CLI当前磁盘导入，不需要重启现有Host。
- 主控额度中断后可从原会话恢复报告；不能承诺停顿期间自动验收／派下一轮。本轮已纠正用旧RUNNING结束监督的问题，单watcher60秒cursor／generation增量，终态及时读一次结果。工程模型用量另存且关联有限，未知费用不补零。

## 保留进度、人工依赖与下一步

长钟馗269成功／3拒绝／469观察保持，原片约15分52秒，842.598秒是续跑墙钟；累计API估算¥1.49022124，本rununknown／预留0，其他未知账独立保留。3缺口仍非Completed；用户选C离线改进，未代选A/B/D，不补窗或重跑成功窗。

已有12标注与用户纠正（10有效：Boss1／连招5／剧情4）、六新增素材全部保留，当前不要求重做或再补文件。只读来源对齐证明10正例对应钟馗failed／coverage_gap，32旧排名均异源，无同源Completed可作有效覆盖投影。F006须原来源独立性／事前参考／明确Completed绑定／固定Top10人评；原v5画面对错按“稍后核对”留空。

工作台可靠性已处理；下一回原真实质量计划，复用已有资料；仅在实际触发来源确认、新参考或具体新费用提案时按[人工清单](docs/exec-plans/human-inputs.md)提醒，不重复催同待办。不转入后续成片／正式桌面／商业阶段。发布状态另见本文件末尾及本机publication.json，不能从旧网络失败推定当前远端。

发布：功能／报告提交`c8b9667`已普通push成功（origin/main从e9361e2更新到c8b9667），此前单帧试验文档9e8e525和0790976亦已同步。25文件保存，12个已验源码／测试Git blob与最终提交一致，工作树干净。此前GitHub连接失败为历史，不是当前阻塞；隔离工具修复51f42dd仍仅本地工具分支，未合入主工具安装。

后续发布状态：补记上述成功事实的文档提交`23a812e`第二次普通push遇GitHub:443连接失败；该文档及本条记录本地保存，未称远端已同步。远端已确认源码仍c8b9667，功能和验收不受影响。本节点不再push；后续有实质交付时一起普通补推，不能据网络失败重跑DSH／旧录像任务。
