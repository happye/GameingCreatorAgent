# 本地检查工作台前端

Owner：Codex frontend worker；日期：2026-10-04（Asia/Hong_Kong）。分支 `codex/inspection-frontend`，基线 `32d5a3b`；仅修改 `src/gamingcreator/ui/static/{index.html,app.js,style.css}` 和此记录。其他协作者负责后端和共享文档，禁止覆盖他们的修改。

## 合同与计划

依据 `docs/design-docs/inspection-workspace-api.md` 及原总方案 §12，交付无需 Node/框架/外部资源的本地三栏工作台：项目/run 选择、真实视频预览、自然语言查询候选、源时间轴、证据、转录、阶段和费用。查询与时间轴保留不同排序；跨项目/run 请求由取消和版本校验隔离。

选片篮只保存本地 project/run 下的区间选择；JSON/CSV 导出保留微秒和来源，导出前校验当前 run 的时间轴/候选。选择不是人工评分，不生成 MP4，不改变 F006。

## 当前检查点

- 已阅读 AGENTS、原方案 §12、Phase 0 规格、feature_list、共享 workflow 和使用手册；`./scripts/init.ps1 -CheckOnly` 通过（7 个特性）。
- 已应用 karpathy-guidelines：最小实现、明确验证、只修改独占文件。
- 前端按 API 冻结合同实现；后端 worker/root 提供服务和 HTTP 验证。
- 未调用远端 API，未安装依赖，未改系统或用户配置。
- 已实现项目/run 自动读取、视频区间播放、证据缩略图和音频、转录、源时间轴/标签筛选、检索候选、隔离片段篮和 JSON/CSV 下载。查询上限 4096 字符；导出带源 SHA256/configHash。
- 内置 Node REPL/VM JavaScript 编译通过；HTML 62 个唯一 ID，无缺失固定 DOM 引用，无 innerHTML。`git diff --check` 通过。
- 准备使用 root 已隔离安装的 Playwright/Chromium，在此 worktree 的 `.cache/` 做浏览器 fixture 验证；不运行安装/sync。此提交为可集成检查点，尚未记录真实浏览器验证。

## 验证与接手

实现后使用内置 Node REPL 的 VM 编译检查 JavaScript、检查固定 DOM 引用与 HTML 结构；若可用浏览器环境，再记录交互验证。完整 Python verify 和后端 HTTP 集成由 root 串行执行。当前尚未记录实现后检查，不能宣称浏览器验收通过。
