# Phase 0 开发任务与依赖

依据 [反向审查](./reverse-review-2026-10-03.md)、[工程合同](../design-docs/phase-0-engineering-spec.md) 和原方案 §71。保持 F001–F006 ID，避免其他工具交接时重复创建特性。以下任务尚未实现；spike 仅为 F000 的证据。

```mermaid
flowchart LR
    F000[审查与合同] --> F001[隔离环境与核心工程]
    F001 --> F002[媒体与源时间]
    F002 --> F003[ASR/视觉与调用账本]
    F001 --> F004[SQLite与恢复]
    F003 --> F005[检索与集成]
    F004 --> F005
    F005 --> F006[真实benchmark与gate]
```

| 特性 | 交付与文件归属 | 验证与依赖 |
| --- | --- | --- |
| F001 | `.tools` 隔离安装脚本/版本清单、global.json、四个 src 工程、DTO/ports、测试/格式/引用检查；不全局安装 | 前提 F000。仅项目 SDK/缓存构建；输入错误码测试；架构方向测试；锁版本。缺包就补项目工具，不用系统安装兜底 |
| F002 | Infrastructure/Media、Evidence/时间映射、tests/Media | 前提 F001。真实素材＋合成 VFR、非零 PTS、无音轨、坏文件、路径中文空格；取消退出与源时间可追溯，不能只测帧序号 |
| F003 | Infrastructure/Providers、项目 `.venv` ASR适配、prompts、tests/Providers | 前提 F002。先 DeepSeek视觉＋一个本地ASR；静音/词表；JSON/schema/usage/预算/重试；第二Provider或合同替换验证，不伪造真实质量 |
| F004 | Infrastructure/Storage、SQL迁移、tests/Storage；消费 F001 ports | 前提 F001；可与媒体/模型适配并行。run/checkpoint/证据/账本、FK/事务、文件丢失、进程中断与恢复，恢复保留未知费用 |
| F005 | Application/Retrieval、检索适配、tests/Retrieval、CLI组合更新 | 前提 F003＋F004。固定run检索、词法与语义方案对照、去重/排序/证据/源时间；无片段合法、相同配置可复现 |
| F006 | benchmark执行器/人工标签清单、tests/Benchmark、go/no-go报告 | 前提 F005；标签准备可先行。主组逐查询≥70%、少例/负例、独立测试集、时间误差、冷/热成本与长素材速度；不达标保留未通过 |

F003 内部可将 ASR 与视觉拆为两项 owner，前提 DTO 已集成并分别拥有文件。公共 Domain/ports 由 F001 owner 集中落地；其他 Agent 不同时改共享接口。每个编码会话使用独立 branch/worktree，在 `assignments.md` 分配后开始；根 HANDOFF/progress/feature_list 由集成负责人汇总。

人工标签准备：先在用户提供的三个短视频上形成开发事件表和查询，核对事件是否确实可见；收集小时级录像与 10–20 代表录制会话，再冻结最终主组。两段 Atom 先视为同源；测试集不能用模型生成标签代替人工。

执行先后：F001 确认项目环境与合同编译；媒体／存储并行；随后模型／存储集成；检索；最后真实 gate。每个任务用 `sprint-template.md` 记录 owner、分支、验证和转交动作。正式 UI、Creative Planner、Rendering 与商业系统在原定质量门槛通过之后另立阶段任务。
