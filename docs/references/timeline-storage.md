# SQLite 存储与恢复

F004 的实现入口为 `application/storage.py` 的 `TimelineStore` port 与 `infrastructure/sqlite_store.py`。`SqliteTimelineStore.open(project)` 建立 writer；`read_only=True` 不取分析锁、不开迁移，仍验证 schema。每实例只有一条拥有连接的专用线程，关闭会排空此前操作；调用方取消不截断 SQL 事务。

## 文件和 schema

- `timeline.sqlite3`：当前 schema v3，13 个 STRICT 表，定义在 `sqlite_schema.py`。v1 九表保持历史定义；v2 添加转录 uncertainty；v3 添加 embeddings、retrieval_runs、retrieval_hits、retrieval_hit_evidence。
- `.analysis-writer.lock`：OS 句柄锁，文件保留不代表占用；第二 writer 非阻塞返回 `storage.writer_busy`。进程退出释放锁，reader 可并行。
- `runs/<run-id>/media/`：F002 已发布的 manifest、图片/WAV。登记路径必须属于该 run，禁止越界链接；源视频保持原位，可在项目外。
- `runs/<run-id>/semantic_timeline.json` 和 `searches/<retrieval-id>.json`：完成时间线/检索的导出，数据库登记与文件导出分开执行。

连接明确使用 autocommit、FK、WAL、FULL 和 1000ms busy timeout。迁移以 BEGIN IMMEDIATE/COMMIT/ROLLBACK 原子执行；高版本、版本断层、表/索引/触发器漂移均拒绝。媒体、run 与证据使用组合 FK；事件引用必须属于相同 run/media，时间再对数据库媒体时长检查。

## 写入与续跑

1. `create_run` 校验来源 hash，保存类型化白名单配置、Decimal 预算、pipeline/required-stages 快照及 hash。
2. `begin_stage` 记录输入 hash；续跑保持原输入，attempt 递增，完成的 checkpoint 不可重写。
3. `persist_media_bundle` 核对 manifest 的原始时钟、piecewise 音频映射及不确定性证明、文件 hash；证据和 Completed checkpoint 同事务登记。
4. ASR worker 开始或视觉发送前 `begin_invocation`；每个逻辑窗口/每次 attempt 独立唯一。`finish_invocation` 保存实际模型/修订/用量/价格/耗时。费用存 Decimal 文本，未知为 NULL，真实零为 `"0"`。模型修订/价格快照不可在 finish 改写；视觉执行详情保留 reservationCny/inputFrames/evidenceIds，schemaError 只存有限诊断码。
5. `persist_timeline` 将事件、证据链接、转录及 checkpoint 整批原子写入；任意无效链接回滚整批。
6. `complete_run` 检查声明阶段、账本与文件。完成后语义输出不可修改；`load_completed_timeline` 每次重新校验来源和已登记文件，拒绝非 Completed 或损坏结果。

`load_media_bundle` 重建未完成或 Interrupted run 的已完成媒体阶段，包括全部 PTS/音频映射。v2 `analyze --resume` 是显式操作：在 writer 锁下校验来源/文件/原配置，将进行中记录标记 Interrupted，再恢复 run；跳过已完成 media/asr/视觉窗口，不自动发请求。逐窗口 `vision-000000` 等 checkpoint 与输出原子提交，父 vision 完成后再 finalize run；所有 checkpoint 已完成的恢复无需重跑模型。

未完成窗口存在可能已计费的远端调用时，要求 `--retry-uncertain`；恢复账本累计所有尝试的请求数、上传图片数和已知费用，未知费用保留原 reservation。原预算不能覆盖增大，重试仍受硬上限。旧 v1 维持有限 checkpoint 续跑。ASR 输入 hash 含权重修订/稳定参数，视觉配置固定 prompt 内容 hash；变化拒绝续跑。不能私读 SQL 或按 WAV 秒数假定源视频秒数。

## 向量与检索记录

检索只接受经完整性校验的 Completed run。`persist_search` 原子登记事件 embedding、retrieval run、ranked hits 和 evidence links，空结果也可保存；不修改已完成分析。组合 FK 约束相同 run/media/事件证据，区间仍不超过源时长。分析只读 reader 可并行；记录新检索需要 writer 锁。

向量唯一键含 run/subject、provider/model/revision_scope、dimension/normalization/text_hash；本地 E5 v2 的空间身份含固定权重 hash 与 batch=1/pooling/token limit 等合同。未知或不同空间不能混检。检索快照保存 query/hash、排序版本/阈值、空间身份、耗时、分数语义与实际证据；默认 hybrid，另有 lexical/semantic。数据回读不替代人评。

## 恢复与实际边界

`recover` 将 Running run/stage/调用置 Interrupted，保留完成阶段和账本；未知费用不改零，也不重放请求。逐 run 报告来源/证据/快照损坏，受损 Completed run 改为 Failed；一个坏记录不阻止其他运行恢复。只在受管 runs 目录报告孤儿和临时文件，不遍历 junction/symlink、不自动删除。

哈希读取在事务外，但完整性查询会重新读源文件；小时级素材的 I/O 性能尚未测量。数据库不存视频或音频 bytes。时间线/检索 JSON 单独导出，失败不能冒称与数据库同时原子。CLI benchmark 从冻结人工标签清单生成报告；gate 未验证或失败返回退出 6，并保留报告。

`./scripts/test-storage.ps1 -AllLocal` 验证四段本地素材的完整 bundle 跨进程重读；该工具只要求 media 阶段，没有模型调用或语义质量结论。普通 pytest 的真实进程测试覆盖事件/账本、中断/回滚、并发锁、损坏与关闭行为，见 sprint-F004。
