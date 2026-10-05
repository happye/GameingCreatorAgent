# F010：断网接续的严格条件工作台

2026-10-06；owner root / Codex，codex/visual-details；接续998bc2d。

## 目标与范围

保持Phase 0、人评未通过及原视频/源时钟/事实/检索rank/篮子身份不变。把已有离线typed AND接入本地页面，允许明确选择v1/v2精分析结果、添加同主体/同部件条件并查看full/partial/no_match/unverified和支持帧。缺结果不得发送Provider、保存或补全。并行独立v3部件合同与只读成本历史由assignments登记owner，root串行集成。自由文本继续按已有检索，不冒充严格条件解析。

## 验证与恢复

已核对工作树clean、HEAD998bc2d；init -CheckOnly通过11项。最后源码完整验证仍1062 passed/1文件symlink权限skip。两次授权HTTP已用完、旧unknown预留保留。新阶段须完成定向HTTP/浏览器反例、完整verify及本地检查点，网络失败不妨碍离线实现。暂未开始新源码验证。

## 实现节点

本地POST /api/match-details严格接受project/run/event/profile/query-v1 constraint，限制64KiB、拒绝重复字段/未知字段/非本机Origin，只读SQLite与精确侧车，不保存match也不发送Provider。页面默认v2，显式profile选择、保持当前片段、弹窗条件编辑/部件组/状态/支持帧展示；编辑、刷新、切换和关闭取消旧match并清理结果。v2 Provider新增protected prompt/identity/parser复用点供独立v3继承，原v2prompt/hash/parser不改。

定向验证运行中：首轮pytest临时目录父目录未预建导致fixture错误（并非产品失败）；已按verify流程预建独立.cache目录并重跑，日志.cache/detail-workspace-targeted.log。Ruff导入顺序已修，mypy58 source通过；新HTTP和browser tests尚待最终结果。

补强节点：inspection暴露reused的payloadHash，POST结果须匹配当前requestHash与payloadHash。迟到响应覆盖条件编辑、关闭、切版本和切run；已有候选添加篮子后核对/切版本，rank/原源表/sidecar与导出保持。Windows拒绝POST未读body导致偶发TCPreset，改为有界读取后返回403；测试SQLite读连接需显式close（context manager仅事务）已修。新22项中21通过，修正最后测试连接后该浏览器单项通过；完整verify待worker整合后统一运行。
