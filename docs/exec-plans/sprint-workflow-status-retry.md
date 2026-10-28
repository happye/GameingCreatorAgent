# TD012 验收状态跨进程文件占用（2026-10-29）

**当前状态（2026-10-29）**：源码 d13b0e7 的四项整合检查已全部通过：3706 passed、3 skipped、924.98秒，双次离线wheel一致（SHA256 89cccf1437350a577a964b374b549aa700caa010e5031061aff7bacb7f78190a），退出码0；日志.cache/verify-20261029-session6d.log。句柄1410已正常结束，不再等待或重启。三项工作台功能与TD012两状态入口已交付、独立评估PASS。当前无活跃源码写者或后台验证任务；后续主线仍为Phase 0真实质量验收，F006/F009/F010保持false，不越过人工门禁。

以下为合同和按时间保留的过程记录，旧“实现中／运行中／下一步”以本条当前状态为准。

阶段：Phase 0 验收工作流可靠性。前三项计划工具交付后，处理已记录的生产阻断：步骤已生成输出，但status.json终态替换遇WinError5会丢失完成状态，界面误作中断。不是新检索/新分析。

实施：task_developer/Sol medium独立worktree .cache/worktrees/workflow-status-retry、codex/workflow-status-retry（base 9833199），仅ui/benchmark_workflow.py与新tests/test_benchmark_workflow_file_contention.py；主控公共文档，Sol/high唯一边界审查。并行主树完整verify日志session6c、句柄80163，禁止修改主树源码。

合同：复用现有原子临时文件+replace、writer OS锁、进程内锁及身份/哈希规则。在状态读取/原子替换遇Windows共享占用错误（winerror5/32/33）时有界短等，最多约1秒，非这些错误即时抛出；不吞失败、不重跑步骤、不放松验证、不覆盖原文件直到replace成功。不无限重试，持续占用超时保留原状态与原输出，错误沿既有路径传播。临时文件仅清理本次自建的那个，不能误删他人文件。

验收：独立进程真实Windows句柄暂占status.json后释放，终态写成功并且完整可读；占用超过等待上限则有界失败、原文件不变、临时清理；非共享错误不重试；读取侧同类占用有界恢复；既有工作流状态/锁/身份测试通过。不依赖随机压测撞到故障。先dot-source主树env.ps1，再设置当前进程PYTHONPATH指向worktree/src，Python -B，缓存与临时目录各自隔离，保护共享runtime回执。

合同细化：真实CreateFileW share=0占用下，pathlib.open/read_bounded在Windows抛PermissionError(errno=EACCES13)但不保留winerror；写replace正常保留winerror32。为避免CRT或平台专用I/O扩展，读取侧仅对Windows、缺winerror、PermissionError且errno13的已知映射同样有界等待。永久ACL拒绝仍约1秒后原异常抛出，不跳过权限；非Windows及其他错误立即失败。写侧仍原winerror5/32/33。这是错误映射识别，未改变安全/身份/状态合同，需独立guard核对。

范围核对及收敛：Luna/high确认仅改benchmark_workflow可关闭验收status子项，整项TD012仍有infrastructure/media_batch_files.py的state.json跨进程占用（读214起、原子替换224起）开放。为完成这项有界可靠性交付，将原已审逻辑提到极小Infrastructure file_sharing helper，两入口复用，不改身份/批次SHA/锁/prepare或模型操作。Sol/medium增加media_batch_files.py、共享helper及新batch占用测试归属；仍独立worktree。原status子项13项通过、Sol/high PASS保留；新增模块集成前只做新增边界审查，不重复普通review。TD012暂保持partial，待两条实际入口证据齐后再决定关单。

集成节点：Sol/medium最终55项通过（原13状态占用+新8批次占用+31批次+3架构），Ruff与三源码mypy通过；Sol/high新增helper/batch唯一增量审查PASS，无有证据缺陷。三功能基线9833199完整verify已3685通过/3跳过、退出0，TD012于其后集成主树，主树FFmpeg相关回归句柄68982运行中。原工作树未准备FFmpeg导致的17跳过不能作为主树通过，正在补齐。下一步主树定向结果/技术债范围关单/提交/最终完整verify。

主树集成验证通过：包含21项新增占用测试、既有批次/架构/验收工作流及浏览器组全部通过，补齐独立工作树FFmpeg跳过范围；无新增跳过。TD012唯一剩余两条公开状态入口已处理，记resolved；尚未完成最终整合源码完整verify，下一条运行session6d，期间固定源码。用户已获功能/影响/验证边界与下一步说明。

最终整合检查已实际启动：源码d13b0e7，exec句柄1410，日志.cache/verify-20261029-session6d.log，状态运行中。此前三个功能完整基线已通过。期间不改源码，不另起重复全量。
