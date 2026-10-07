# Technical debt

TD012补充（2026-10-07原片参考交付）：一次完整2225passed／3旧准备失败／1权限skip441.531s JUnit，.cache/benchmark-reference-final-tests.xml／final-verify.log及原目录保留。test_corrupt_batch_records_refuse_before_media_work[state.json]明确storage.batch_checkpoint；test_coverage_is_reported_without_analysis_command_or_new_budget期望输入2实际存储5；test_browser_page_reload_recovers_live_job_then_explicit_stop_and_same_batch_resume停止按钮已disabled超时，第三原因未证实，不把它直接归作同一存储根因。首窄命令漏父目录3setup error／无测试执行保留recheck.xml，正确准备后仅一次3passed6.121s（recheck-final.xml）。22原片新检查全部通过；不改保存或加生产重试、不重新跑无变化整套，原因继续未解。

TD012补充（2026-10-07准备页面交付）：一次完整2204passed／1新test_prepare_browser_three_materials_download_and_open_waiting_tasks[viewport0]失败／1权限skip444.233s，失败项目state明确第三项storage.batch_checkpoint／停止，两项prepared保留。.cache/media-preparation-workspace-tests.xml／verify.log及原pytest目录保存；唯一失败仅一次窄复查1passed3.021s（workspace-recheck.xml）。原因未定位、旧save未改、未加重试；最终另修明确UI读批次取消后按钮状态，并相关28项通过，未重新跑完整。继续延期，不把新测试遇旧问题说成旧测试或整套全绿。

TD012补充（2026-10-07准备页面检查点）：20新后台／HTTP全部通过，合跑原23批次测试有4项状态保存／恢复失败（.cache/media-preparation-jobs-first.xml）。test_bad_middle_item_continues_and_repaired_item_reuses_frozen_batch、test_cancel_stops_remaining_items_and_explicit_resume_keeps_ids、test_started_analysis_is_reported_without_touching_stage_or_unknown_invocation、test_per_item_deadline_includes_probe_and_can_be_explicitly_extended仅一次窄复查4passed1.854s（.cache/media-preparation-old-failure-recheck.xml）。未定位原因、未更改旧保存或加入生产重试；按用户主线优先延期。本轮尚未运行整体验证，不能把此复查称整套通过。

TD004补充（2026-10-07跨素材检索）：真实三开发片的长负面词法查询“**不存在**的星际交易飞船维修机制”仍得到一候选，唯一共享bigram为“**存在**”，原facts含“仍存在”。证明有限检索不保证负面／整句意图，不代表录像包含该机制。证据ignored artifacts/project-retrieval-validation/report.json；程序与原单run排名未改，首次校验误假设应空已纠正，三原查询记录保留后再做最终验证，共七新项目查询。按用户优先级只记录、不在本轮循环修复；F006仍false。

TD012补充（同轮）：一次完整回归的旧test_coverage_is_reported_without_analysis_command_or_new_budget遇storage.batch_checkpoint，.cache/project-retrieval-tests.xml／verify.log留证；唯一失败仅一次窄复查1passed0.648s（old-failure.xml）。40新增联合检索全部通过，无生产重试／状态持久化修改，不重跑无变化整套。

Record debt when it is discovered; do not hide it in a passing feature. Review related entries during each sprint and close them with a tested change.

| ID | Found | Severity | Impact | Proposed fix | Status |
| --- | --- | --- | --- | --- | --- |

