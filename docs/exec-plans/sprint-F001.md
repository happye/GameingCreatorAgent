# F001：隔离 Python 环境与可运行核心骨架

日期：2026-10-03（Asia/Hong_Kong）。Owner：Codex `/root`；分支 `codex/F001-core`。

## 范围与归属

根 agent 独占代码、测试、依赖清单、安装/验证脚本和共享交接的写入权。合同与环境 reviewer 只读；没有多个编码会话共享修改。本项依赖已验收 F000 和 ADR-001。

交付：项目内 portable uv/CPython 3.13/venv 的固定版本与校验；可安装四层包；CLI 命令入口/输入错误；领域时间与 Provider/账本数据合同；pytest/Ruff/mypy/导入方向检查。有效 analyze/search 在处理链路落地前明确返回尚未实现，不产生虚假成功或数据库。

## 验收计划

1. 固定官方工具/运行时及构建/开发依赖，不全局安装、不登记 Python、不创建用户全局链接。
2. 用项目解释器创建 venv，锁依赖并构建 wheel；记录工具/源码/产物 hash。
3. 输入不存在、目录、不读、零长度和无效配置时退出 2/3，JSON 诊断走 stderr，项目目录不被创建；help/version 可运行。
4. 验证 Int64 微秒区间、未知用量/成本、类型化 ports、取消上下文和分层导入；正常单位测试不联网/不收费。
5. 仅达到 F001 条件后标记 true；F002–F006 不由骨架验收代替。

## 实际交付与验收

F001 已验收。`src/gamingcreator` 可安装，四层结构和 typed DTO/Protocol 基础已落实；`config.example.json` 与 CLI 校验不接受凭据字段。正常处理仍明确退出 3，不创建输出；没有媒体/模型/SQLite/检索执行链路。

| 检查 | 实际结果 |
| --- | --- |
| 官方工具归档 | uv 0.12.22 ZIP 与 CPython 3.13.16/build 20261001 TAR 的 SHA256 均符合 `toolchain.json`；解压前检查 |
| 项目环境 | `.tools` runtime + `.venv`，标准 x64/GIL；逐文件 receipt hash、精确版本和 `include-system-site-packages=false` 通过 |
| 开发依赖 | `uv.lock` 固定 17 项（含本包），pytest 9.1.1、Ruff 0.16.10、mypy 2.4.0、hatchling 1.32.4 |
| `./scripts/verify.ps1` | 17 个 Python 文件格式/静态导入通过；严格 mypy 检查 14 个源/Provider fake 文件；50 个 pytest 测试通过（0.61s） |
| 重复离线 wheel | 两次 SHA256 一致：`4b2b9a5d0e76d8a18b048436e1fbc192323540f280728be8bc84783890b57667`；审计 18 项仅含包/metadata，含 py.typed |
| 安装入口 | 模块 CLI help、console --version 成功；坏输入/无效配置/续跑互斥均按合同失败，无项目输出 |
| 离线复用 | 从仓库父目录执行 setup -Offline 成功，故意继承外部 UV_PROJECT/UV_WORKING_DIR 被清除；调用目录恢复 |
| 主机边界 | 用户/系统环境变量及 HKCU/HKLM/WOW6432Node 的 Python 子树 SHA 指纹前后不变；仅报告 hash，不保存变量值 |
| `./scripts/init.ps1` | scaffold 7 特性、精确工具/venv 和本地媒体工具检查通过 |

普通测试全部离线且不调用模型。归档/运行时/包缓存、wheel、环境指纹保存在 Git 忽略目录；他机根据清单重建，不能依赖 Git 携带这些文件。uv 的缓存位于源码目录警告已人工核对：wheel 无缓存/媒体/配置内容；Hatch 仅打包 `src/gamingcreator`。

## 审查、修复与局限

合同和环境各由只读 Agent 复核，根 Agent 唯一编码。修复了包 alias 导入检查遗漏、负 Infinity 参数解析、argparse.error 的 Never 类型、结果状态/错误约束、继承 uv 目录覆盖以及验证脚本解释器选择。

初始化首次失败原因：Python `-I` 忽略 PYTHONPYCACHEPREFIX，探针/venv 重写了项目 runtime 内 46 个 `.pyc`，使逐文件 receipt 检查失败。改用 `-I -B`；从已校验原归档恢复文件后所有检查通过。可复用教训写入隔离环境文档；不创建本机全局 skill 记忆目录。

本项不验证真实 Provider replacement、异步超时/worker 回收、源 PTS 映射、完整账本或模型 schema；这些仍归 F002/F003/F004。F002–F006 保留 false；Phase 0 人工 U10 gate 未测量。

## 后续动作

F002 先实现 ffprobe/FFmpeg 源时间映射和可取消进程；F004 可在独立 worktree 并行。模型包/权重留给 F003。继续前检查实际分支与 assignments/HANDOFF，不重复初始化已验收核心。
