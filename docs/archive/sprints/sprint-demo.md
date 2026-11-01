# Phase 0 完整 CLI Demo

2026-10-04，用户授权继续实施，目标是本地视频 → 语义时间线/SQLite → 自然语言搜索与时间码的可运行闭环，遵循总方案 §58/71；正式UI、商业系统不在本轮范围。根分支 `codex/phase0-demo`，起点 `dee146b`。每个验证节点持续保存，不等会话结束。

## 分工

- root：config v2、全轴滑窗、窗口checkpoint/显式恢复、ASR提前登记、CLI/search/benchmark接线、真实本地/API实验、整合和文档。
- `demo_pricing`：独立 `.worktrees/demo-pricing`，价格快照及视觉计价；官方CNY价目核对，费用保持 estimated/unknown。
- `demo_retrieval`：独立 `.worktrees/demo-retrieval`，词法/真正本地ONNX语义检索和固定模型资产清单。
- `demo_benchmark`：独立 `.worktrees/demo-benchmark`，人工标签清单/评分工具，不伪造真实gate。

## 验证目标及真实限制

当前进程已有DeepSeek凭据，仅检查存在，不复制或写盘。可执行有预算上限的真实请求。全部环境/包/模型/缓存仍在项目目录。本轮先在授权开发素材运行完整CLI，再比较词法/语义结果；独立人工Top10≥70%仍须真实人评，不能用Demo成功替代验收。

价格配置缺口由代码补齐，不要求用户自行提供官方价目。默认保存版本化价格记录，未知费用不记零，首轮全视频上传只限已有抽帧，不上传视频文件。失败先保存已有窗口，不自动重放无法确认费用的请求。

最新完整基线：332 passed/0skip、Ruff/mypy/重复wheel通过。F003/F005/F006在各自证据记录前继续false。

## 实测检查点（2026-10-04）
完整95.175874s PV经24窗口得到111events/0transcripts，run f76f5d6495314c04ae04083614d4afd6；费用估算0.06246088CNY。早期schema失败run823799e10a0440e8aec8b78b603bec57完整保留，估算0.01163912CNY，总0.0741CNY。现有CLI hybrid/search及schema3物理向量/检索、第二进程读取已通过；三查询三mode重复稳定，真实英文query漏召回和puresemantic负例错返未隐藏。人工gate仍null。首轮整合verify551pass/6fail/2err，正在修legacy schema测试及presend固定fixture。完整JSON证据在ignored artifacts/demo-phase0/demo-validation.json。


## 最终技术验收与接续

2026-10-04，./scripts/verify.ps1退出0：557 passed/0skip（51.13s）、Ruff、mypy42源文件及CLI通过。离线wheel两次SHA256相同：90c27fba9af76a86a35c191d684d0c5160baf07b49a4e8e90eb0356bf6eb4a75。zip检查41条package/dist-info，无缓存、视频、原生DLL或权重。setup-demo.ps1 -Offline和run-demo.ps1 -Run已实测；三query×三mode重复稳定、另进程重读以及CLI benchmark未标注报告退出6通过。

首轮6fail/2err已修，未放松生产合同：旧迁移测试当前版本3/future4，已知fixture pin在begin_invocation前登记，-I子进程用-X utf8防cp936掩盖错误，非崩溃路径finally关闭。新增ASR presend、model变更拒绝、已完成窗口跳过、最后checkpoint后恢复、未知收费明确重试/保留预算、NULL音频候选及unverified费用不可提升回归。

F003/F005依feature_list合同技术验收：真实视觉/ASR证据与Provider替换合同、unknown费用/逐次记录；Completed source区间/证据、稳定去重/合法空结果、固定词法/本地语义对照。此验收不声称人评≥70%。F006false：真实英文漏召回、puresemantic负例误召回和未知人工grade仍保留；未做独立会话冻结及小时级验证，不开始正式UI。

API模型费用本轮总估算0.0741CNY（完成0.06246088+失败0.01163912），不含硬件/工具费用，未核账单。用户/系统环境及三处Python注册表5指纹与此前相同，证据.cache/demo-host-after.json；所有包/模型/运行库仅项目内。最终worker及文档已整合；下一owner按HANDOFF/TD004/TD005冻结人评集和改善检索，不重复搭建环境。

代码与当前规格检查点19cfe58已成功推送origin/codex/phase0-demo，并快进同步到origin/main。接续直接使用main；旧F003/Grok分支为历史。核心代码和wheel未因交接记录更新而改变。
