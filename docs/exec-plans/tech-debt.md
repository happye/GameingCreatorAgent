# Technical debt

Record debt when it is discovered; do not hide it in a passing feature. Review related entries during each sprint and close them with a tested change.

| ID | Found | Severity | Impact | Proposed fix | Status |
| --- | --- | --- | --- | --- | --- |

| TD001 | 2026-10-03/F002 | medium | 全量 showinfo/双 ashowinfo 日志受 16MiB 限制，小时级素材可能明确失败 | F006 长视频验证前流式解析/持久化日志并维持输出限流、取消和 EOF 回收测试 | open |
| TD002 | 2026-10-03/F002 | medium | 缺精确 stream start/duration/timebase 的容器被明确拒绝 | 需要支持时用可验证补探测，补容器/原始 PTS fixtures；不得猜 format.duration | open |
| TD003 | 2026-10-03/F000 | release prerequisite | 当前 FFmpeg 是复制副本，固定 hash 不等于分发来源/许可证完整 | 发布前固定可取得来源、审查 GPL 与第三方 notices；保持项目内安装 | open |
| TD004 | 2026-10-04/F005 | high before F006 | v4有限否定规则已排除Atom jump的明确否定候选；Boss/射击/汽车维修hybrid为空，但pure semantic仍误召回，阈值未用人评校准，不能证明U10 | 冻结独立人评/主稀疏负例查询，测否定/混合语义覆盖、pure semantic负例和片段边界 | open |
| TD005 | 2026-10-04/F005 | medium | 当前embedding请求最多1024文本，逐文本固定batch，小时级事件索引和全量source hash I/O尚未实测 | 按验证后的空间分批索引，保持原子持久化/取消/稳定排序，并测长会话资源上限 | open |
| TD006 | 2026-10-04/F007 | medium | 工作台原视频seek仅在现有零起点PV验证；非零PTS/音视频异步起点及浏览器不支持编码尚未联调 | 补真实浏览器容器/编码fixture，核对媒体规范化源时钟与currentTime映射，必要时增加显式映射或本地预览转码 | open |
| TD007 | 2026-10-04/F009 | high before F006 | v4有效多帧JSON仍可能跨镜头关联、下落/jump歧义、标签/不确定性矛盾；静帧幻觉被拒绝使窗口失败，4秒跨度不能覆盖长动作/Boss遭遇 | 冻结真实动作/切镜/静帧样本，比较更合适视觉Provider与事件表示、候选精分析/长窗口；保留失败与全部费用，独立人工验收 | open |
| TD008 | 2026-10-04/F007 | low | 源/证据hash缓存依赖文件大小/mtime等身份变化，不能发现元数据完全不变的同大小外部改写 | 当前媒体按不可变素材使用；若需对抗元数据保持修改，提供强制重验/显式缓存期限并测I/O成本，不宣称已解决 | open |
| TD009 | 2026-10-05/F010 | high before detail acceptance | V5/V6紧凑事实可描述细节，但自由文本RRF不保证条件全部满足/同一主体/同一部件；恶魔领主复合例V6仍hybrid8局部候选，uncertainty不能抵消facts误分类，E5截断512token；静态衣着不独立索引 | 按actor-detail-matching-spec实现候选sidecar精分析与同actor/part AND、共同支持帧和uncertain保护；合同先冻结，再Provider/预算与Store/UI；独立复合人评，静态索引另立事件类型，不删除动作保护 | open |
| TD010 | 2026-10-06/F005 | medium; defer outside current milestone | 正文明确否认某动作时，同动作裸mechanicTag可能盖过否认保护；人工夹具17/18复现，真实四run尚未证明存在同样矛盾 | 后续修改否认保护的事实／标签优先级，保留其他动作／真实肯定／模糊与负意图、原passage与来源。复现在ignored artifacts/action-tag-support/tag-denial-repro.py，红测.cache/action-tag-support-red.xml；生产源码未改 | deferred per user delivery priority |
