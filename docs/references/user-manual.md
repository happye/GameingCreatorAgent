# Gaming Creator Agent 使用手册

本手册说明本地视频分析、语义时间线与自然语言检索，以及浏览器检查工作台的预览、证据查看和选片清单导出。检索结果是模型观察和排序信号，仍须观看原片核对。

所有命令都在仓库根目录的 Windows PowerShell 里执行。工具、包、模型和缓存只放在项目内的 `.tools/`、`.venv/` 和 `.cache/`，不要安装到系统或用户目录。

更短的演示步骤见 [Demo 快速开始](./demo-quickstart.md)。环境细则见 [隔离环境](./isolated-environment.md)。当前进度见仓库根目录的 `HANDOFF.md`。

当前界面和处理服务都在本机，DeepSeek视觉分析使用必要抽样帧的云端推理，尚未打包EXE；详见[部署路线](./deployment-roadmap.md)。内容是否通过人工验收见[F006操作指南](./human-acceptance-guide.md)，不以页面好看或选片次数代替检索质量。

## 1. 你能做什么

| 你想做的事 | 用什么 | 要不要密钥 | 会不会联网付费 |
| --- | --- | --- | --- |
| 重放本机已经分析完的视频 | `run-demo.ps1 -Run <id>` | 不要 | 不要 |
| 分析一段新视频 | `run-demo.ps1 -Video <文件>` | 要 `DEEPSEEK_API_KEY` | 会上传抽到的帧，按次计费 |
| 只做词法检索 | `search --mode lexical` | 不要 | 不要 |
| 语义或混合检索 | 默认 `hybrid`，或 `--mode semantic` | 不要 | 不要；使用项目内 E5 模型 |
| 对照人工标签打分 | `benchmark` | 不要 | 不要；没有独立人工标签时门禁不算通过 |
| 视频预览、查看证据、选片与下载清单 | 双击 `Start-Workspace.cmd` | 不要 | 不要；只读取已有分析结果 |

已在本机验证过的示例是 95.175874 秒的《漫画群星：大集结》PV，run `f76f5d6495314c04ae04083614d4afd6`，24 个视觉窗口、111 条事件、0 条转录。2026-10-04 用默认 hybrid、`-TopK 3` 查询「寻找角色打斗和攻击的片段」，连续两次都得到：

| 开始 | 结束 | 可观察事实 |
| --- | --- | --- |
| 00:00:28.000 | 00:00:29.000 | 画面中央偏右有角色发出黄色光效并显示伤害数字 |
| 00:00:31.000 | 00:00:32.000 | 画面中央偏右出现绿色光效和伤害数字 |
| 00:00:30.000 | 00:00:31.000 | 画面中央偏下出现蓝色光效和伤害数字 |

同一默认模式下，英文 `Find clips of fighters attacking each other in the arena` 返回这三段带证据的区间。查询「汽车修理工拆卸发动机维修车辆」时 hybrid 返回 0 条。空结果是合法的。只开 pure semantic 时，这个汽车维修负例仍可能错返候选。这些数字不是人工 Top-10 通过，也不是小时级性能结论。该 run 的视觉 API 估价约 ¥0.06246088，未核对账单。

视频、数据库、模型权重和生成文件不进 Git。换一台机器要自己准备授权素材，并重新准备项目内工具。

## 2. 第一次准备

在仓库根目录执行：

```powershell
./scripts/setup-demo.ps1
./scripts/init.ps1
```

`setup-demo.ps1` 只往项目目录放入固定版本的 uv、CPython、依赖、ASR 小模型和多语言 E5 权重。本机已经下过这些文件时，用 `./scripts/setup-demo.ps1 -Offline`，缺缓存会明确失败，不会改去访问一套不同的版本。

FFmpeg 和 ffprobe 不在这个脚本里下载。把固定副本放到 `.tools/ffmpeg/bin/`，再跑 `./scripts/init.ps1`。规则见 [隔离环境](./isolated-environment.md)。

准备好之后，命令入口是：

```powershell
. ./scripts/env.ps1
./.venv/Scripts/gamingcreator.exe --help
```

`env.ps1` 只改当前 PowerShell 进程，关掉窗口就失效。不要改系统 PATH，也不要改用电脑上另装的 Python。

