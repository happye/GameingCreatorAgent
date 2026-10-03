# 项目隔离环境

来源：用户在 2026-10-03 明确要求所有包与环境独立于本机、不影响系统。此规则对 Codex、Claude Code、Grok Build 及每个 worktree 相同。

| 内容 | 项目内路径 | 准备要求 |
| --- | --- | --- |
| .NET SDK | `.tools/dotnet/` | 便携安装、固定 .NET 10 SDK 版本及校验；用完整路径调用 |
| FFmpeg/ffprobe | `.tools/ffmpeg/bin/` | 固定构建和 DLL；分发许可证另评审 |
| Python 运行时 | `.tools/python/` | 项目管理的运行时，不安装系统 Python |
| ASR/Python 包 | `.venv/` | 使用项目运行时建立 venv，固定依赖；禁止全局 pip |
| NuGet/模型/下载缓存 | `.cache/` | 显式设置进程缓存目录，避免用户全局目录 |
| 运行证据与模型结果 | `artifacts/` | 忽略原视频/图片/响应和本地模型数据 |

先在当前 PowerShell 进程执行 `. ./scripts/env.ps1`，再使用项目内工具的完整路径。脚本仅设置当前进程的 SDK、NuGet 包/HTTP/插件/临时缓存、pip/uv、Hugging Face/PyTorch 和 TEMP/TMP 路径；禁止 Python 用户包与全局 pip。它不创建 Python 虚拟环境或安装依赖。`.tools`、`.venv`、`.cache` 均已 Git 忽略。[NuGet 缓存目录](https://learn.microsoft.com/nuget/consume-packages/managing-the-global-packages-and-cache-folders)

`init.ps1` 完整检查先载入这些进程设置，只接受项目内 .NET 10 SDK 与媒体工具；Python/ASR 的运行检查留给 F003，不把核心工具检查成功称为所有 Phase 0 环境就绪。

当前本地 FFmpeg/ffprobe 与 DLL 已从已存在的安装复制到项目内作为实验工具，未改动原安装；.NET SDK、Python/ASR 环境仍待 F001 准备。新机器不能依赖这些忽略文件，需要按固定版本与校验重建。并行 worktree 分别准备虚拟环境，或明确使用同一只读、固定版本工具副本；包和输出不共享可变目录。

禁止全局安装、自动改系统 PATH、改用户工具配置或自动安装 GPU 驱动。没有合适 GPU 时先用项目内 CPU ASR 验证。`global.json`、锁文件和工具校验清单须跟代码一起维护；密钥仅走进程环境或项目忽略的本地密钥存储。
