# Technical debt

Record debt when it is discovered; do not hide it in a passing feature. Review related entries during each sprint and close them with a tested change.

| ID | Found | Severity | Impact | Proposed fix | Status |
| --- | --- | --- | --- | --- | --- |

| TD001 | 2026-10-03/F002 | medium | 全量 showinfo/双 ashowinfo 日志受 16MiB 限制，小时级素材可能明确失败 | F006 长视频验证前流式解析/持久化日志并维持输出限流、取消和 EOF 回收测试 | open |
| TD002 | 2026-10-03/F002 | medium | 缺精确 stream start/duration/timebase 的容器被明确拒绝 | 需要支持时用可验证补探测，补容器/原始 PTS fixtures；不得猜 format.duration | open |
| TD003 | 2026-10-03/F000 | release prerequisite | 当前 FFmpeg 是复制副本，固定 hash 不等于分发来源/许可证完整 | 发布前固定可取得来源、审查 GPL 与第三方 notices；保持项目内安装 | open |
| TD004 | 2026-10-04/F005 | high before F006 | 实际漫画PV英文攻击query零召回，puresemantic对汽车维修负例错返10；hybrid阈值未校准，当前不能证明U10 | 冻结独立人评/主稀疏负例查询，对照跨语言召回、语义阈值/重排及片段边界，保留失败 | open |
| TD005 | 2026-10-04/F005 | medium | 当前embedding请求最多1024文本，逐文本固定batch，小时级事件索引和全量source hash I/O尚未实测 | 按验证后的空间分批索引，保持原子持久化/取消/稳定排序，并测长会话资源上限 | open |
