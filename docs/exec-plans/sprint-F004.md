# F004 SQLite 存储与恢复

状态：已验收，`passes: true`。2026-10-03 开始，2026-10-04 完成；Codex root 集成，独立 schema/lock 与进程测试 workers，另有只读审查。

## 本轮边界

采用标准库 sqlite3，独占写线程及项目级进程锁；v1 落地媒体、run、checkpoint、证据、转录、事件和逐 attempt 账本。embedding/检索表随 F005 后续迁移。原始视频仅存路径/hash/时钟；不写视频 bytes。

媒体 bundle、语义输出各与完成 checkpoint 同一短事务提交；文件由 F002 先发布。Completed 查询重新验证来源、manifest 和证据文件；恢复报告损坏/孤儿/临时文件，中断状态与未知费用，不自动重放网络请求。

## 实现与验证

- 九个 STRICT 表、四索引、七个时间约束触发器；读写双方验证结构，组合 FK 防串 run/media。
- 单连接独占线程；进程 OS 锁覆盖 writer 生命周期；第二进程只读、强制退出后锁释放。
- bundle/事件/转录与完成 checkpoint 同事务；失败整批回滚；完成 run 不再修改。
- recover 对每个 run 报告坏来源/文件/快照，保留完成 checkpoint；Running 调用置 Interrupted，unknown token/cost 为 NULL，不重放。源视频 bytes 不入数据库。
- `load_media_bundle` 完整重建已完成媒体阶段；Completed 查询重新核对来源与证据。

`./scripts/verify.ps1`：**147 passed，0 skipped**，资源警告按失败处理；Ruff 37 文件、strict mypy 28 文件、导入方向/CLI 与两次离线 wheel 通过。wheel SHA256 `9c6dd6ddc7dedd8d4434c87ccf428af4268b5961e8851339c10f892d6b36e137`。

其中 F004 新增 **60 项**：schema/lock 34、service 21、真实进程/线程 5。包含第二进程完整事件/账本读回、os._exit 后未提交事务回滚、未知费用、取消/close 队列、SQL 异常后连接可用、多 run 损坏快照和 Windows junction 回归。

`./scripts/test-storage.ps1 -AllLocal`：四段真实视频共 490.693314s，492 图片＋4 WAV 登记并由第二进程读取。完整 DTO 相等，包括录屏 12,930 个音频 frame mapping、12,928 个不连续点。记录 `artifacts/storage-F004/2f4b113a813448d5907e24c370b46c4e/validation.json`（忽略）；明确 media-only、0 events、0 invocations，不代表模型结果。

## 审查修复及边界

独立审查最后确认无必须修复项。修复包括：坏路径/Decimal/分母/字段类型不阻断其他 run 恢复；readonly 验证 DDL；配置原文 hash 与媒体列/快照一致性；异步共享 close drain；完整音频不确定性证明；junction 扫描剪枝。

整套测试首次暴露旧 F002 检查立即等待 Windows interpreter 句柄的时序问题。50 次独立实验中立即检查均未 signaled，而既有 5s 等待全部退出（最长额外 0.582ms；root 单次 0.638ms）。测试现持有原句柄并限时等待，不更改产品 Job.close；不误归因 PID 复用。

v1 尚无 embedding/检索表、完整 CLI、JSON 导出或小时级 I/O 性能证据。包未增加运行依赖，未安装系统组件，未调用模型/API；Phase 0 人工质量 gate 仍未测。

## 接续状态

root 已集成全部 worker 文件，scratch worktrees 已冻结，不是下一阶段接续点。F003 继续：先按 ASR readiness 固定候选验证项目内 native runtime，再实现模型 facade/预算/schema；F005 依赖 F003 与 F004。Git 同步状态以 HANDOFF 和实际分支为准。
