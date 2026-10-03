# Technical debt

Record debt when it is discovered; do not hide it in a passing feature. Review related entries during each sprint and close them with a tested change.

| ID | Found | Severity | Impact | Proposed fix | Status |
| --- | --- | --- | --- | --- | --- |

| TD001 | 2026-10-03/F002 | medium | 全量 showinfo/双 ashowinfo 日志受 16MiB 限制，小时级素材可能明确失败 | F006 长视频验证前流式解析/持久化日志并维持输出限流、取消和 EOF 回收测试 | open |
| TD002 | 2026-10-03/F002 | medium | 缺精确 stream start/duration/timebase 的容器被明确拒绝 | 需要支持时用可验证补探测，补容器/原始 PTS fixtures；不得猜 format.duration | open |
| TD003 | 2026-10-03/F000 | release prerequisite | 当前 FFmpeg 是复制副本，固定 hash 不等于分发来源/许可证完整 | 发布前固定可取得来源、审查 GPL 与第三方 notices；保持项目内安装 | open |