## 3. 在工作台预览、查询和选片

工作台可选择项目与运行、回看原视频、查询片段和查看原始证据：

```powershell
./Start-Workspace.cmd
```

也可在资源管理器双击根目录脚本。服务在后台启动并自动打开浏览器，重复启动复用本仓库服务；日志与PID在`.cache/workspace`。端口冲突会报错，不会关掉其他服务；可用`./scripts/start-workspace.ps1 -Port 8766`。不打开浏览器加`-NoBrowser`。需要前台运行则用`./scripts/run-ui.ps1`。启动和查询不重新分析视频或付费。页面上：

1. 左侧选择`demo-phase0`项目。初次默认Atom细节动作run `f601fb9b3e734d5ea188fc15c790acbb`（33事件）；旧V4 run `96b5f01530ce43e2944828fb0520b9b4`和漫画run `f76f5d6495314c04ae04083614d4afd6`仍可选择，原数据保留。其他项目可输入目录；新机须先准备素材并分析。
2. 中央显示原视频。右侧输入「寻找角色打斗和攻击的片段」，选检索方式与1–100条候选，点击「查找片段」。
3. 桌面中央上方是原视频与证据，下方是时间轴；点击事件/候选定位播放，「播放区间」会在结束时暂停。证据图片可放大，音频证据和转录可查看。
4. 时间轴与预览保持同屏；输入描述或选择玩法标签筛选，在面板内滚动事件，点击后保持列表位置。检索候选仍保留相关性排名。
5. 右下方片段篮紧邻时间轴；点「+」选片，按源开始/结束时间自动排序，浏览器保存及JSON/CSV导出采用同一顺序。可移除或清空，导出按钮固定在篮子底部。

排序口径：

- 时间轴按源视频时间从早到晚。
- 检索排名按分数从高到低，分数相同才看开始时间。所以排名表的顺序可以和时间轴不一样。

起止、事实和证据来自该run的SQLite。清单导出保留源身份、微秒区间、证据与检索版本；过期选择须重新核对。CSV对公式前缀转义。导出的是候选区间清单，不是MP4，也不会自动标成人工有用度。片段篮按项目/run保存；初次打开优先已完成连续动作run，重新选择原run才能看到其保存的选择。

新Atom试验可查询「寻找跳跃玩法的片段」「寻找角色奔跑和移动的片段」。有限否定规则修正后，跳跃hybrid有11.5–12.5s、0–2s两条候选；播放原片判断动作与边界，“连续动作（试验）”不是质量通过。模型仍可能跨镜头联系动作、混淆下落与跳跃；Boss与射击未验证可用。旧数据不会因代码更新自动变成新分析。

V5/V6运行标为“细节动作（试验）”，默认优先已完成细节run。新分析显式 `-Config config.detailed-v6.example.json`，描述衣着、外观、持有物、背景及动作效果；V6先判断多帧动作资格。可以查「黑色高礼帽白色面具角色挥动指挥棒」「粉色心形墨镜」「沙地石板蓝色水域」。结果需回看，“待核对”单独显示；模型仍可能误认配饰/武器或跨切镜关联角色。自由长句不能保证全部条件同属一人，完整复合匹配尚未接入工作台。旧f0/f1是输入图片编号，界面/导出已中性清理；新编号映射真实时间，技术证据ID保留。旧篮子身份及原事实不改，导出新增factsProjectionVersion与uncertainty。

分析还没结束时，已写入数据库的窗口会出现在时间轴上，不必等 `semantic_timeline.json`。点击「刷新时间轴」只重新读取；检索仅用于已完成的run。换项目或run会清空旧显示，避免误认旧结果。

左侧显示阶段、已记录费用估算和未知计费次数。浏览器不支持原视频编码或源文件已移动时会显示错误；证据和源时间仍以数据库为准，不据浏览器播放推导原始PTS。

常见桌面1440×900、1366×768已验证无需页面往返滚动；窄屏/手机改为纵向排列，只保证无横向溢出。顶部编排/成片与侧边资源「待开放」是后续位置，目前不能操作；区间清单与未来创意编排顺序分开。

## 4. 看已经分析好的结果