| TD001 | 2026-10-03/F002 | medium | 已识别showinfo／双ashowinfo记录已改流式消费，不再按完整日志16MiB拒绝长素材；未知诊断行与单行继续受限 | 一小时合成带音轨、63.2MB时间记录／3600图／168752音频分段通过真实FFmpeg、保存及第二进程回读；取消／超时／错误回收和完整1912／1权限skip通过。真实游戏小时性能与全进程峰值由TD005继续跟踪，见sprint-long-footage-media | resolved; synthetic-hour capacity verified |
| TD002 | 2026-10-03/F002 | medium | 缺精确 stream start/duration/timebase 的容器被明确拒绝 | 需要支持时用可验证补探测，补容器/原始 PTS fixtures；不得猜 format.duration | open |
| TD003 | 2026-10-03/F000 | release prerequisite | 当前 FFmpeg 是复制副本，固定 hash 不等于分发来源/许可证完整 | 发布前固定可取得来源、审查 GPL 与第三方 notices；保持项目内安装 | open |
| TD004 | 2026-10-04/F005 | high before F006 | v4有限否定规则已排除Atom jump的明确否定候选；Boss/射击/汽车维修hybrid为空，但pure semantic仍误召回，阈值未用人评校准，不能证明U10 | 冻结独立人评/主稀疏负例查询，测否定/混合语义覆盖、pure semantic负例和片段边界 | open |
| TD005 | 2026-10-04/F005 | medium | 1024整次请求限制已解除，固定batch=1；真实小时游戏全链路、总进程峰值及source hash I/O待测。一小时合成准备续跑的文件核对／映射重建仍25秒；素材任务清单metadata读取已独立，一小时完整详情首次5秒等待超时，实际打开耗时尚未验证，不循环优化 | 已有2051文本／1280事件及真实E5 1281文本18.6s／2.6s证据；一小时合成实际本地准备／保存33秒、续准备25秒未重新抽帧、独立进程读回，见sprint-media-preparation与sprint-long-footage-media。下一步真实长素材资源验证，另择阶段优化重复核对 | partial / real long-footage resources pending |
| TD006 | 2026-10-04/F007 | medium | 工作台原视频seek仅在现有零起点PV验证；非零PTS/音视频异步起点及浏览器不支持编码尚未联调 | 补真实浏览器容器/编码fixture，核对媒体规范化源时钟与currentTime映射，必要时增加显式映射或本地预览转码 | open |
| TD007 | 2026-10-04/F009 | high before F006 | v4有效多帧JSON仍可能跨镜头关联、下落/jump歧义、标签/不确定性矛盾；静帧幻觉被拒绝使窗口失败，4秒跨度不能覆盖长动作/Boss遭遇 | 冻结真实动作/切镜/静帧样本，比较更合适视觉Provider与事件表示、候选精分析/长窗口；保留失败与全部费用，独立人工验收 | open |
| TD008 | 2026-10-04/F007 | low | 源/证据hash缓存依赖文件大小/mtime等身份变化，不能发现元数据完全不变的同大小外部改写 | 当前媒体按不可变素材使用；若需对抗元数据保持修改，提供强制重验/显式缓存期限并测I/O成本，不宣称已解决 | open |
| TD009 | 2026-10-05/F010 | high before detail acceptance | V5/V6紧凑事实可描述细节，但自由文本RRF不保证条件全部满足/同一主体/同一部件；恶魔领主复合例V6仍hybrid8局部候选，uncertainty不能抵消facts误分类，E5截断512token；静态衣着不独立索引 | 按actor-detail-matching-spec实现候选sidecar精分析与同actor/part AND、共同支持帧和uncertain保护；合同先冻结，再Provider/预算与Store/UI；独立复合人评，静态索引另立事件类型，不删除动作保护 | open |
| TD010 | 2026-10-06/F005 | medium; defer outside current milestone | 正文明确否认某动作时，同动作裸mechanicTag可能盖过否认保护；人工夹具17/18复现，真实四run尚未证明存在同样矛盾 | 后续修改否认保护的事实／标签优先级，保留其他动作／真实肯定／模糊与负意图、原passage与来源。复现在ignored artifacts/action-tag-support/tag-denial-repro.py，红测.cache/action-tag-support-red.xml；生产源码未改 | deferred per user delivery priority |
| TD011 | 2026-10-07/F002 | low; local shell compatibility | 从当前Codex PowerShell 7环境拉起Windows PowerShell 5时，媒体校验包装脚本遇Get-FileHash不可用；移除继承模块路径也未解决，不继续反复定位 | 当前使用已有PowerShell 7执行同一脚本和真实入口验证，不改全局环境／安装组件；后续需验证独立Windows PowerShell 5环境，不能称其通过 | deferred; use prepared PowerShell 7 |
| TD012 | 2026-10-07/F006 | low; intermittent verification environment | 完整候选评审回归中两个旧测试分别WinError10053本机HTTP连接中断、WinError5替换report.json拒绝访问；原因未定位，不能据此称生产问题已修复 | 保留.cache/benchmark-review-tests.xml／verify.log，失败为test_bad_draft_requests_cannot_access_a_project[content_type]和test_each_outcome_is_durable_and_reverse_sends_no_http[False]；仅一次窄复查2passed1.11s，代码未改。后续相关环境阶段复现与定位，不重跑无变化全套 | deferred per user delivery priority; focused recheck passed |
| TD013 | 2026-10-07/F002 | low; before first task only | 批次plan已冻结但SQLite尚未创建就中断时，resume的原项目存在性检查拒绝；尚无已创建任务，不影响已有任务恢复 | 保留批次冻结资料，恢复环境后重新提交清单；后续明确仅对未创建任务的批次放开初始化，不能重建已丢失DB中的分析或未知费用。由本轮代码路径检查发现，未宣称真实硬杀在此窗口验证 | deferred per user delivery priority |
| TD014 | 2026-10-07/F006 | medium; workflow status display | 旧原片HTTP流程检查在一步保存时读取到busy=false／interrupted，而最终磁盘记录finished；完整与一次窄复查均出现，不能称环境偶发已修复 | 复现tests/test_benchmark_workflow.py::test_http_registered_source_range_csp_and_reference_import；保留.cache/benchmark-run-picker-tests.xml和old-workflow-recheck.xml／原目录。后续核对status快照与执行锁之间的完成时序；不自动重试或改写已有步骤。当前新选择11项与实际四步／独立读回通过，保留旧问题后继续主要交付 | deferred per user delivery priority; single recheck still failed |

TD012补充（2026-10-07多素材准备）：定向批次state替换也偶发storage.batch_checkpoint，保留.cache/media-batch-behavior.xml／complete-targeted.xml；最终23新增在一次完整回归均通过。该次旧HTTP oversized请求WinError10053失败，.cache/media-batch-tests.xml／verify.log保留，唯一失败一次窄复查1passed0.981s（old-failure-recheck.xml）。没有定位环境原因、加生产重试或重跑无变化全套，继续按用户优先级延期。

TD012补充（2026-10-07统一验收入口）：完整回归两旧media-preparation-jobs检查分别出现项目路径资格拒绝和取消范围400而非404，原代码未改，原因未确定；.cache/benchmark-workflow-verify.log保留。一轮窄复查连同新增能力声明同步检查3passed2.22s（recheck.xml），不称两旧问题已修复、不重跑整套、不放松路径边界。旧health预期未包含新能力属于本次合同检查同步，已改测试，不归入环境债务。

TD012补充（2026-10-07冻结来源选择）：相关定向检查中的旧test_actual_os_lock_blocks_duplicate_and_released_ownership_is_interrupted在读取status.json时PermissionError，原输出.cache/benchmark-run-picker-focused.xml；生产执行锁／保存路径未改，原因未定位。保留影响与复现入口，做一次窄复查后继续主交付，不通过生产重试掩盖，不把复查通过称为原因解决。
