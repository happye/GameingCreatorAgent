# 本地检查工作台 API

2026-10-04 基础功能实现合同。现有 CLI 和 F006 验收不变；页面只绑定 `127.0.0.1`，Windows使用独占端口防止旧/新进程同时监听。

## 文件归属

root：`ui/server.py`、`ui/service.py`、新 `ui/media.py`、HTTP行为测试和共享文档。

页面 worker：新 `ui/static/index.html`、`app.js`、`style.css` 和自己的 sprint。不得改后端/依赖/公共交接；静态页面无需安装 Node 或其他包。

## GET 接口

- `/api/health` → `{application:"gamingcreator-workspace",apiVersion:1,repository,pid,parentPid}`；GET/HEAD，不访问模型或项目数据库，no-store。启动器用仓库真实路径与进程身份判断ready/复用，不能仅凭端口打开认作本服务。
- `/api/projects` → `{projects:[{path,name}]}`；path为仓库内相对路径，发现 `artifacts/` 下现有数据库。
- `/api/runs?project=...` → `{runs:[{id,status,sourceName,durationUs,errorCode,analysisKind,analysisProfile}]}`；analysisKind为temporal或frame_observations，analysisProfile为detailed/temporal/frame_observations，来自固定prompt配置。
- `/api/inspect?project=...&run=...&query=...&mode=hybrid&top=10` → 下面的视图；query为空只刷新时间轴，不执行搜索。检索模式 lexical/semantic/hybrid、top 1..100。
- `/api/media?project=...&run=...` → run已登记的原视频，GET/HEAD和单段HTTP Range。
- `/api/evidence?project=...&run=...&id=...` → 当前run已登记的图片或WAV，GET/HEAD。
- `/assets/app.js`、`/assets/style.css` → 固定静态资源；`/` → index.html。

项目目录和数据库真实路径都必须位于当前仓库。已注册原视频可保留在原本的本地路径。媒体只通过run/evidence身份映射，不接受任意文件路径。inspect生成的URL保留请求的project表示（例如仓库相对路径），前端核对项目/run身份后才加载。应用错误使用有效HTTP状态，JSON包含 `code,message,exitCode,runId`；请求/访问边界错误至少有code/message。检查/查询不调用远端API。

## inspect 视图

保留已有 `artifact,runId,runStatus,timeline,candidates,abstentionReason,ordering`。

`analysisKind/analysisProfile`与runs同义。V5/V6为“细节动作（试验）”，v3/v4为“连续动作（试验）”，旧run为“画面观察”。初次打开优先Completed detailed，其次Completed temporal；显式选择或刷新保持所选run。标签表示管线身份，不表示F006通过。

- `media:{id,name,durationUs,sha256,videoUrl}`。
- timeline行保留 `eventId,startUs,endUs,startTimecode,endTimecode,observableFacts,evidenceIds`，新增 `mechanicTags`。
- candidate行保留 `rank,eventId,candidateId,startUs,endUs,startTimecode,endTimecode,observableFacts,evidenceIds,score,scoreKind`。
- timeline/candidate新增 `displayFacts`（旧别名中性投影）与 `uncertainty`（关联事件原值）；顶层 `factsProjectionVersion=legacy-frame-alias-neutral-v1`。界面显示/筛选用displayFacts，并独立展示待核对信息；observableFacts保留原值用于保存、身份校验，不把uncertainty作为肯定检索事实。
- `evidence:[{id,kind,startUs,endUs,url}]`，图片start=end，音频为源区间。
- `transcripts:[{startUs,endUs,text,uncertainty}]`。
- `stages:[{id,status,errorCode}]`。
- `cost:{knownCny,unknownAttempts,status}`；knownCny是已知部分的Decimal字符串，未知项单独计数，缺DeepSeek价格版本或unverified记录不得算零/已知金额，估价不是账单。
- `retrievalVersion`、`configHash`、`query`、`mode`，用于导出来源追踪。

## 页面行为与导出

按原方案§12提供素材/视频/查询三个区域和下方时间轴。事件/候选可点击seek并播放到end自动暂停；证据图可查看源帧。文本全部用textContent等安全DOM API，不插入模型HTML。

查询结果按rank保留，时间轴按源时间；时间轴文本/标签筛选不更改候选排名。页面可选择片段，按 project+run 隔离，localStorage只保存选中候选，不写密钥。片段篮显示、保存和JSON/CSV统一按startUs、endUs、稳定身份升序，保留每片原rank/查询来源。切换run清空旧显示；同run重绘保留列表scrollTop，改变时间轴筛选回到列表开头。

导出仅用户已选区间的JSON/CSV，不渲染MP4。JSON含schemaVersion=1、project/run/media身份、retrievalVersion、query/mode、selectedClips（微秒、timecode、原证据、事实、rank/score）。导出前重新匹配当前run的事件或候选，拒绝过期区间；不得把选中状态当人工有用度或humanLabels.confirmed。

2026-10-05导出仍schemaVersion=1，增加factsProjectionVersion；selectedClips.observableFacts仅在身份校验后复制为显示投影，增加uncertainty，CSV相应增加两列。localStorage和原数据库事实不重写，旧篮子恢复时重新从当前事件取得显示/不确定性；改写rawfacts冒充投影会被拒。技术evidenceIds仍完整保留。

普通CLI与benchmark的持久化search JSON同样带factsProjectionVersion、displayFacts、事件原uncertainty和清理后的displayUncertainty；run-demo表格使用投影并显示待核对列。原observableFacts和CandidateClip身份不改，uncertainty不加入正面索引，audio-only候选目前无事件不确定性映射。
