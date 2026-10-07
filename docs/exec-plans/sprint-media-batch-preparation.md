# Phase 0 多素材批量离线准备与逐任务续跑

2026-10-07，root / Codex，codex/visual-details，接06394ae。上一原排名计分已交付、完整2095／1权限skip，属于progress；旧worker／worktree冻结，顺序单writer。

F002／F004主交付：一次提交有界本机录像清单，在同项目逐素材抽帧／音轨保存，Pending等待另行明确分析。批次开始即冻结原清单／配置／每任务后续费用上限，预先分配固定runId并落盘；逐项状态原子保存，失败不丢已完成工作。显式--resume批次按原配置复核及续跑，同批次不能重建已存在任务；已准备媒体复核后跳过提取，已进入模型分析的任务只报告现状，不恢复／改费用／重试调用。

root独占新application/media_batch.py、infrastructure/media_batch_files.py、批量行为／真实脚本测试，main新增prepare-media-batch组合和原配置验证复用，scripts/prepare-media-batch.ps1、输入模板／指南及共享记录。复用现有prepare_media／MediaProcessor／TimelineStore，无新SQLite／HTTP／Provider合同。新目录内清单／配置／plan及SHA回执冻结，state可续更新；批次和项目持有进程锁，不依持久文件名猜活跃。

验证单项坏素材后继续、配置及后续限额保持、帧覆盖不足、取消／硬中断后固定ID恢复、旧完成不再抽帧、模型已开始不触动、清单／配置／状态篡改和并发写入拒绝。真实两已注册视频夹一坏文件的新项目：前后成功／中间失败，修复未登记坏文件后同批次续跑；第二进程读取、原配置和前三任务固定、0ASR／视觉／预算／搜索／真评分，旧开发项目／原视频／unknown／proposal保持。

用户已获通俗开工说明：一次清单逐项准备，中断后继续同批次，不做模型分析或费用预留。小问题／TD012等延期，不重复无变化完整验证；新两次¥4.07仍待授权，F006/F009/F010false。上一普通push连接失败，此轮先离线交付。

## 实现与实际交付

已实现media-batch-input-v1（UTF-8/BOM、1–100项、1MiB、不同id和原路径）、预分配固定runId、项目内原输入／配置／plan SHA回执；可变state逐项原子替换且批次／原SQLite双进程锁。media_batch只组合原prepare_media：新项探测，Pending已准备完整核验复用不写任务，media-only失败／取消／stale Running显式同ID接续；非media阶段或调用仅analysis_started，不重置状态／unknown。帧／重叠上传数不足coverage_blocked并空分析命令。输入失败继续，存储／环境停止、取消130，verifiedThisInvocation区分尚未复核的旧状态。每段探测及后续操作检查剩余期限，不能硬取消SQLite／hash I/O。

CLI prepare-media-batch／PowerShell7入口、模板和指南完成。单段prepare-media原配置验证提取共用，原行为保留，无新Provider／SQL／HTTP合同，0模型／新预留。原清单或配置文件可移走，续批次不可覆盖冻结资料；原字节／任务身份变化停止，不自动重建已登记任务。

实际三开发PV：首次两Atom夹坏文件3974ms／exit2／prepared-failed-prepared；修复尚未登记坏文件为第三个独立SHA的漫画录像，公开PowerShell7同批次3125ms／exit0／固定三runId、复用原两任务124文件。第三次禁止probe/preprocess769ms／原228项目文件逐字节保持。三任务55／96／65图均音轨可用，原配置hash相同、后续上限¥1仅保存、media attempt1、Pending、0invocations／events，另一真实进程plan SHA／任务摘要相同。

batch1ba0b7c0b77a478893f02146a281f64b、plan SHA2dfb1acef990ade60fc869473c0b0a1cf038dc7c1747cf12c60185f026039d3f；ignored artifacts/media-batch-preparation-validation/check-batch.py／report.json／中文输入与项目为本机证据。原demo832文件及三源SHA保持，搜索214→214，0Provider／预算／人工评分，原unknown¥4.065536和待授权proposal原SHA保持。没有真实批量模型分析／小时游戏全链路／独立人评。

已向用户通俗汇报一次准备／坏文件续跑及真实4秒／3秒／0.8秒、无新增费用和任务仍待分析。TD012在定向测试出现batch state替换拒绝，保留日志，不循环修生产；TD013为代码路径检查的首DB创建前恢复缺口，非阻断已有任务主流程，指南已明确。下一root主线跨素材检索：一次需求搜多段已完成录像、保持来源／原时间／排名；先登记归属，不拿新批次准备当分析完成。

## 验证状态

最终一次完整2117passed／1旧HTTP连接中断失败／1 Windows symlink权限skip372.98s；JUnit2119／errors0，23新增批次行为全部通过。旧失败test_bad_match_requests_are_rejected_before_source_mutation[oversize]为WinError10053，仅一次窄复查1passed0.981s，不称第一次全过／不重跑整套。159格式／83类型／lint和后续CLI／双离线wheel均通过，wheel SHAdeb283c665afbd762eff48a2d87fcccff5c3e92d63945aef54ce2f6784d270cd，82包文件逐字节等于源码，无媒体／环境／缓存／DB。回执.cache/media-batch-tests.xml／verify.log／old-failure-recheck.xml／package.json。现有tasks入口实际3项均pending／media_prepared／remoteRequests0，边界回执.cache/media-batch-boundaries.json保留旧unknown／空retry命令、proposal SHA和未过三gate。

新增23项行为。首轮夹具误用不存在_ports／漏v2字段／await生成器／invocation elapsed已直接按原合同更正；生产只有remaining闭包绑定的lint修正。定向最后一次77passed／1 state保存拒绝，其余原准备／CLI／架构通过，硬杀恢复独立一次窄复查1passed；硬杀测试最终聚焦单个Running任务（其他多项继续由独立批次测试覆盖），完整验证将覆盖最终源码。完整检查启动后仅文档／ignored证据，无生产源码或测试改动，运行结果补记下方。
