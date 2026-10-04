# Phase 0 Demo

当前可完成本地视频分析、语义时间线保存与自然语言片段检索，并用本地工作台预览、查看证据和导出选片区间清单。候选还未经独立人工质量验收。所有命令在仓库根目录的 Windows PowerShell 执行，环境、包、模型和缓存均留在项目内。完整步骤、退出码和结果文件见 [使用手册](./user-manual.md)。

## 直接查看已有结果

当前工作站已具备本地素材、模型和 `artifacts/demo-phase0/timeline.sqlite3`，可复制这两条命令；不需要 API 密钥或联网：

```powershell
./scripts/setup-demo.ps1 -Offline
./scripts/run-demo.ps1 -Run f76f5d6495314c04ae04083614d4afd6 -Query "寻找角色打斗和攻击的片段"
```

脚本打印候选起止时间、可观察事实、时间线与检索记录位置。也可加 `-Mode lexical` 或 `-Mode semantic`；默认 `hybrid`。词法检索不需要 E5，语义与混合检索使用本地模型，不调用远端 API。

本地验证素材是 95.175874 秒的《漫画群星：大集结》PV，run `f76f5d6495314c04ae04083614d4afd6` 有 24 个视觉窗口、111 个事件、0 段转录。该 run 的 API 费用估算为 ¥0.06246088，未核对账单。上述查询曾返回 28–29、31–32、30–31 秒等候选，首次 hybrid 检索为 2574 ms；结果不证明 U10 或小时级性能。

2026-10-04 用 `-TopK 3` 复跑上述中文查询，连续两次都打印 00:00:28.000–00:00:29.000、00:00:31.000–00:00:32.000、00:00:30.000–00:00:31.000 和对应可观察事实。默认 hybrid 对 `Find clips of fighters attacking each other in the arena` 返回这三段带证据区间。汽车维修查询 hybrid 为 0 条。pure semantic 对汽车维修负例仍会误召回。这些不是人工 U10。早先全模式报告仍在 ignored `artifacts/demo-phase0/demo-validation.json`。

启动工作台用 `./scripts/run-ui.ps1`，浏览器打开 `http://127.0.0.1:8765/`。选择 `demo-phase0` 和完整 run `f76f5d6495314c04ae04083614d4afd6`；点击候选播放源区间，点击证据缩略图放大，使用描述/标签筛选时间轴，点「+」选片并下载 JSON/CSV。片段篮按项目/run 隔离，刷新后重新选择同一 run 可恢复；清单不生成 MP4。同一进程点击「刷新时间轴」重读数据库，无需等待 snapshot 文件。时间轴按源时间，候选保持检索排名。最新归属与下一步见根 `HANDOFF.md`；F006 人工 U10 仍未通过。

早期 run `823799e10a0440e8aec8b78b603bec57` 在2/24窗口后因 schema 失败停止，原响应未保存，未确定具体原因。该失败 run 估价 ¥0.01163912；与完成 run 合计本轮模型 API 估价 ¥0.0741，均非账单确认，不含硬件或开发工具费用。

视频、数据库、权重及生成文件不进 Git；换机须自行准备授权素材与本地项目文件。`-Offline` 缺少缓存时会明确失败。

## 分析自己的视频

首次准备运行 `./scripts/setup-demo.ps1`，仅向项目目录下载固定版本工具、包、运行库与模型。FFmpeg 仍须按 [隔离环境](./isolated-environment.md) 准备到 `.tools/ffmpeg/bin`，然后用 `./scripts/init.ps1` 检查。

新分析需要当前进程已配置 `DEEPSEEK_API_KEY`，只用于上传选定图片的付费视觉请求；不要把密钥写进配置、脚本、日志或交接。

```powershell
./scripts/run-demo.ps1 -Video "GameVideos/漫画群星：大集结/PV/漫画群星：大集结 - TapTap.mp4" -Query "寻找角色打斗和攻击的片段" -MaxCostCny 5
```

`config.example.json` 固定 schema v2、1 秒采样、5 帧窗口/1 帧重叠、视觉 prompt 内容 hash、CNY 价目和调用限制。覆盖的是抽取帧；不能据此保证捕获每个短动作。费用上限还包含未知调用的保守预留，因此可在实际估价很低时停止。

## 续跑与结果文件

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B -m gamingcreator analyze "<原视频路径>" --project artifacts/demo-phase0 --resume <run-id>
```

显式续跑保留原配置、预算和已完成窗口。若远端调用可能完成但本地窗口未提交，先查看错误诊断；决定重试时加 `--retry-uncertain`，原调用费用或未知预留继续计入预算。配置或 prompt 内容不一致时拒绝续跑。已完成 run 只重读，不再请求视觉模型。

项目保存 `timeline.sqlite3`、`runs/<run>/semantic_timeline.json`、`runs/<run>/searches/<local-file-id>.json` 与帧/音频证据。检索 JSON 包含排序、证据、分数语义与版本；分数不是置信概率。默认 E5 相似度/边际阈值 0.80/0.02 尚未用独立真实标签校准，允许空结果。

## 人工评测

按 [标签清单规格](./benchmark-manifest-schema.md) 冻结独立人工标签后执行 `gamingcreator benchmark`。报告即使 gate 未验证或未达标也会保存，此时退出码为 6。F006 须每个主机制查询的固定十槽 U10 ≥0.70；模型观察、示例命中和合成标签都不能替代该验收。
