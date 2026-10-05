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

2026-10-06版本选择：`/api/inspect`可选`detailProfile=v1|v2|v3`，API默认v1保持旧合同，页面默认v2并显式选择版本，未知值为400/input.detail_profile。顶层`detailRefinementProfile:{version:"actor-detail-inspection-v1",profile,settingsHash,schemaVersion,promptVersion,promptHash,provider,requestedModel}`使用固定RefinementSettings与所选独立身份：v1为冻结骨架、v2独立Provider、v3嵌套部件Provider。精确key缺失返回unverified，不借用其他版本；不接受任意路径、不扫描mtime、不自动解析自由查询约束。v3只有离线合同验证，没有新真实模型输出。

timeline/candidate行新增 `detailRefinement:{status:"unverified",availability,requestHash,detail}`。availability为 `missing`（该冻结key未发布结果）、`reused`（完整校验后复用）、`unsupported`（无视觉事件或旧数据缺合同兼容的版本/身份）、`run_incomplete`。非事件音频候选requestHash为null。detail缺失为null；复用时为actor-details-v1规范主体结构并增加计算出的unassignedEvidenceIds，保留镜头、主体、部件、observed/uncertain、原候选区间与支持源帧，不覆盖observableFacts或rank。没有typed QueryConstraint时status始终unverified，reused不等于full或人工认可。

读取先重验Completed timeline/source/evidence，再按计算出的requestHash检查不可变request、base prompt、schema、canonical payload/hash和来源；reused增加`payloadHash`供页面比对匹配内容。损坏/错身份/未知版本/越界路径或符号链接为明确409/refinement错误，不退成空详情；每JSON最多1MiB。缺侧车不建目录，刷新不写侧车、不预留预算、不实例化Provider。非空查询仍可追加原检索记录。`cost`继续表示base run账本，精分析费用由独立接口读取；只读复用不产生新推理费用。

## 明确条件与费用接口

`POST /api/match-details`仅接受JSON `{project,run,event,profile,constraint}`，constraint为query-v1显式正向AND清单，字段版本见detail-query.example.json；请求正文最多64KiB，拒绝重复字段、额外字段、非JSON、Transfer-Encoding或重复Content-Length。只接受本机Host/Origin，读取有界body后拒绝外部Origin，避免Windows未读正文导致TCPreset。Completed及event归属校验后，调用`match_refinement(save=False)`，缺结构返回unverified，损坏报错；不会保存match、预留预算或实例化Provider。

`inspect.detailQueryOptions`从冻结词表给出kind/value标签、query/schema/vocabulary版本和条件上限。页面弹窗允许显式AND/部件组，显示满足、缺失、不确定、冲突和支持帧；requestHash、payloadHash、run/event/profile须同时对应当前片段。编辑、关闭、切run/profile或刷新会取消迟到请求并清理旧显示。full仅指结构条件有共同支持，humanLabels/qualityGate仍null；自由检索结果不自动按typed约束过滤。

`GET /api/detail-cost-history?project=...&run=...`先只读确认run已登记（允许失败/进行中），再返回`detail-refinement-cost-history-v1`的summary、sharedCommitment、attempts、totalAttemptCount/attemptsTruncated。金额为Decimal字符串，已知估价与unknown预留分列；sharedCommitment只统计本项目全部run/budget精分析，基础分析与其他项目不包含。最多200条attempt展示/1MiB响应，摘要覆盖全部；planned丢ledger和result未settle仍保留unknown，legacy缺metadata为null。坏账本/路径报409，不创建目录/锁、不恢复/结算/发布、不返回原响应/提示词。页面只在点击费用入口后读取。

## 页面行为与导出

按原方案§12提供素材/视频/查询三个区域和下方时间轴。事件/候选可点击seek并播放到end自动暂停；证据图可查看源帧。文本全部用textContent等安全DOM API，不插入模型HTML。

查询结果按rank保留，时间轴按源时间；时间轴文本/标签筛选不更改候选排名。页面可选择片段，按 project+run 隔离，localStorage只保存选中候选，不写密钥。片段篮显示、保存和JSON/CSV统一按startUs、endUs、稳定身份升序，保留每片原rank/查询来源。切换run清空旧显示；同run重绘保留列表scrollTop，改变时间轴筛选回到列表开头。

选中片段时证据页显示主体详情未验证原因，复用结构可展开按镜头/主体/部件查看属性及支持帧，uncertain明确标待核对。所有模型描述用textContent；详情从当前检查视图读取，不写入localStorage篮子或schema1 JSON/CSV导出，旧篮子仍按rawfacts/区间/证据验证。点击、打开、刷新、搜索均不发精分析请求。

导出仅用户已选区间的JSON/CSV，不渲染MP4。JSON含schemaVersion=1、project/run/media身份、retrievalVersion、query/mode、selectedClips（微秒、timecode、原证据、事实、rank/score）。导出前重新匹配当前run的事件或候选，拒绝过期区间；不得把选中状态当人工有用度或humanLabels.confirmed。

2026-10-05导出仍schemaVersion=1，增加factsProjectionVersion；selectedClips.observableFacts仅在身份校验后复制为显示投影，增加uncertainty，CSV相应增加两列。localStorage和原数据库事实不重写，旧篮子恢复时重新从当前事件取得显示/不确定性；改写rawfacts冒充投影会被拒。技术evidenceIds仍完整保留。

普通CLI与benchmark的持久化search JSON同样带factsProjectionVersion、displayFacts、事件原uncertainty和清理后的displayUncertainty；run-demo表格使用投影并显示待核对列。原observableFacts和CandidateClip身份不改，uncertainty不加入正面索引，audio-only候选目前无事件不确定性映射。
