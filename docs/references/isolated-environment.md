# 项目隔离环境

来源：用户在 2026-10-03 明确要求所有包与环境独立于本机、不影响系统。此规则对 Codex、Claude Code、Grok Build 及每个 worktree 相同。

| 内容 | 项目内路径 | 准备要求 |
| --- | --- | --- |
| portable uv | `.tools/uv/` | 下载固定版本便携包并校验；禁止全局安装脚本 |
| FFmpeg/ffprobe | `.tools/ffmpeg/bin/` | 固定构建和 DLL；分发许可证另评审 |
| CPython 3.13 | `.tools/python/` | 项目管理的标准运行时，固定补丁/发行构建，不安装系统 Python |
| 应用/开发/ASR 包 | `.venv/` | 使用项目运行时建立 venv，uv.lock 固定依赖；禁止全局 pip |
| 包/模型/下载缓存 | `.cache/` | 显式设置进程缓存目录，避免用户全局目录 |
| 运行证据与模型结果 | `artifacts/` | 忽略原视频/图片/响应和本地模型数据 |

先在当前 PowerShell 进程执行 `. ./scripts/env.ps1`，再使用项目内工具的完整路径。脚本仅设置进程内 pip/uv、Hugging Face/PyTorch、Ruff/mypy 和 TEMP/TMP 路径；禁止 Python 用户包与全局 pip。它不创建虚拟环境或安装依赖。`.tools`、`.venv`、`.cache` 均已 Git 忽略。

uv 在 Windows 默认可注册 Python；必须固定支持隔离开关的版本，使用 `UV_PYTHON_INSTALL_REGISTRY=0`、`UV_PYTHON_INSTALL_BIN=0` 和 `UV_PYTHON_NO_REGISTRY=1`（uv ≥0.11.8）。工具/可执行链接目录也指向 `.tools`，解释器只接受 managed 模式；创建 venv 显式提供项目解释器，不调用系统 `python`/`py` 兜底。[官方环境变量](https://docs.astral.sh/uv/reference/environment/)

`init.ps1` 完整检查先载入进程设置，只接受项目内 uv、来自 `.tools/python` 的 CPython 3.13 venv 与媒体工具；依赖锁和 ASR 运行检查分别属于 F001/F003，不把核心工具可执行称为所有 Phase 0 就绪。

当前 FFmpeg/ffprobe 与 DLL 已从现有安装复制到项目内作实验工具，未改动原安装；uv/Python 与包环境仍待 F001，ASR 权重在 F003 准备。新机器不能依赖这些忽略文件，需要按固定版本与校验重建。每个 worktree 分别准备 venv/缓存，或明确共享只读固定工具；不共享可变包目录。

禁止全局安装、自动改系统 PATH、改用户工具配置或自动安装 GPU 驱动。先用项目内 CPU ASR 验证；`pyproject.toml`、`uv.lock`、`.python-version` 和校验清单跟代码维护，密钥只走进程环境或忽略的本地存储。Phase 0 不需要 .NET，依据 [ADR-001](../design-docs/adr-001-phase-0-language.md)。
