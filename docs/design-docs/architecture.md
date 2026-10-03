# Phase 0 架构基线 v1

状态：2026-10-03 完成反向审查后的实施基线；性能和检索质量仍待实测。依据原方案 §15–20、49–56、69–71；详见 [审查报告](../exec-plans/reverse-review-2026-10-03.md) 与 [工程合同](./phase-0-engineering-spec.md)。

## 工程与依赖

```mermaid
flowchart TD
    CLI[Cli 组合入口] --> APP[Application 用例与 Provider 合同]
    CLI --> INFRA[Infrastructure 媒体、模型和 SQLite 适配]
    APP --> DOMAIN[Domain 领域记录与时间约束]
    INFRA --> APP
    INFRA --> DOMAIN
```

初始工程为 `src/GamingCreator.{Cli,Application,Domain,Infrastructure}/`，测试镜像组织。目标 `net10.0`，第一工程任务安装/固定可用 SDK 并建立构建、格式与测试命令。Media、ASR、Vision、Timeline、Retrieval 先作为模块；在出现独立生命周期或复用理由时再拆工程。

CLI 只解析输入、组装依赖和输出结果；Application 编排 stages；Domain 无厂商 SDK、SQL 或进程调用；Infrastructure 实现 Application 的 ports。未来 Windows Desktop 接入 Application，模型与数据库不直接进入 UI。

## 数据流与状态

本地源文件 → hash/probe → 带 PTS 的视觉证据＋音频 → 本地 ASR＋视觉 Provider → 校验后的 SemanticEvent → SQLite → 检索/重排/去重 → CandidateClip。

阶段：`Probe → Evidence → ASR → Vision → Persist → Index`；状态 `Pending/Running/Completed/Failed/Cancelled/Interrupted`。无音轨/无语音是 ASR 的显式结果，不是异常终止。只从完整可用 run 搜索；每项目同时只允许一个分析写入者。

证据和原始响应保存在本地项目工作目录；SQLite 存路径、hash、语义结果、版本、checkpoint 和调用账本。源视频保持原位。先完成临时文件写入并校验，再短事务登记；恢复时核对文件与数据库。任何模型或 FFmpeg 调用均不持有数据库写事务。

## 模型与检索边界

首个视觉实验使用 DeepSeek `deepseek-flash` 图像序列；本地 ASR 实现与替换对照属于 F003。`IVisionModel`、`IASRModel`、`IEmbeddingModel` 定义可替换合同；需要查询扩展或重排时用 `ILLM`。Provider 声明输入能力和实际模型修订，不能只声明“OpenAI 兼容”。

先建立可解释词法检索基线，再比较语义扩展/embedding 与重排方案；embedding 用量、维数和版本独立记录。检索只输出有源证据的片段，不把叙述模型的自由文本直接当确定机制。强模型升级率是实验参数，不固定为 10%。

## 架构检查

F001 建立项目引用方向测试与格式工具；F004 检查 SQLite 与文件原子边界、断点恢复；F003 检查 Provider 替换和未知 usage；F005 检查时间码、稳定排序和重复事件；F006 执行独立 benchmark。架构基线可据失败证据修订，修订保留原因、影响与版本。
