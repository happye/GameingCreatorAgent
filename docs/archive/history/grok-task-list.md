# Grok 接手长任务清单（2026-11-01，由 Claude Code 交接）

> 用途：Claude Code 额度将尽，把**不需要用户、不需要新费用、不需要外部账号**、但冗杂或耗时的开发全部列在这里，交给 Grok 按顺序推进。
> 每完成一项：同一次提交内更新 `docs/exec-plans/progress-board.md`（数字只取自 feature_list / tech-debt / human-inputs）、`HANDOFF.md` 顶部、`progress.md`、`assignments.md`、对应 sprint 文件；向用户用通俗中文汇报“现在能做什么、验证了什么、还缺什么、下一步”。

## 0. 开工前必读（5 分钟）

1. 读 `AGENTS.md`、`HANDOFF.md` 顶部三段、进度看板第 6 节、本清单。
2. 环境：Windows PowerShell；每次先 `. ./scripts/env.ps1`；Python 一律 `.\.venv\Scripts\python.exe -B`（不加 `-B` 会写 pyc，破坏工具链校验）；pytest 加 `-p no:cacheprovider --basetemp .cache/pt-<名字>`，跑完删掉自己的 basetemp。
3. 推送：`git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push origin main`，不 force。不要提交 `.codex/agents/*.toml`（用户本地未跟踪文件）。
4. **禁止**：在 `.cache` 里做备份或复制大文件；递归扫描 `.cache` 找东西删（用户另有安排）；生成超过几百 MB 的测试文件（曾出现 58 GB 事故，见 TD018）——媒体测试必须带字节上限，测完即删。
5. **需要用户许可才能做**（本清单不包含）：付费模型调用（视觉分析）、任何下载、真实平台发布、支付、上传云端、真人质量评审（F006）。遇到就记到 `docs/exec-plans/human-inputs.md`，继续做别的。
6. 当前基线：最新提交见 `git log -1`；全量回归 4383 项通过（11-01）。51 项：已交付10 · 部分41 · 未开始0（约60%）；技术债 21 项 12/4/5。

## 1. 高优先（直接影响“装好就能用”）

### T1 便携应用内置本地模型（让安装版能分析新录像的语音和检索）✅ 已完成（32a8ab0）
- 现状：安装版缺 ASR 模型（`.cache/models/faster-whisper`，75MB）、嵌入模型（`.cache/models/multilingual-e5-small`，129MB）、原生运行库（`.tools/native`，1.6MB）和三个固定清单（`docs/references/asr-models.json`、`asr-native-toolchain.json`、`embedding-model.json`）。
- 做法：
  1. `src/gamingcreator/infrastructure/app_paths.py` 新增 `model_directory(repository, *parts)`：优先 `repository/.cache/models/...`（开发环境），不存在时用 `repository/models/...`（安装版）。
  2. 改 `cli/main.py::_pinned_asr_settings`（约 1084 行）和 `infrastructure/local_embeddings.py::from_manifest`（约 141 行）使用它；哈希校验保持不变。
  3. `scripts/build-app.ps1`：复制上述两个模型目录到 `Output/models/`、`.tools/native` 到 `Output/.tools/native`、三个清单到 `Output/docs/references/`；`$programParts` 加 `docs`、`models`。
  4. `scripts/install-app.ps1`：`$programParts` 同步加 `docs`、`models`（升级/卸载才会替换和删除它们）。
  5. 验收：`build-app.ps1 -Smoke` 通过；用打包目录里的 `.venv\Scripts\python.exe -B -c` 调 `LocalEmbeddings.from_manifest(<app>)` 真实嵌入一句 `query: 测试`，并调用 `_pinned_asr_settings(<app>)` 做文件校验；用 `install-app.ps1` 装到临时目录再测一次后卸载删除。总大小仍须小于 1.5GB（预计约 870MB）。

### T2 第三方许可证随包材料 ✅ 已完成（d1672f4）
- 生成 `Output/licenses/`：CPython、FFmpeg（固定构建的 LICENSE/编译参数说明）、WebView2 SDK（`.tools/webview2` 里已解出许可证）、每个运行依赖包（从 `.venv/Lib/site-packages/*.dist-info/LICENSE*` 与 METADATA 的 License 字段汇总），模型许可（faster-whisper tiny、multilingual-e5-small 的 model card 许可）。
- 写一个汇总 `licenses/THIRD-PARTY-NOTICES.md`（包名、版本、许可证类型、来源文件）。缺许可证文件的包列出来记入 human-inputs（需用户确认分发），不要自己猜。
- 加测试：build 后 notices 覆盖 site-packages 中每个 dist-info。

