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

`toolchain.json` 固定 uv 0.12.22、标准 x64 CPython 3.13.16/build 20261001 与官方归档 SHA256；`.python-version` 与清单一致。`./scripts/setup-env.ps1` 从官方 GitHub asset API 下载，先校验再解压；直接解压 portable Python，不运行安装程序或 Python 注册命令。运行时逐文件 hash 和归档来源记在忽略的 `.tools/toolchain-receipt.json`。

uv 注册/链接仍以 `UV_PYTHON_INSTALL_REGISTRY=0`、`UV_PYTHON_INSTALL_BIN=0`、`UV_PYTHON_NO_REGISTRY=1` 禁用。所有调用指定项目 uv、`--no-config`、项目解释器与 `--no-python-downloads`；清除继承项目目录/镜像覆盖变量。初始化探针用 `-I -B`，避免隔离模式忽略缓存变量后改写运行时字节码；普通开发进程的缓存仍由 `env.ps1` 指向 `.cache`。[官方环境变量](https://docs.astral.sh/uv/reference/environment/)

`setup-env.ps1` 使用显式项目解释器建立不含系统包的 `.venv`，按 `uv.lock` 同步；`-Offline` 复用已验证归档和包缓存。只有依赖 owner 可用 `-CreateLock` 修改锁；普通安装不能默默升级。支持从其他目录启动并还原当前目录。下载失败保留项目内 `.partial` 以续传；hash 错误停止，不执行可疑文件。不要改用全局安装或盲删本机目录。

`init.ps1` 核对精确工具版本、运行时 hash、x64/标准 GIL ABI、venv 来源和系统包隔离，再检查媒体工具；`verify.ps1` 检查锁、类型、格式、测试和离线构建。ASR/原生库/权重属于 F003，不把 F001 工具可执行称为所有 Phase 0 就绪。

当前 FFmpeg/ffprobe 与 DLL 已从现有安装复制到项目内作实验工具，未改动原安装；Python 工具与开发包已验收 F001。新机器需运行 setup 并另行准备固定 FFmpeg 副本。每个 worktree 分别准备 venv/缓存，或明确共享只读固定工具；不共享可变包目录。

F001 前后核对的用户/系统环境变量及三处 Python 注册表子树指纹均未变化。这是指定边界的检查，不是全系统变更监控。不得自动安装 VC++ 运行库、CUDA 或驱动；F003 原生库缺依赖时记录失败，使用合法项目内方案或替换实现。

禁止全局安装、自动改系统 PATH、改用户工具配置或自动安装 GPU 驱动。先用项目内 CPU ASR 验证；`pyproject.toml`、`uv.lock`、`.python-version` 和校验清单跟代码维护，密钥只走进程环境或忽略的本地存储。Phase 0 不需要 .NET，依据 [ADR-001](../design-docs/adr-001-phase-0-language.md)。
