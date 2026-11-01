# 本地检查工作台前端

Owner：Codex frontend worker；日期：2026-10-04（Asia/Hong_Kong）。分支 `codex/inspection-frontend`，基线 `32d5a3b`；仅修改 `src/gamingcreator/ui/static/{index.html,app.js,style.css}` 和此记录。其他协作者负责后端和共享文档，禁止覆盖他们的修改。

## 合同与计划

依据 `docs/design-docs/inspection-workspace-api.md` 及原总方案 §12，交付无需 Node/框架/外部资源的本地三栏工作台：项目/run 选择、真实视频预览、自然语言查询候选、源时间轴、证据、转录、阶段和费用。查询与时间轴保留不同排序；跨项目/run 请求由取消和版本校验隔离。

选片篮只保存本地 project/run 下的区间选择；JSON/CSV 导出保留微秒和来源，导出前校验当前 run 的时间轴/候选。选择不是人工评分，不生成 MP4，不改变 F006。

## 实现检查点

- 已阅读 AGENTS、原方案 §12、Phase 0 规格、feature_list、共享 workflow 和使用手册；`./scripts/init.ps1 -CheckOnly` 通过（7 个特性）。
- 已应用 karpathy-guidelines：最小实现、明确验证、只修改独占文件。
- 前端按 API 冻结合同实现；后端 worker/root 提供服务和 HTTP 验证。
- 未调用远端 API，未安装依赖，未改系统或用户配置。
- 已实现项目/run 自动读取、视频区间播放、证据缩略图和音频、转录、源时间轴/标签筛选、检索候选、隔离片段篮和 JSON/CSV 下载。查询上限 4096 字符；导出带源 SHA256/configHash。
- 内置 Node REPL/VM JavaScript 编译通过；HTML 62 个唯一 ID，无缺失固定 DOM 引用，无 innerHTML。`git diff --check` 通过。
- 首个可集成提交为 `0d9e3c5`；只包含前端独占文件。后续修复限制了证据缩略图高度、清空切换时的旧素材信息，并避免失败查询被误记为选片检索来源。

## 验证与接手

使用 root 已隔离安装的 Python Playwright 1.63.0 和 `.tools/browsers` Chromium，未运行安装/sync。TEMP/TMP、临时 profile、合成素材、下载和截图均落在此 worktree 的 `.cache/frontend-browser/`。验证脚本为 ignored `check.py`，报告 `report.json`；桌面 1440px 与移动 390px 截图已人工查看。

21 项浏览器行为检查通过：自动读取 completed run、未知费用单列、安全 DOM 文本、候选与源时间不同排序、视频精确 seek/区间结束暂停、证据弹窗、JSON 微秒/身份/hash/证据/来源、旧候选重新匹配源事件、CSV 公式防护、描述/标签筛选、转录、空 query 刷新、不匹配的转录候选阻止整份下载、移除恢复下载、失败检索清除旧候选且不捏造来源、跨项目旧响应隔离、片段篮恢复、移动端无横向溢出、无 JS pageerror。JSON 未生成 humanLabels 或评分。

此结果只证明合成浏览器交互，不证明真实视频质量、F006 或小时级性能。完整 Python verify 和真实 PV/后端 HTTP 集成由 root 串行执行；worker 不宣称其已通过。所有权重、视频、截图和清单均未加入 Git。

检查中修正了两个 fixture 前提：严格 CSP 下 Playwright `wait_for_function` 使用箭头函数，字符串表达式会触发 unsafe-eval；媒体 fixture 必须实现 HTTP Range 才能可靠验证 seek。初次无 Range 的 fixture 曾复位到 0，修正后 4.045678s 结束暂停误差 <2ms。跨 run 取消会使测试服务端收到 WinError 10053，属于预期的已取消连接；报告中保留失败信息，不将其误称产品故障。

## 交付边界

页面只读已存在的运行/检索，不上传视频、不触发新分析、不写人工评测。源视频需要浏览器支持其编码。片段篮可跨查询保留，但必须与当前已读源事件或候选精确匹配，候选保留其原查询/模式/版本并写 `validatedAgainst`；无源事件的旧转录候选须重查原查询或移除。localStorage 被禁用时本次仍可选择/下载，页面提示无法跨会话保存。
