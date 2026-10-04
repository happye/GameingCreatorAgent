# 本地检查工作台 API

2026-10-04 基础功能实现合同。现有 CLI 和 F006 验收不变；页面只绑定 `127.0.0.1`。

## 文件归属

root：`ui/server.py`、`ui/service.py`、新 `ui/media.py`、HTTP行为测试和共享文档。

页面 worker：新 `ui/static/index.html`、`app.js`、`style.css` 和自己的 sprint。不得改后端/依赖/公共交接；静态页面无需安装 Node 或其他包。

## GET 接口

- `/api/projects` → `{projects:[{path,name}]}`；path为仓库内相对路径，发现 `artifacts/` 下现有数据库。
- `/api/runs?project=...` → `{runs:[{id,status,sourceName,durationUs,errorCode}]}`。
- `/api/inspect?project=...&run=...&query=...&mode=hybrid&top=10` → 下面的视图；query为空只刷新时间轴，不执行搜索。检索模式 lexical/semantic/hybrid、top 1..100。
- `/api/media?project=...&run=...` → run已登记的原视频，GET/HEAD和单段HTTP Range。
- `/api/evidence?project=...&run=...&id=...` → 当前run已登记的图片或WAV，GET/HEAD。
- `/assets/app.js`、`/assets/style.css` → 固定静态资源；`/` → index.html。

项目只允许当前仓库内已存在的数据库。媒体只通过run/evidence身份映射，不接受任意文件路径。所有错误使用有效HTTP状态，JSON包含 `code,message,exitCode,runId`；前端显示message。检查/查询不调用远端API。

## inspect 视图

保留已有 `artifact,runId,runStatus,timeline,candidates,abstentionReason,ordering`。

- `media:{id,name,durationUs,videoUrl}`。
- timeline行保留 `eventId,startUs,endUs,startTimecode,endTimecode,observableFacts,evidenceIds`，新增 `mechanicTags`。
- candidate行保留 `rank,eventId,candidateId,startUs,endUs,startTimecode,endTimecode,observableFacts,evidenceIds,score,scoreKind`。
- `evidence:[{id,kind,startUs,endUs,url}]`，图片start=end，音频为源区间。
- `transcripts:[{startUs,endUs,text,uncertainty}]`。
- `stages:[{id,status,errorCode}]`。
- `cost:{knownCny,unknownAttempts,status}`；knownCny是Decimal字符串，未知项单独计数，金额不是账单。
- `retrievalVersion`、`query`、`mode`，用于导出来源追踪。

## 页面行为与导出

按原方案§12提供素材/视频/查询三个区域和下方时间轴。事件/候选可点击seek并播放到end自动暂停；证据图可查看源帧。文本全部用textContent等安全DOM API，不插入模型HTML。

查询结果按rank保留，时间轴按源时间；时间轴文本/标签筛选不更改候选排名。页面可选择片段，按 project+run 隔离，localStorage只保存选中候选，不写密钥。切换run清空显示中旧结果。

导出仅用户已选区间的JSON/CSV，不渲染MP4。JSON含schemaVersion=1、project/run/media身份、retrievalVersion、query/mode、selectedClips（微秒、timecode、原证据、事实、rank/score）。导出前重新匹配当前run的事件或候选，拒绝过期区间；不得把选中状态当人工有用度或humanLabels.confirmed。
