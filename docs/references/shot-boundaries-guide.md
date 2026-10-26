# 镜头切分与黑屏检测使用指南（detect-shots）

用途：看一个已准备或已分析的任务，原片哪里换了镜头、哪里黑屏，以及它已保存的事件和多帧分析窗口有没有把不同镜头混在一起。只读、本机、不花钱，不改变分析结果、检索排名或验收结论。

## 运行

```powershell
./scripts/detect-shots.ps1 -Project artifacts/independent-footage-20261011 -Run 5c7894aa10e94b8aa82533bd77f9871e -OutputPath .cache/shots/zhongkui.json
```

等价CLI：`python -B -m gamingcreator detect-shots --project <项目> --run <任务ID> --output <新JSON>`。任务ID可从工作台任务清单或`tasks`命令取得。

- 报告必须写到**新文件**，不能写进项目目录或原片所在目录。
- 原片须仍在任务登记的位置且内容未变（扫描前后各核对一次SHA256），否则拒绝并不写报告。
- 速度参考：15分52秒1080p约20秒。

## 在工作台里用

打开某个任务后，左侧“镜头切分（本机，不花钱）”卡片点“检测镜头切换”。完成后卡片显示汇总，时间轴上方出现切换刻度、下方标出黑屏段，跨镜头的事件和候选显示“跨 N 个镜头切换”。结果缓存在仓库`.cache/workspace/shots/`，再次打开同一任务直接读取；任务的分析结果变化后需要重新检测。

## 报告怎么读（`shot-boundaries-v1`）

- `summary`：切换数`cuts`、镜头数`shots`、中位镜头长`medianShotUs`、黑屏段数与总长、事件数及`eventsCrossingCut`／`eventsWithBlack`，窗口数及`windowsSpanningCut`／`windowsWithBlackFrames`（非窗口任务为null）。
- `cuts`（切换时刻＝新镜头第一帧，原片微秒）、`blackIntervals`、`shots`：都在原片时钟上，可直接在工作台跳转对照。
- `events`：每个已保存事件的`cutsInside`、`blackOverlapUs`、`crossesCut`。
- `windowsSpanningCut`：画面来自不同镜头的多帧窗口（窗口序号、阶段状态、第一／最后一帧时刻）。每个窗口用保存的阶段输入哈希核对“重建的这组图就是当时发出的那组图”（`inputMatchesStage`），汇总里`windowInputMismatches`应为0；`windowsStarted`是已开始分析的窗口数，只做过素材准备的任务为0（这时窗口只是按设置的计划划分）。
- `timelineDigest`：报告对应的已保存分析的指纹，工作台用它判断缓存是否过期。
- `detector`：FFmpeg版本、滤镜、阈值等全部参数；`humanReviewed: false`。

## 注意

这是画面变化启发式，未经系统人工核对：快速运镜、爆闪、界面弹窗可能误报，柔和转场可能漏报；相隔不到120毫秒的两个切换候选会被当作闪光一起丢掉，所以真实硬切紧跟运动模糊时可能漏报。用它来**找值得复查的位置**，不要当作验收证据或模型质量结论。规则细节见[sprint](../exec-plans/sprint-shot-boundaries.md)。