本机若已有 `artifacts/demo-phase0/timeline.sqlite3`：

```powershell
./scripts/setup-demo.ps1 -Offline
./scripts/run-demo.ps1 -Run f76f5d6495314c04ae04083614d4afd6 -Query "寻找角色打斗和攻击的片段" -TopK 3
```

脚本会打印候选序号、起止时间码和可观察事实，并给出两处文件：

- 时间线：`artifacts/demo-phase0/runs/<run-id>/semantic_timeline.json`
- 这次检索：`runs/<run-id>/searches/` 下的一份 JSON

`-Query` 可换成别的句子。`-Mode` 可以是 `hybrid`（默认）、`lexical` 或 `semantic`。`-TopK` 取 1 到 100，默认 10。`-Run` 和 `-Video` 只能二选一。

直接调用程序时等价于：

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B -m gamingcreator search "寻找角色打斗和攻击的片段" --project artifacts/demo-phase0 --run f76f5d6495314c04ae04083614d4afd6 --mode hybrid --top-k 3
```

标准输出是一行 JSON。`run-demo.ps1` 负责把其中的时间和事实打成表。脚本会把当前进程的控制台输出解码设为 UTF-8，以便 Windows PowerShell 5.1 读懂中文结果；退出脚本后恢复原来的解码。

## 5. 分析自己的视频

1. 把授权视频放在仓库里或本机任意可读路径。建议放在被 Git 忽略的 `GameVideos/`。
2. 只在当前窗口设置密钥，不要写进文件、命令历史或交接文档：

```powershell
$env:DEEPSEEK_API_KEY = "<你的密钥>"
./scripts/run-demo.ps1 -Video "GameVideos\你的视频.mp4" -Query "寻找角色打斗和攻击的片段" -MaxCostCny 5
```

`-MaxCostCny` 是这次新分析允许花的人民币上限，必须是有限正数。示例配置是 `config.example.json`：

- 视觉：DeepSeek `deepseek-flash`，价目版本 `deepseek-flash-cny-2026-10-04`
- 采样：每 1000 毫秒一帧，5 帧一个窗口，相邻窗口重叠 1 帧
- 上限：最多 500 次请求、5000 帧输入
- ASR 语言：`zh`

测试新版连续动作时显式加`-Config config.temporal.example.json`（v4，500ms/9帧/重叠2）。它创建独立新run，保留旧画面分析；9帧时间跨度约4秒，不代表完整故事或长Boss遭遇。示例：

```powershell
./scripts/run-demo.ps1 -Video "GameVideos/代号：Atom/PV/实机 代号：Atom（TapTap测试版） - 安卓官方试玩 - TapTap.mp4" -Config config.temporal.example.json -Query "寻找跳跃玩法的片段" -MaxCostCny 5
```

程序会先探测视频，抽出帧和音频，在本地做语音转录，再把每个窗口的画面发给视觉模型。成功后标准输出类似：

```json
{"runId":"<新的运行 ID>","status":"completed","mediaId":"<媒体 ID>","eventCount":111,"transcriptCount":0}
```

记下 `runId`。随后的检索使用这个 ID，不再上传画面。

费用按配置里的价目估算，并在真正发送前预留。未知费用保持未知，不会被写成 0。预留加上已发生的费用达到 `--max-cost-cny` 时，分析会停在退出码 7，已完成的窗口仍留在项目里。估价不是账单。

采样覆盖的是抽到的帧，不能保证每一个很短的动作都被看见。

## 6. 中断之后接着做

分析中途失败、取消或进程退出时，不要重新从头分析。用原来的视频路径和运行 ID：

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B -m gamingcreator analyze "<原来的视频路径>" --project artifacts/demo-phase0 --resume <run-id>
```

续跑规则：

- 沿用当初的配置、预算和已完成窗口，不接受另一份配置或新的费用上限。
- 视频路径必须和当初一致。
- 已经完成的阶段不会重做。
- 还有进行中的阶段时，返回 `storage.run_incomplete`，不会自动重放半截阶段。
- 失败、取消或中断的运行不会自动重放。
- 若某次调用可能已经在服务端完成、本地窗口却没提交，先看错误里的 `runId` 和 `code`。确认要补这一次时才加 `--retry-uncertain`。该次已发生或尚未确认的费用继续算进原预算。
- 配置或提示内容哈希对不上时，续跑会被拒绝。要换模型或提示，应新建一次分析。

