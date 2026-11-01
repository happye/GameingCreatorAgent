# HANDOFF（覆盖快照）

当前状态只看 `STATUS.md`；本页是接手提示。

## 最近一次会话（2026-11-01，Claude Code）

harness 复盘落地：
- 主指标改为端到端流程 `docs/exec-plans/journeys.json`；`scripts/status.py` 改为从源文件计算，加了 `--check`，CI 会运行。
- 测试分层：新增 `scripts/test-affected.ps1`；测试按 browser、local_data、ffmpeg 自动打标；verify 默认不再做 wheel 构建（改由 `-Release` 触发）；toolchain 检查不再哈希 `__pycache__`。
- 归档了 236 份历史 sprint、报告和快照，链接全部改写，断链数为 0。
- 格式和类型门禁已恢复：11-01 的小提交留下了 27 个未格式化文件和 6 个 mypy 错误。
- main 原有 51 个失败测试（11-01 小提交带入）：37 个是测试里的假渲染器没跟上 `presentation` 参数（TD022，已修）；4 个检索否定用例回归（TD024，xfail 隔离）；knowledge_import 放错层已移到 infrastructure，analysis 的缓存分层违规以 TD023 显式放行；1 个 HTTP 测试漏关 socket 已修。

## 接手注意

- 先加载 `. ./scripts/env.ps1`。推送走 Clash 代理 `127.0.0.1:7890`，不要 force。
- 不要重跑长钟馗 launcher；已有标注和付费尝试保留，不重做。
- 已删除分支的备份在仓库外：`G:\Tools\ChatGPTRepo\GameingCreatorAgent-archive\2026-11-01-branch-backup\`，含全部 78 个本地分支（其中 40 个与 main 不同，只此一份）和 8 个孤儿 worktree 副本，不要删。
