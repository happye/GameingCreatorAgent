# 验收第6／8步结果通俗卡片（2026-10-28）

**当前状态（2026-10-29）**：源码 d13b0e7 的四项整合检查已全部通过：3706 passed、3 skipped、924.98秒，双次离线wheel一致（SHA256 89cccf1437350a577a964b374b549aa700caa010e5031061aff7bacb7f78190a），退出码0；日志.cache/verify-20261029-session6d.log。句柄1410已正常结束，不再等待或重启。三项工作台功能与TD012两状态入口已交付、独立评估PASS。当前无活跃源码写者或后台验证任务；后续主线仍为Phase 0真实质量验收，F006/F009/F010保持false，不越过人工门禁。

以下为合同和按时间保留的过程记录，旧“实现中／运行中／下一步”以本条当前状态为准。

阶段：Phase 0 验收工作台，HANDOFF第二轮候选排名第四。当前仅只读定位与合同，完整verify结束前不改代码。

主交付：第6步固定检索报告完成后展示“原十位排名已保存、下一步人工回看”，列出每条查询的查询文本、种类、返回槽位/失败；不显示质量门槛，不把没有人评的0或null说成理解失败。第8步读取固定评分报告，按原qualityGate及qualityStatus显示通过、未通过、未验证，列出原报告的可用率与状态，不能自行计算门槛、补位或重排。第7步不加门槛或诱导信息。报告卡片注明只读已有文件、没有重跑检索。

复用安全入口：benchmark-workflow.js fileUrl(row,name)→/api/benchmark-file，后端仅已完成且登记过的文件、限定名称、大小及SHA核验。第6步benchmark-report.json，第8步benchmark-fixed-report.json，实际报告schemaVersion=1，固定评分还需scoring.schemaVersion=benchmark-fixed-scoring-v1。不能把CLI envelope benchmark-fixed-score-result-v1当文件schema。

异步保护：每个卡片绑定workflow id、attempt id及文件sha；切换workflow或重绘后旧响应不得回填。用textContent展示。缺报告/读取失败/未知结构显示“结果摘要暂不可读”，原文件链接继续可用，不回退推断。只读报告卡片，不扩展费用、SQL或人工判断存储。

待验证：passed/failed/unverified/null、失败查询、部分判断、摘要缺失、坏schema、切换工作流迟到响应、桌面/窄屏；保留原链接与原query顺序。人工验收边界交付前由Sol/high独立核对（替代普通审查，不叠加）。

只读定位：task_explorer，gpt-6-luna/high；源字段见application/benchmark.py:575起与benchmark_review_scoring.py:100起，入口ui/benchmark_workflow.py:255起。

实施节点：已创建独立worktree .cache/worktrees/benchmark-result-cards、分支codex/benchmark-result-cards（base b84d850）；task_developer/gpt-6.1-sol/medium唯一源码写者。主树verify句柄16797运行时只在独立worktree开发/定向测试，主树不变；禁止worker提交/推送，回传后主控集成。

交付节点（2026-10-29）：独立Sol/medium实现两文件；新增13浏览器＋旧静态1项通过。界面中文解释状态，原null保留尚未验证、失败返回数量未知。Sol/high task_quality_guard唯一评估PASS，无P0/P1/P2，静态审查未重跑测试。现已集成主树，正在运行相关workflow浏览器检查。此前完整verify针对前两项为3671通过/1环境门禁失败/3跳过；共享运行时134个pyc原字节已从SHA核验归档恢复，3309项原回执匹配，init和失败用例已通过。下一步对集成三项最终源码完整verify，期间固定源码。

集成验证：主树新13项＋benchmark workflow浏览器＋静态测试全部通过，Ruff格式/检查与diff检查通过。准备最终完整verify日志.cache/verify-20261029-session6c.log；该检查完成前不改源码。