### T3 安装器可选快捷方式 ✅ 已完成（781060c）
- `install-app.ps1 -StartMenuShortcut`（默认不建）：在 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\` 建 `GamingCreator.lnk`（WScript.Shell），卸载时只删自己建的那个（记在安装记录里）。测试用临时 `-ShortcutDirectory` 参数，不碰真实开始菜单。

### T4 Free 套餐“分析分钟数”计量（总方案 §40） ✅ 已完成（f6433f4）
- 只计**本地媒体准备**（工作台“准备录像”，`ui/media_preparation.py::submit`）的录像时长：提交时用 ffprobe 读时长，按月累计（记录在 `.cache/workspace/creations/entitlement-usage.json` 之类，独占写/加锁），Free 每月上限（如 60 分钟，写在 `application/entitlements.py` 的 PLANS），超出时拒绝并说明；Creator/Pro/创始人版另设或不限。
- 不碰付费视觉分析的授权与账本逻辑；续跑（resume）不重复计数；失败的批次是否计数要写清楚并测试。
- `summary()` 返回本月已用分钟，页面“套餐与用量”显示。

## 2. 中优先（质量与可信度）

### T5 TD020 活动规则句式覆盖 ✅ 已完成（ba7827d）
- 在 `tests/` 建一个活动规则样例语料（至少 60 条真实风格写法：多阶段时间“第一阶段…第二阶段…”、“截止到”“自…起”、全角数字、“不少于/至少/≥”、“禁止/不得/请勿”、OCR 常见错字如“秒→杪”）。逐条期望值写进测试，扩展 `application/activity_rules.py` 规则；识别不了的必须返回“未识别”而不是猜。更新 TD020 状态。

### T6 TD021 剩余项 ✅ 已完成（4d6afec）
- `infrastructure/knowledge_store.py` 改用 `infrastructure/local_files.py` 的有界读取与独占创建 helper；`entries()` 的 mtime 排序对消失文件容错。
- Premiere xmeml 变速片段：查 FCP7 XML 规范中 `<rate>`/`timeremap` 写法，若能确定就补上并加 XML 结构测试；无法验证则保持现状并写明。

### T7 发布包水印核验 ✅ 已完成（e7c5a2a）
- `ui/package_jobs.py::verify` 检查包收据 `watermark` 与父成片收据 `watermark` 一致（旧包缺字段视为 None）；页面在发布包结果里显示“含 Free 水印”。加测试（Free 成片 → 包 → 篡改收据 → 核验失败）。

### T8 新界面文案的浏览器测试 ✅ 已完成（2eb9f6c）
- 用现有 strict-route 浏览器测试风格（参考 `tests/test_narration_browser.py`），覆盖：成片下的水印说明、“套餐与用量”的水印提示、方案卡“你常用的结构”文案（`rankedByHistory` 真/假两种）、时间线导出链接点击后带 `size` 参数。注意新端点要在 mock 里登记，否则 KeyError。

### T9 反馈学习进一步（P042） ✅ 已完成（bd294f3）
- 现在只按“做成成片的次数”调整通用方案顺序。可加：统计用户常做的修改（如“裁剪”占比高 → 在方案说明里提示“你常裁短，已建议更短片段”），但**必须**写入方案记录的 `ordering`/新字段并可复现；不要偷偷改片段时长而不记录。先写设计到 sprint 文件再实现。

### T10 企业版增强（P051） ✅ 已完成（1c08bcc）
- 审核历史在页面可展开查看；审核/团队变更导出为 CSV/JSON 审计日志；按项目设置不同团队（当前全局一个团队）。保持“操作人姓名自报、不是登录账号”的诚实说明。

## 3. 低优先 / 冗杂但有价值

### T11 全量 verify 门禁 ✅ 已完成（2215cb3）
- scripts/verify.ps1 全套（format/lint/mypy/pytest/离线 wheel）已绿；墙钟 1451.7s；见 sprint-t11-verify-gate.md。
### T12 用户手册 ✅ 已完成（23c49b4）
- docs/references/creation-guide.md 已扩为安装→发布包通俗全流程（每步入口／会发生／不会发生／常见问题）；见 sprint-t12-creation-user-guide.md。
### T13 pycache 清理 ✅ 已完成（4e28c31）
- 确认 gitignore；删除 src/gamingcreator 下 6×__pycache__／106×.pyc（未跟踪）；见 sprint-t13-pycache-cleanup.md。
### T14 进度看板逐行核对 ✅ 已完成（aed73e8）
- 每个 🟡／partial 已在 sprint-t14-progress-board-audit.md 标明缺口、用户／外部、可本地；可本地项拆为 T17–T28 追加于下。
### T15 CLI render-creation 水印 ADR ✅ 已完成（3f73b48）
- ADR-004：保持 CLI 默认无套餐水印；见 sprint-t15-cli-render-watermark-adr.md。
### T16 feedback 内容哈希缓存 ✅ 已完成（2d8f9f2）
- `feedback-cache` 按贡献文件内容 SHA-256 指纹；命中跳过汇总；见 sprint-t16-feedback-content-hash-cache.md。

### T17 窗口级片段缓存（P008） ✅ 已完成（8c69132）
- 设计见 sprint-t17；`window_segment_cache` + 分析命中跳过视觉；内容哈希失效；测试通过。

### T18 批量 make-proxy 入口（P011） ✅ 已完成（b73a5bd）
- CLI／脚本／API／工作台任务对话框可排队多条；同 SHA shared；单条失败不留半成品；见 sprint-t18。

### T19 OCR 离线难例夹具（P009） ✅ 已完成（e2dade3）
- catalog + 合成夹具 + Windows OCR 冒烟；准确率仍未人评、不宣称 F006；见 sprint-t19。

### T20 detect-shots 夹具回归（P010） ✅ 已完成（bfdada7）
- 扩大合成黑场／硬切夹具 + 回归；报告／工作台标明「抽检未人评」；见 sprint-t20。

### T21 本机知识库目录导入（P018） ✅ 已完成（57dc779）
- 目录批量导入 txt／md（可选截图／PDF）；CLI／API／创作页；不联网；见 sprint-t21。

### T22 平台规格 JSON 化（P034） ✅ 已完成（0cff287）
- manifest＋loader 版本化加载四平台 JSON；页面可编辑覆盖；不宣称官方已核；见 sprint-t22。

### T23 渲染裁切画面／简单叠加（P028） ✅ 已完成
- 成片安全区裁切＋静态角标本地 FFmpeg 路径与收据；见 sprint-t23-render-safe-area-badge.md。

### T24 字幕词级时序（若 ASR 已有）（P029） ✅ 已完成
- 探测结论：本机 ASR 无词级时间戳（缺口已文档化）；映射器仅接受真实 words 载荷，不造假；见 sprint-t24-subtitle-word-timing.md。

### T25 时间线导出音字轨实验（P033） ✅ 已完成
- FCPXML／OTIO／xmeml 最佳努力字幕＋立体声结构＋夹具；真机 NLE 导入仍非宣称；见 sprint-t25-timeline-export-av-tracks.md。

### T26 时间线中文指令语料（P041） ✅ 已完成
- 规则语料／拒绝用例扩充（rule-v4-corpus）；无云端模型；见 sprint-t26-timeline-command-corpus.md。

### T27 安装包 licenses／gaps 可见性（P039／T2） ✅ 已完成
- build-app／install-app（含 Smoke）提示阅读 `licenses/THIRD-PARTY-NOTICES.md` 与 `gaps.json`；不下载补许可；见 sprint-t27-license-gaps-visibility.md。

### T28 内容模式诚实文案（P043–P049） → 已完成
- 各模式方案卡／帮助统一写明「描述代理评分、非画面理解／未做人评／投放未验证」；与 creation-guide 交叉链接；见 sprint-t28-content-mode-honesty.md。

## 4. 交接时的未尽事项（Claude Code 最后状态）

- 第二轮对抗复审 8 项修复已完成并随本清单一起提交（见 HANDOFF 顶部“第二轮对抗复审”段）。
- `dist/GamingCreator` 是本地生成物（git 忽略），已按最新代码重建；可随时用 `scripts/build-app.ps1 -Smoke` 重建。
- 人工待办仍为：现在 0 项，未来 8 项（human-inputs.md）；真人质量评审入口：`Start-Workspace.cmd` → 验收流程 `/acceptance`。