## 7. 怎样写查询

默认 `hybrid` 同时使用词法 BM25 和本地 E5 向量，再用倒数排名融合。分数写在 `why` 里，例如 `BM25=3.9836; cosine=0.8715`。这句话后面的 “ranking signal, not probability” 表示它只是排序用的数，不是概率，也不是人工有用度。

三种模式：

| 模式 | 适合 | 依赖 |
| --- | --- | --- |
| `lexical` | 查询词会直接出现在画面描述或台词里 | 无 E5 |
| `semantic` | 想靠意思接近来找；负例也可能被高余弦带出来 | 本地 E5 |
| `hybrid` | 日常使用。没有词法锚点、语义分数又挤在一起时，可以合法地返回空 | 本地 E5 |

中文查询会去掉“帮我找”“片段”“角色”这类空话，再按二字片段匹配。英文里的 attack / fight / fighter / combat 会在词法侧补上「攻击」或「战斗」，因此英文攻击查询可以命中中文事件。这不是通用翻译，也没有把 pure semantic 的负例问题修掉。

空结果是正常结果。汽车维修这类与画面无关的查询，在 hybrid 下就应该可以是 0 条。不要为了“总有结果”改去 pure semantic 再把错返的 10 条当成找到了。

默认语义阈值是相似度 0.80、最高分与次高分至少相差 0.02。这两项还没有用独立人工标签校准。需要对比时可以加 `--min-similarity`，它只影响这一次排序。

## 8. 结果文件

一次分析的项目目录默认是 `artifacts/demo-phase0/`，也可以在命令里换成别的 `--project`。

| 路径 | 内容 |
| --- | --- |
| `timeline.sqlite3` | 运行、证据、事件、转录、费用和检索记录 |
| `runs/<run-id>/semantic_timeline.json` | 完成后的语义时间线。导出失败不会把数据库里的完成状态改回去 |
| `runs/<run-id>/media/` | 抽帧、音频和清单 |
| `runs/<run-id>/searches/*.json` | 每一次检索的查询、模式、候选、证据和版本 |

检索 JSON 里每个候选包含 `rank`、`startUs`、`endUs`、`startTimecode`、`endTimecode`、`evidenceIds`、`observableFacts`、`score` 和 `scoreKind`。时间是源视频上的半开区间，微秒整数。`evidenceIds` 指向这次分析保存的帧或音频，用来回看模型到底看见了什么。

源视频留在原处，不会被复制进数据库。

## 9. 人工评测

工具可以出报告，但报告本身不是验收通过。F006 要求：独立的人看过素材，每个主要玩法查询至少有 10 个互不重复的可用参考，固定 10 个槽位的 Useful Rate 至少 0.70。缺槽和重复计 0。现在这一步还没有完成，`feature_list.json` 里 F006 保持 `passes: false`。

