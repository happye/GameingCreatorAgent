# 当前交接

更新时间：2026-10-04（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共享此记录；历史见 `progress.md`，验收见 `feature_list.json`，产品边界见原总方案 §58/71。

## 当前结果

Phase 0 CLI 闭环已实测：本地视频 → FFmpeg/ASR → 逐窗口视觉事件 → SQLite/semantic_timeline.json → 词法/本地 E5 语义检索 → 时间码和人工评测报告。没有正式 UI。价格快照配置已实现，不需要用户另找价目；搜索现有 Completed run 不需要密钥或联网。

当前root在 `main`。已验证代码检查点 `19cfe58` 成功推送 `origin/main` 与 `origin/codex/phase0-demo`；main已从ca0394e快进整合模型与Demo，不覆盖远端其他修改。最新文档提交/工作树以 `git log -1` 和 `git status --short` 为准；旧F003分支仅为历史。F003/F005技术合同已验收；F006工具已实现，独立人工U10尚未通过。

## 真实证据

- 完整 run：`f76f5d6495314c04ae04083614d4afd6`，项目 `artifacts/demo-phase0`；漫画群星 PV 时长 95.175874s，24 窗口全覆盖、111 条视觉事件、0 条转录。逐次 API 费用合计估算 ¥0.06246088，非账单确认。
- 初次 run `823799e10a0440e8aec8b78b603bec57` 在 2/24 窗口后因 schema 拒绝停止，10 条事件已保存，费用估算 ¥0.01163912，无未知费用。本轮两次实验合计估算 ¥0.0741。旧响应没有保留，不能补称具体失败字段。
- `artifacts/demo-phase0/demo-validation.json`：三查询 × lexical/semantic/hybrid，九个 case 重复候选及分数稳定；SQLite 向量/检索记录与第二进程读取通过。中文攻击 query 返回约28–29s、31–32s、30–31s等候选；英文攻击 query 漏召回；汽车维修开发负例 hybrid/lexical 空，pure semantic 错返10条。不可把开发观察写成真实质量 gate。
- `demo-benchmark-input.json` 和 `demo-cli-benchmark-report.json` 是未标注开发报告，qualityGate=null；CLI 正确退出6。未来人工清单模板在 `templates/phase0-benchmark.example.json`。
- worker 文本/真实本地模型证据在 `docs/exec-plans/sprint-F005-worker.md`；固定batch=1消除量化冷/热漂移。早期负例及批次失败报告未覆盖。ASR 真实语音、无语音、取消/超时证据保留于 sprint-F003 和此前复核。

## 继续工作

先看 `docs/references/demo-quickstart.md`。本机现有 run：`./scripts/run-demo.ps1 -Run f76f5d6495314c04ae04083614d4afd6 -TopK 3`。新视频用 `-Video <本地路径>`；新机先 `./scripts/setup-demo.ps1`，另备固定 FFmpeg。ignored素材、DB和权重不随Git克隆。

当前代码：config v2含价格/采样/ASR/提示版本hash；5帧窗口重叠1；调用前登记；完成窗口不重发；显式 `analyze --resume` 保留原配置、全部费用与请求/帧累计。未提交/未知收费远端调用须 `--retry-uncertain`，不会自动补零或重试。schema3为13张STRICT表，使用原连接owner线程与事务；转录候选 event_id可NULL但必须真实同源音频证据。

最终 ./scripts/verify.ps1退出0：557 passed/0skip（51.13s）、Ruff、mypy42源文件、CLI通过；两次wheel SHA256 90c27fba9af76a86a35c191d684d0c5160baf07b49a4e8e90eb0356bf6eb4a75，41条package/dist-info，无模型/原生DLL/视频。setup-demo.ps1 -Offline已实际通过。首轮6fail/2err已修：legacy schema硬编码改为当前版本，固定fixture调用前登记pin，子进程显式-X utf8并正常finally关闭；生产合同未放松。五项用户/系统环境及Python注册表指纹未变，不代表全系统监控。所有workers和文档已冻结/整合；root工作树为最终来源。

下一阶段：冻结独立录制会话与主/稀疏/负例人工标签，主组每query至少10个独立可用参考，grade0..3，固定十槽U10≥0.70；先改善真实跨语言漏召回、无关召回和片段边界，再测小时级成本/性能。不得提前宣称完整Phase0质量、小时级性能或商业产品完成。

## 环境与接续规则

全部工具、原生库、包、模型和缓存只在 `.tools/`、`.venv/`、`.cache/`。`. ./scripts/env.ps1` 只改当前进程；禁止全局安装、改用户/系统设置。ASR和E5 worker用 -I -B、项目内CRT/hash与离线固定权重；uv.lock已含retrieval extra。

密钥仅走进程 DEEPSEEK_API_KEY，不复制聊天凭据、不写文件、不输出。source视频字节、DB、模型和实验响应均忽略。Codex/Claude/Grok遵循AGENTS和共享workflow；语言决定仍Python Phase0，未来UI另立ADR。

网络或额度中断前持续保存具体检查点，先核对分支/未提交修改和模块归属，不覆盖其他owner。旧scratch worktrees全部冻结；当前root和本轮worker归属见assignments。
