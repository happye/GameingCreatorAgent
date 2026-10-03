# ADR-001：Phase 0 使用 Python 模块化核心

日期：2026-10-03。状态：已采纳，替代初版 .NET 工程基线；应用代码尚未创建。

## 约束与依据

原总方案 §13 根据开发者背景推荐 C#/.NET。用户在 2026-10-03 明确语言不强制，可选择更适合方案；此决定覆盖该技术推荐，不改变产品方向、阶段范围或质量门槛。跨 Agent 以本 ADR 和更新后的规格为准，不重新按原推荐安装 .NET。

Phase 0 核心风险是采样、模型、时间映射与真实检索质量；当前没有桌面界面或已有 C# 代码。所有环境必须项目隔离，多 Agent 需要清晰接口、可重复验证与独立文件归属。

## 比较与决定

| 方案 | 当前收益 | 当前代价 | 决定 |
| --- | --- | --- | --- |
| Python 核心 | 直接接 ASR/embedding/评测；一个语言运行时 | 必须强制类型、依赖边界与锁版本；桌面分发仍需验证 | Phase 0 采用 |
| C# 核心＋Python ASR | 编译期约束、Windows 集成 | 两套环境，IPC schema、取消与恢复协议 | 后续有实际需要再评估 |
| TypeScript 核心 | 适合 Web UI 与交互 | ASR 仍需另一个运行时，当前无正式 UI | 留作后续 UI 候选 |
| Rust 核心 | 资源控制、原生热点优化 | 模型实验适配与开发成本，暂无测量证明热点 | 有性能证据再局部引入 |

采用标准 CPython 3.13（非 free-threaded 版本）作为兼容基线，具体安全补丁和发行构建在 F001 固定、校验。faster-whisper 官方提供 Python/CPU int8 接口；CTranslate2 已有 CPython 3.13 Windows x64 wheel，但完整 ASR 依赖和本机启动仍未验证。[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[CTranslate2 文件](https://pypi.org/project/ctranslate2/#files)、[Python 生命周期](https://devguide.python.org/versions/)

这是工程取舍，不是 Python 更快的实测结论；视频解码、原生推理与网络耗时仍按配置测量。未来 UI 可用 Python、TypeScript 或 C#，需另写 ADR；优先复用核心与版本化数据合同，不因 UI 改写已验收处理链路。

## 实施影响

- `src/gamingcreator/{cli,application,domain,infrastructure}/` 保留四层方向。领域记录用 dataclass/类型标注；Application ports 用 Protocol；基础设施负责进程、模型和 SQLite。
- F001 建立 `pyproject.toml`、`uv.lock`、`.python-version`、pytest/Ruff/mypy 与导入边界检查；本地模型依赖在 F003 增加，不先装全部 ML 栈。
- ASR 用可终止 worker；网络 Provider 可异步，不能把同步推理阻塞事件循环。Python `int` 在领域边界检查 SQLite Int64 范围。
- portable uv/Python 在 `.tools/`，全部包在 `.venv/`；设置项目缓存，禁用 uv Windows 注册和全局链接。固定 uv 版本必须支持这些隔离开关。[uv 环境变量](https://docs.astral.sh/uv/reference/environment/)
- CLI/JSON、时间码、Provider 账本、恢复、缓存、SQLite 与 Top10 gate 合同不变；更换语言不构成任何特性通过证据。

## 验证与回退

F001 验证仅项目工具可重建环境、类型/格式/边界/输入测试通过；F003 验证 CPU ASR 及依赖。若 wheel、原生运行库或性能实验失败，记录失败环境与替代方案后修订 ADR，不全局安装、不悄悄降验收门槛。目前没有安装 Python/uv，也没有 ASR 或 Python 构建通过记录。
