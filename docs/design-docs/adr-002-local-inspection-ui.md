# ADR-002：本地检查页使用项目内 Python

状态：已接受，仅用于检查已有时间线。日期：2026-10-04。用户随后明确要求继续完善基础交互；本地浏览/选片功能据此扩展。

ADR-001 要求未来界面另写决定，并且不改写已验收的分析链路，也不安装 .NET。本决定只增加一个本地检查页。

检查页由项目虚拟环境里的 `python -m gamingcreator.ui` 提供，启动命令是 `./scripts/run-ui.ps1`。它读取 SQLite 里已经写下的事件，并调用与 `run-demo.ps1` 相同的 `execute_search`。时间轴按源时间排序；检索结果保持搜索返回的分数顺序。未完成 run 的新事件在同一进程里再次读取就能看到，不等 `semantic_timeline.json`。

基础检查工作台增加原视频Range预览、按真实源区间跳转、证据查看、时间轴筛选、运行/费用状态、按run隔离的选片与JSON/CSV清单下载。依旧使用项目内Python标准库HTTP服务和零依赖HTML/CSS/JS，绑定127.0.0.1；不需要全局Node、.NET或前端包安装。合同见 [inspection-workspace-api.md](./inspection-workspace-api.md)。

这不是商业桌面程序，不渲染成片、不发布、不结算。它也不代替 F006 的独立人工 U10。后续桌面EXE仍须另立决定。
