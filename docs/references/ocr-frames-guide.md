# 画面文字识别使用指南（ocr-frames）

用途：读出一个已准备或已分析任务在每个取帧时刻的原片画面文字（血条上的Boss名、字幕、菜单、片头片尾字卡等）。只读、本机、不下载、不花钱，不改变分析结果、检索排名或验收结论。只在Windows上可用。

## 运行

```powershell
./scripts/ocr-frames.ps1 -Project artifacts/independent-footage-20261011 -Run 5c7894aa10e94b8aa82533bd77f9871e -OutputPath .cache/ocr/zhongkui.json
```

- `-Every N`：每N个取帧识别一个（15分钟片全量约4.5分钟，`-Every 10`约45秒）。
- 等价CLI：`python -B -m gamingcreator ocr-frames --project <项目> --run <任务ID> --output <新JSON> [--every N] [--languages zh-Hans-CN en-US]`。
- 只用本机已装的识别语言；没有的语言在报告里列为“未使用”，不会自动下载或安装。
- 报告只能写到**新文件**，不能写进项目目录或原片所在目录；原片须在登记位置且内容未变。

## 报告怎么读（`ocr-frames-v1`）

- `summary`：识别帧数、有文字帧数、像真实文字的帧数（`likelyText`启发式）、空白帧、失败帧。
- `recurringTexts`：反复出现的文字及首末出现时刻（原片微秒）和帧数——最适合快速找“这段是不是Boss战”“片头片尾在哪”。
- `frames`：每帧`evidenceId`、`timeUs`、`status`（text／empty／failed／unavailable）、各语言的文字行和每个词的位置。
- `engine`：识别引擎、Windows版本、请求／可用／实际使用的语言；`humanReviewed: false`。

## 注意

文字识别不是验收证据：风格化标题常读不出，小字会有错字（如“大蚌真苕”），图标会被误读成零碎字符（标为`likelyText: false`）。用它来**找值得复查的位置**。规则细节见[sprint](../exec-plans/sprint-ocr-frames.md)。
