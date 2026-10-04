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
