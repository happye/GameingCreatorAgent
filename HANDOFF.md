# 当前交接

更新时间：2026-10-04（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共享此记录；历史见 `progress.md`，验收见 `feature_list.json`，产品边界见原总方案 §58/71。

## 当前结果

Phase 0 CLI 闭环已实测：本地视频 → FFmpeg/ASR → 逐窗口视觉事件 → SQLite/semantic_timeline.json → 词法/本地 E5 语义检索 → 时间码和人工评测报告。本地检查页用 `./scripts/run-ui.ps1`，不是商业编辑器。价格快照配置已实现，不需要用户另找价目；搜索现有 Completed run 不需要密钥或联网。

当前root在 `codex/inspection-workspace`；Grok基线与初步工作台计划已保存检查点 `32d5a3b`（561pass）。完整CLI代码检查点 `19cfe58` 及文档 `d6eb311` 已在origin/main；本轮工作台功能仍在实现，远端状态以 `git log -1` 和 `git status --short` 为准。旧F003分支仅为历史。F003/F005技术合同已验收；F006工具已实现，独立人工U10尚未通过。

## 真实证据

- 完整 run：`f76f5d6495314c04ae04083614d4afd6`，项目 `artifacts/demo-phase0`；漫画群星 PV 时长 95.175874s，24 窗口全覆盖、111 条视觉事件、0 条转录。逐次 API 费用合计估算 ¥0.06246088，非账单确认。
- 初次 run `823799e10a0440e8aec8b78b603bec57` 在 2/24 窗口后因 schema 拒绝停止，10 条事件已保存，费用估算 ¥0.01163912，无未知费用。本轮两次实验合计估算 ¥0.0741。旧响应没有保留，不能补称具体失败字段。
- `artifacts/demo-phase0/demo-validation.json`：早先三查询 × lexical/semantic/hybrid 的重复稳定性记录。2026-10-04 默认 hybrid 复跑后，中文攻击查询与英文 `Find clips of fighters attacking each other in the arena` 都返回 28–29、31–32、30–31 秒带证据区间；汽车维修查询 hybrid 为 0 条。pure semantic 对汽车维修负例的误召回仍在。不可把这些观察写成真实质量 gate。
- `demo-benchmark-input.json` 和 `demo-cli-benchmark-report.json` 是未标注开发报告，qualityGate=null；CLI 正确退出6。未来人工清单模板在 `templates/phase0-benchmark.example.json`。
- worker 文本/真实本地模型证据在 `docs/exec-plans/sprint-F005-worker.md`；固定batch=1消除量化冷/热漂移。早期负例及批次失败报告未覆盖。ASR 真实语音、无语音、取消/超时证据保留于 sprint-F003 和此前复核。

## 继续工作

使用说明见 `docs/references/user-manual.md`，最短命令见 `docs/references/demo-quickstart.md`。本机现有 run：`./scripts/run-demo.ps1 -Run f76f5d6495314c04ae04083614d4afd6 -TopK 3`。新视频用 `-Video <本地路径>`；新机先 `./scripts/setup-demo.ps1`，另备固定 FFmpeg。ignored素材、DB和权重不随Git克隆。

当前代码：config v2含价格/采样/ASR/提示版本hash；5帧窗口重叠1；调用前登记；完成窗口不重发；显式 `analyze --resume` 保留原配置、全部费用与请求/帧累计。未提交/未知收费远端调用须 `--retry-uncertain`，不会自动补零或重试。schema3为13张STRICT表，使用原连接owner线程与事务；转录候选 event_id可NULL但必须真实同源音频证据。

最终 ./scripts/verify.ps1退出0：557 passed/0skip（51.13s）、Ruff、mypy42源文件、CLI通过；两次wheel SHA256 90c27fba9af76a86a35c191d684d0c5160baf07b49a4e8e90eb0356bf6eb4a75，41条package/dist-info，无模型/原生DLL/视频。setup-demo.ps1 -Offline已实际通过。首轮6fail/2err已修：legacy schema硬编码改为当前版本，固定fixture调用前登记pin，子进程显式-X utf8并正常finally关闭；生产合同未放松。五项用户/系统环境及Python注册表指纹未变，不代表全系统监控。所有workers和文档已冻结/整合；root工作树为最终来源。

2026-10-04 用户要求 Codex 接续 Grok 检查页并完善基础功能。当前 owner 为 Codex root；计划与持续验证见 `docs/exec-plans/sprint-inspection-workspace.md`。Grok 改动已保留并复核：恢复28个归档校验的项目内stdlib pyc后，完整verify为561passed/0skip、Ruff/mypy47文件/重复wheel通过。HTTP错误码缺陷已复现，尚待修复。接下来补项目/运行选择、原视频预览、片段跳转、证据查看、时间轴筛选、片段选择及JSON/CSV清单导出，F006仍false。

## 环境与接续规则

全部工具、原生库、包、模型和缓存只在 `.tools/`、`.venv/`、`.cache/`。`. ./scripts/env.ps1` 只改当前进程；禁止全局安装、改用户/系统设置。ASR和E5 worker用 -I -B、项目内CRT/hash与离线固定权重；uv.lock已含retrieval extra。

密钥仅走进程 DEEPSEEK_API_KEY，不复制聊天凭据、不写文件、不输出。source视频字节、DB、模型和实验响应均忽略。Codex/Claude/Grok遵循AGENTS和共享workflow；语言决定仍Python Phase0，未来UI另立ADR。

网络或额度中断前持续保存具体检查点，先核对分支/未提交修改和模块归属，不覆盖其他owner。旧scratch worktrees全部冻结；当前root和本轮worker归属见assignments。