未标注时也可以先跑通报告格式。复制 `templates/phase0-benchmark.example.json`，把 `mediaId`、`runId`、视频 SHA256 和时长换成完成 run 里的真实值。保持 `humanLabels.confirmed` 为 `false`：

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B -m gamingcreator benchmark --input templates\phase0-benchmark.example.json --project artifacts/demo-phase0 --output artifacts/demo-phase0/report.json
```

示例文件里的媒体 ID 是占位符，直接跑会被拒，必须先改成真实完成 run。清单格式见 [评测清单](./benchmark-manifest-schema.md)。

人还没标、或标了但没到门槛时，报告仍会写出，`qualityGate` 为 `null` 或未通过，进程退出码是 6。这表示“报告已写、门禁未过”，不是程序崩溃。模型自己写的观察、开发查询命中和合成标签都不能拿来把这个门禁改成通过。

人工标签里的等级是整数：0 无关，1 相关但不能用，2 可用，3 非常相关。2 和 3 必须对应一个人工参考事件。

## 10. 退出码

成功时退出码为 0，结果在标准输出。失败时退出码如下，诊断 JSON 在标准错误，字段是 `code`、`runId`、`retryable` 和 `message`。诊断不含密钥。

| 退出码 | 含义 | 常见原因 |
| --- | --- | --- |
| 0 | 成功 | 分析完成，或检索完成；检索允许 0 条候选 |
| 2 | 输入 | 视频打不开、路径不对、续跑视频和原运行不一致 |
| 3 | 环境或配置 | 配置字段不对、缺本地模型、检索功能参数不合法 |
| 4 | 模型提供方 | 视觉或嵌入调用失败、返回不符合约定 |
| 5 | 存储 | 数据库忙、文件损坏、进行中的阶段还不能续 |
| 6 | 评测门禁未过 | 报告已写，人评未确认或未达 U10 |
| 7 | 预算 | 费用上限到了，或发送前缺少价目 |
| 130 | 取消 | 你中断了命令，或任务超时被取消 |

看到非 0 时，先保留 `runId`。已写入的窗口还在项目目录里，按第 6 节续跑，不要删掉项目再重来。

## 11. 边界

做不到、也不要当成已经做到的事：

- 没有桌面软件，不能在界面里拖时间线或导出成片。
- 不能自动发布、结算或生成商业投放素材。
- 候选分数不是有用概率。中文攻击示例只说明命令能返回带证据的区间。
- pure semantic 仍可能把无关画面排进来。日常查询用默认 hybrid。
- 没有测过小时级录像的耗时和费用。长视频可能在抽帧日志体积上失败，见 `docs/exec-plans/tech-debt.md` 的 TD001、TD005。
- 缺少精确时间基的视频会被拒绝，程序不会猜时长。
- 语音模型是项目内的 tiny 权重，语言按配置里的 `zh`。没有人听过的转录不能当成字幕定稿。示例 PV 的转录数是 0。
- 密钥只放进程环境变量 `DEEPSEEK_API_KEY`。泄露过的密钥应作废，不要抄进文档。

## 12. 常用命令

```powershell
# 准备或复核项目内工具、ASR 与 E5
./scripts/setup-demo.ps1 -Offline
./scripts/init.ps1

# 打开本地检查工作台
./scripts/run-ui.ps1

# 重放已完成 run
./scripts/run-demo.ps1 -Run f76f5d6495314c04ae04083614d4afd6 -Query "寻找角色打斗和攻击的片段" -TopK 3

# 新视频。先在当前窗口设置 DEEPSEEK_API_KEY
./scripts/run-demo.ps1 -Video "GameVideos\你的视频.mp4" -Query "寻找开大招的片段" -MaxCostCny 5

# 同一条时间线换一种检索
./scripts/run-demo.ps1 -Run <run-id> -Query "寻找开大招的片段" -Mode lexical -TopK 5

# 显式续跑
./.venv/Scripts/python.exe -B -m gamingcreator analyze "<原视频>" --project artifacts/demo-phase0 --resume <run-id>
```

开发者核对仓库时用 `./scripts/verify.ps1`。那是格式、类型、测试和离线打包检查，不是使用视频分析功能的入口。

## 13. 文档地图

| 问题 | 去看 |
| --- | --- |
| 现在做到哪一步 | `HANDOFF.md` |
| 最短演示 | [demo-quickstart.md](./demo-quickstart.md) |
| 检查页为什么用 Python | [adr-002-local-inspection-ui.md](../design-docs/adr-002-local-inspection-ui.md) |
| 工具为什么必须留在项目内 | [isolated-environment.md](./isolated-environment.md) |
| 本地、云端与未来EXE是什么关系 | [deployment-roadmap.md](./deployment-roadmap.md) |
| 抽帧、时间戳和音频映射 | [media-processing.md](./media-processing.md) |
| 数据库和续跑存在哪里 | [timeline-storage.md](./timeline-storage.md) |
| 人工标签和 U10 怎么算 | [benchmark-manifest-schema.md](./benchmark-manifest-schema.md)、[phase-0-benchmark.md](./phase-0-benchmark.md) |
| 我该怎样进行F006人工验收 | [human-acceptance-guide.md](./human-acceptance-guide.md) |
| 命令和数据的工程合同 | [phase-0-engineering-spec.md](../design-docs/phase-0-engineering-spec.md) |
