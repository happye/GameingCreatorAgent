# F000：反向审查与 Phase 0 工程基线

日期：2026-10-03（Asia/Hong_Kong）。Owner：Codex `/root`；分支 `main`。状态：文档审查验收完成，Phase 0 产品 gate 未完成。

## 范围与验收

严格遵循原方案 §70：先从技术可行性、架构、模型能力、视频处理、商业化、工程风险六个方面审查，再形成 §71 的工程规格与开发任务依赖图。

本轮验收：风险与证据写入仓库；补齐 CLI、数据、Provider、成本、恢复、采样与 benchmark 合同；记录能实际运行的本地验证以及未具备条件的模型/真实录像实验。F000 文档验收不等于 Phase 0 产品验收，后者仍须真实素材达到 Top-10 ≥70%。

## 分工

- `/root`：集成负责人，拥有审查报告、工程规格、执行计划、特性清单、验证脚本和交接文件的写入权。
- `model_media_review`：模型与媒体审查，只读。
- `architecture_review`：架构与合同审查，只读。
- `acceptance_cost_review`：质量/成本与商业化审查，只读。
- 审查 Agent 不编辑共享工作树；本轮无多个编码 Agent 并行修改文件。

## 验证计划

1. 检查项目内运行时、FFmpeg/ffprobe 与现有素材。
2. 在本地合成媒体上验证探测、抽帧、音频提取和无音轨处理，保存结果与限制。
3. 查证官方 Provider/ASR/存储行为；把支持能力与实测性能分开。
4. 明确真实游戏录像、人工标签、可调用模型是端到端检索验收的必需条件。
5. 交付后只将 F000 标为通过；没有跑通真实检索和人工标注的 F001–F006 保持未验收。

## 输入与实际结果

用户提供 `GameVideos/` 测试素材、DeepSeek 可调用能力、隔离环境要求与 GitHub 版本库。三个短视频共约 214.86 秒；无小时级原始录像和正式人工 benchmark 标签。凭据仅在请求进程使用，没有保存至文件。

已交付 [六方向审查](./reverse-review-2026-10-03.md)、[工程合同](../design-docs/phase-0-engineering-spec.md)、[验证证据](./phase-0-validation-2026-10-03.md)、[开发依赖与文件归属](./phase-0-plan.md)。原方案文件及产品方向未改变；按用户语言补充采纳 [ADR-001 Python 基线](../design-docs/adr-001-phase-0-language.md)。

## 验证与评审处理

- `./scripts/init.ps1 -CheckOnly`：通过，7 项特性；完整检查从早期 .NET 检查改为 Python/uv/venv 检查，缺环境时退出 1，未安装全局依赖。
- `./scripts/test-media-spike.ps1 -Synthetic`：项目内 FFmpeg 有音轨复测通过；无音轨及三个真实素材短窗实验通过。
- `./scripts/test-retrieval-score.ps1`：固定分母、缺项、重复、负例与无效评级回归通过。合成报告仍为 `phase0QualityVerified=false`。
- PowerShell AST 语法与包/模型缓存及 TEMP/TMP 进程路径隔离检查通过。
- 专项评审修复：严格整数评级及布尔值回归；pip/uv/模型/临时缓存全部归项目；完整检查只认项目 CPython 3.13 venv；embedding 唯一键包含 Provider/模型/空间；未确认修订的缓存不跨 run 复用。补充只读语言评审选择 Python，并显式禁用 uv 注册与全局链接。
- DeepSeek 三次请求、15 帧结构校验成功，估算上界合计 ¥0.024076；未将此视为检索质量、源小时成本或正式人工标签。

## 转交

F000 `passes:true` 仅表示审查交付满足文档验收。F001–F006 `passes:false`；没有 CLI、ASR、SQLite 或检索实现。下一 owner 从 F001 开始：在独立 worktree 登记范围，固定项目 uv/CPython 3.13/venv，建立四层包与合同/输入测试。详细入口见根 `HANDOFF.md`；本轮提交与文件状态以 Git 为准。
