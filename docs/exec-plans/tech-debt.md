# Technical debt

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

TD012补充（2026-10-07多素材准备）：定向批次state替换也偶发storage.batch_checkpoint，保留.cache/media-batch-behavior.xml／complete-targeted.xml；最终23新增在一次完整回归均通过。该次旧HTTP oversized请求WinError10053失败，.cache/media-batch-tests.xml／verify.log保留，唯一失败一次窄复查1passed0.981s（old-failure-recheck.xml）。没有定位环境原因、加生产重试或重跑无变化全套，继续按用户优先级延期。
