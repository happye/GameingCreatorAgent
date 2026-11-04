# HANDOFF（覆盖快照）

当前状态只看 `STATUS.md`；本页是接手提示。每次会话结束时整页覆盖，不要追加。

## 最近一次会话（2026-11-03，Claude Code）

在新工作台 `/studio` 上做完了 sprint 第 3–6 步，逐步结果见 `docs/exec-plans/sprint-studio-workbench.md`：

- **剪辑**：镜头裁剪、速度、转场、排序、删除；保存版本；一句话修改先预览后应用；替换镜头（片段篮优先）。
- **声音**：
  - 旁白可用本机 Windows 语音，或云端 CosyVoice（默认 龙安洋）。
  - 云端每次合成都要用户在界面上确认费用；月上限 ¥5；同样的文字和音色不重复付费。
  - 账单记录：`artifacts/billing/narration-tts.jsonl`。
  - 配乐支持上传和音量调节。
- **素材**：片段搜索和片段篮；方案可以只用篮里的片段（方案请求的 `eventIds`）。
- **发布**：标题、简介、标签，封面帧，平台包 zip 下载。不会自动发布。
- **技术债**：TD024 已处理（修了 attack 标签被语义闸门挡掉的问题，另外两条测试按 TD004 的精度设计改写）；TD023 已处理（窗口缓存改由端口注入，架构测试的放行名单已清空）。全量 verify：4678 通过；两条失败已查明，一条是本地数据测试选错记录（已修），一条是 Windows 文件锁导致的偶发失败。

## 下一位接手先做什么

1. 读 `STATUS.md` 的“下一步”，再看 sprint 文档末尾的待办。主指标是 `docs/exec-plans/journeys.json` 里的端到端流程，不是功能数。
2. 等用户在新工作台走完一次 J1（剪辑 → 声音 → 导出 → 发布区打包），把结果记进 journeys.json，再按 sprint 第 6 步删除旧页面（`/`、`/creation`）和它们的模拟测试。没有用户确认之前，不要删。
3. 剩下的开放技术债（TD002–TD009）都需要用户人评或真实素材，不要在没有人评的情况下调阈值或继续加别名闸门。

## 工作方式（这次会话吃过的亏）

- **界面功能**：汇报前，用浏览器在 `http://127.0.0.1:8765/studio` 按用户的点法走一遍（例如先选中镜头，再去找功能）。重启工作台后，已打开的页面要刷新。
  - 2026-11-03 声音面板只在没选镜头时显示，用户找不到，被认为是瞎编汇报。
- **测试**：迭代时跑 `./scripts/test-affected.ps1 -Browser`（改了界面就带 `-Browser`）。跑测试期间不要改文件，否则会出现假失败。
- **在 bash heredoc 里用 Python 改文件时**，`\\x00` 一类的转义会变成真 NUL 字节。改动较大时，把脚本写到 `.cache/scratch/*.py` 里再运行。
- **重启 8765**：先结束占用端口的进程，再在终端运行 `scripts/start-workspace.ps1 -NoBrowser`。从 agent 的后台 shell 启动的进程会随 shell 退出。
- **云端语音**：只有在启动工作台的那个进程环境里有 `DASHSCOPE_API_KEY` 时才可用。Key 由用户自己设置，任何文件里都不要写。

## Codex 接手

- 只用 `.codex/agents/` 里那一套 9 个角色（`task_*`、`harness_*`）。之前由 Claude 角色转出来、未提交的 `gc-*.toml` 是重复的一套，已移到仓库外 `GameingCreatorAgent-archive/`；2026-11-04 又被某个工具重新生成过一次，已再次移出并加入 `.gitignore`。不要再生成或提交这套文件（用户已确认只保留 task_*／harness_*）。
- 分工表：`docs/references/codex-agent-routing-guide.md`（精简版；10 月的记录已移到 `docs/archive/references/`）。

## 不要做

- 不要重跑长钟馗 launcher；已有标注和付费尝试保留，不重做。
- 不要为了“补文档”单独提交；STATUS 只在里程碑或会话结束时更新一次。
- 已删除分支的备份在仓库外：`G:\Tools\ChatGPTRepo\GameingCreatorAgent-archive\2026-11-01-branch-backup\`，不要删。
- 推送走 Clash 代理 `127.0.0.1:7890`，不要 force。
