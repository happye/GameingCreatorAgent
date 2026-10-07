# Phase 0 工程规格 v5

状态：2026-10-04 实施合同。CLI 已接媒体、本地 ASR、视觉窗口/账本、显式续跑、词法/本地语义检索和人工标签评测入口；F003/F005 技术合同已验收，F006独立人工质量gate未通过。CLI证据见sprint-demo；本地工作台及最新完整验证见 [sprint-inspection-workspace](../exec-plans/sprint-inspection-workspace.md)。来源：原总方案 §58–59、69–71；语言见 [ADR-001](./adr-001-phase-0-language.md)，审查见 [reverse-review](../exec-plans/reverse-review-2026-10-03.md)。当前运行入口见 [Demo](../references/demo-quickstart.md)。

## 1. CLI 与外部行为

用户硬约束：所有工具、包、模型权重和缓存隔离于本机系统。portable uv 放 `.tools/uv`，CPython 3.13 运行时放 `.tools/python`，应用/开发/ASR 包全部装入 `.venv`；FFmpeg 放 `.tools/ffmpeg/bin`，缓存放 `.cache`。仅使用进程环境，不写注册表、系统/用户 PATH 或全局包目录；uv 注册和全局链接显式禁用。版本固定及校验在 F001 完成，详见 [隔离环境](../references/isolated-environment.md)。

以下命令已接入应用流水线。`analyze` 创建 run、逐窗口保存语义输出；`search` 查询 Completed run 并记录排名；`benchmark` 保存人工标签评测报告，gate 未过或未验证时退出 6。缺少视觉费用上界时停止且不发送。历史实验见 [验证记录](../exec-plans/phase-0-validation-2026-10-03.md)。

```text
gamingcreator analyze <local-video> --project <directory> --config <json> --max-cost-cny <amount>
gamingcreator analyze <local-video> --project <directory> --resume <run-id>
gamingcreator analyze <local-video> --project <directory> --resume <run-id> --retry-uncertain
gamingcreator prepare-media <local-video> --project <directory> --config <json> --max-cost-cny <amount> --timeout-seconds 3600
gamingcreator prepare-media <local-video> --project <directory> --resume <run-id>
gamingcreator tasks --project <directory> --limit 100 --offset 0
gamingcreator tasks --project <directory> --run <run-id>
gamingcreator freeze-benchmark --input <plan.json> --output <new-directory>
gamingcreator bind-benchmark --freeze <freeze-directory> --project <directory> --runs <mapping.json> --partition test --output <new-directory>
gamingcreator search "机制描述" --project <directory> --run <completed-run-id> --mode hybrid --top-k 10 --format json
gamingcreator benchmark --input <frozen-manifest> --project <directory> --output <report.json>
gamingcreator benchmark --input <judged-manifest> --project <directory> --output <report.json> --binding <bound-directory>
```

`analyze` 校验文件、能力、预算和空间后创建 run。成功写 SQLite 与 `semantic_timeline.json`；失败或取消输出 run ID 和稳定错误码，保留已完成 checkpoint。显式 v2 resume 使用原配置/预算，跳过完成的 media、asr 和 `vision-000000` 等窗口；进行中记录转 Interrupted 后重开，不自动重放。未提交的远端调用可能已有费用，须 `--retry-uncertain` 才重试，原费用/未知预留继续计入预算。已完成 run 只重读。旧 v1 保留原有限续跑行为；配置、prompt 内容或 ASR 稳定参数不匹配时拒绝恢复。

`prepare-media`仅支持原schemaVersion 2窗口合同，保存与analyze相同的配置／pipeline／required stages，复用原512或1280抽帧宽度和媒体发布逻辑。单独组合MediaProcessor／TimelineStore，不构造ASR／Vision／HTTP或预算账本，不读取密钥。media完成且无其他阶段／调用时finish_media_preparation把run置pending；原分析显式resume跳过media。续准备拒绝源变化、配置／预算覆盖及已开始模型工作，不触及旧未知费用。JSON区分status=media_prepared与runStatus=pending，显示imageCount／audioAvailable／plannedWindows／含重叠的plannedUploadFrames／coverageFits；不足只保存，不输出启动命令。这不是费用估价或内容理解。超时只约束探测与提取工具执行，不包括SQLite保存／完整性检查。

`tasks`用只读metadata快照查看保存的进度、原配置及基础费用，不重读源视频／media manifest、不recover或实例化Provider。返回material-tasks-v1；limit为1–200、offset为0–1000000，按创建时间倒序／run ID分页，单项查看拒绝非零offset。准备未完成、素材已保存等待分析、分析未完成与已完成分别显示；父阶段与已完成视觉窗口分别计数。原maxCostCny不覆盖；未知尝试保留reservation，旧记录缺预留时承诺／余额为null，精分析费用不在此账本。CLI仅在无已知阻断时提供nextCommand参数数组，未提交费用未定调用不提供命令，不自动添加retry-uncertain或执行。清单不证明文件完整、进程正在运行或人工质量；打开／实际续跑继续原完整性检查。入口脚本list-tasks.ps1，使用已有PowerShell 7。

`config.example.json` 使用 schema v2：vision 含 provider/model、priceVersion、maxOutputTokens（≤4096）、promptVersion/promptHash；limits 含正整数 maxRequests/maxInputFrames；sampling 含 intervalMs/windowFrames/windowOverlap；asr 含 language。未知字段（包括密钥）拒绝。默认每秒采样、5 帧/1 帧重叠、最多 2048 输出 token。新分析费用上限由 CLI 传入有限正 Decimal；resume 禁止配置/预算覆盖。旧 schema v1 仍可读，但没有完整窗口/价目配置。

连续动作试验显式使用 `config.temporal.example.json`：schema仍为2，prompt为独立fingerprint的`phase0-vision-v4`，500ms采样、9帧/2帧重叠、独立pipeline `phase0-analyze-temporal-v1`。v1/v2仍最多5帧，v3/v4最多9帧；旧配置、prompt内容与run不改写。

2026-10-05细节优化显式用 `config.detailed.example.json`：V5 hash为c64c644e9889fcfd91cc0e9a26d8bf1b9546ce73c548e6ac056a5067498ff98a，pipeline `phase0-analyze-detailed-v1`，500ms/9帧/重叠2、输出4096token。V5采样宽上限1280（原源更小不放大），每图3MiB、detail=original；旧V1–V4仍512/1MiB，管线hash与配置身份分别钉住版本和prompt。新配置创建新run，恢复不得提升旧证据尺寸。

同日V5在31.5s单帧外观重复作动作后，新增 `config.detailed-v6.example.json` / phase0-vision-v6 / pipeline `phase0-analyze-detailed-v2`，hash a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00。能力/六字段/事实限制与V5一致；提示先确认多帧主体动作再补外观，输出前自检不同端点/引用和uncertainty类型，单帧/纯切镜省略。Parser保护不松、V1–V5字节冻结，失败V5不换prompt续跑；V6另起run。细节准确性及轻微待机/静态边缘仍须人评。

`search` 指定 Completed run；找不到或完整性失败时返回明确错误。默认 hybrid，也可 lexical/semantic；候选含 candidateId/mediaId/eventId、startUs/endUs、startTimecode/endTimecode、rank、score/scoreKind、evidenceIds、observableFacts/why。时间为半开区间，分数不是事实概率。排序确定，去重后保留排名和证据；空结果合法并附 abstentionReason。检索记录与向量在 schema v3 中保存，分析输出保持不可变。

stdout 为结果或 JSON；进度/JSON 诊断写 stderr。退出码：0 成功，2 输入，3 环境/配置，4 Provider，5 存储/完整性，6 benchmark 未过门槛，7 预算停止，130 用户取消。JSON 错误含 code、runId、retryable、友好说明，不含凭据。

## 2. 时间与数据合同

评审导入显式--score（PowerShell -Score）并提供人工记录时，对已重新核对来源的原保存十位hits／失败调用旧run_benchmark，无新检索。报告v1加scoring benchmark-fixed-scoring-v1及原报告／绑定／依据／规范记录SHA，ordinarySearches=0／paidRequestsSent=0；原retrievalId／startedAt／elapsedMs／耗时比例保留，scoredAt／scoringElapsedMs分开。基础费用由与CLI共用benchmark_analysis_costs从原attempt重新汇总，不信任报告自填费用、不清账或新增预留。原质量协议及声明约束不变；null／false退出6并保留新目录报告。默认无Score仅转标签且qualityGate=null，文件发布回执null不冒充验收。原benchmark命令仍明确再检索。

候选评审记录benchmark-candidate-review-v1绑定原manifest／报告SHA及实际retrievalId，保留十位、原排名／区间／模型事实、缺位和已知重复。成功报告须可回读保存检索；音频无eventId使用原candidateId，失败查询不可判分。只允许日期／填写人／复核与候选grade、humanEventId、reason填写；0–3必须理由、2/3必须原参考，未判定保持null。导入重新核对Completed来源／config／pipeline和排名、原报告／绑定，只生成旧v1候选标签，不改变confirmed／independent。新目录独占发布回执最后保存，生成／导入无搜索／模型／预算或新HTTP。HTML本机原片回看仅零起点已验证；其他时钟及编码手动核对，TD006未关闭。正式benchmark仍显式再检索评分，不称原排名只读评测。见[指南](../references/benchmark-candidate-review-guide.md)。

验收准备用benchmark-plan-v1记录原路径、录制组、development/test、是否看过模型结果、查询族及人工参考，不含候选评分。freeze-benchmark仅本地probe／hash原视频，重验输入／来源未改变，在新目录独占写原字节和benchmark-freeze-v1，UTC冻结时间、准备缺口与SHA回执；完成回执最后写。来源／内容／查询族跨区、缺同源组／足量代表来源／主查询或人工参考、测试已看结果等不冒充独立ready。参考采用原benchmark验证并按实际时长核对；原录制与人工声明不由工具认证。bind-benchmark只读核对Completed run／来源完整性／冻结SHA和时长，指定分区完整映射，输出原benchmark v1与config／pipeline／freeze SHA来源。新目录不可覆盖或写入项目／冻结目录；缺参考保持confirmed=false，独立准备不足或development时independentTestSet=false，candidateLabels空。两步不构造模型、预算或搜索。benchmark可选--binding在打开store／加载embedding前复核原绑定，仅candidateLabels与humanLabels.reviewed可变；改查询／参考／来源／版本／填写人或声明拒绝。准备结果qualityGate始终null，正式70%与费用合同不变；操作见[验收准备](../references/benchmark-preparation-guide.md)。

所有领域时间是从源视频规范化起点计量的 Int64 微秒 `[startUs,endUs)`；非负且小于等于源时长，Python int 必须校验不超过 `2^63-1`。格式化显示时间可以舍入，持久化不可用显示字符串反推。Evidence 另存原始 PTS、timebase、streamStart、切片偏移、音视频偏移和变换版本；模型局部时间由程序回映射并检查范围，VAD 必须有回映射。

F002 采用最早选中流 presentation start 为共同 origin，精确 Fraction 先相减，点/起点 floor 到微秒，终点/时长 ceil。音频输出保留逐帧 sampleOffset/PTS/样本数；gap/overlap 与≤1输出样本的边界量化裁切均可追溯。按元信息音轨 end_pts 裁去本次解码观察到的越界样本。完成 bundle 不等于 Completed AnalysisRun。实现/支持范围见 [媒体合同](../references/media-processing.md)。

| 记录 | 必需字段 |
| --- | --- |
| MediaAsset | mediaId、源路径（本地）、SHA256、durationUs、streams、probeVersion |
| Evidence | evidenceId、mediaId、kind、源区间/时刻、PTS/timebase、artifactPath、hash、transformVersion |
| TranscriptSegment | mediaId、源区间、text、uncertainty；ASR 模型/版本/状态由调用账本关联 |
| SemanticEvent | eventId、mediaId、源区间、observableFacts、mechanicTags、evidenceIds、modality、uncertainty、runId |
| Embedding | subjectId、provider/model/revisionScope、dimension、normalization、vector、textHash |
| CandidateClip | candidateId、eventId、源区间、rank、scoreKind/score、证据与排除原因 |
| AnalysisRun | runId、配置快照/hash、pipelineVersion、状态、开始/结束/错误 |
| StageCheckpoint | runId/stageId、输入/输出 hash、状态、attempt、错误 |
| ProviderInvocation | invocationId、run/stage、attempt、Provider/模型、用量、价格/币种、费用状态、耗时、requestId、executionDetails |

`confidence`、GPU 时间和供应商未提供用量可以 null；未知不是 0。推断机制与可观察事实分开。没有足够证据的动作边界存不确定性，不允许模型输出越界时间或编造 evidenceId。OCR/情绪等后续字段可缺失，未测量值不能虚填。

## 3. Provider ports 与首个实现

Application 用 `typing.Protocol` 定义类型化 async ports，await 得到 `ProviderResult[T]`，请求携带明确取消/超时上下文。`VisionProvider.analyze(VisionRequest)`、`AsrProvider.transcribe(AsrRequest)`、`EmbeddingProvider.embed(EmbeddingRequest)` 对应原方案 IVisionModel/IASRModel/IEmbeddingModel；查询扩展/重排需要时用 `LlmProvider.complete(StructuredRequest)`。不创建 Phase 0 不用的 IImageModel 实现。

同步 ASR/原生推理放可终止 worker，由异步 facade 收集完整结果并校验；不能仅用取消 await 或线程假装终止推理。faster-whisper segments 的惰性迭代必须在 worker 内完成，再返回可序列化段落。[官方运行语义](https://github.com/SYSTRAN/faster-whisper)

请求含 runId、输入证据引用、语言/游戏词表、prompt/schema 版本、输出预算；结果含 typed output、usage、实际 model/revision、requestId、elapsed、状态与错误。Capabilities 声明图片序列/视频/音频、尺寸/数量限制、结构化输出和局部时间语义。Capability mismatch 在请求前失败。

首个视觉 Provider：DeepSeek `deepseek-flash`，`POST https://api.deepseek.com/chat/completions`，`user.content` 用带源时间的 text 与 `image_url`；只上传窗口证据，不上传整视频。禁用 thinking，使用 json_object。`phase0-vision-v2` 用 f0..f4 短别名，程序严格映射回原 evidenceId；prompt 给出窗口首末 sourceUs、整数微秒与半开边界要求，end 必须大于最晚引用时刻。字段/类型/证据/边界错误不修猜，返回 provider.schema；executionDetails保留有限schemaError枚举，可加schemaDetail白名单：eventIndex/startUs/endUs/sourceUs为Int64整数、frameAlias仅f0..f8，不保存原响应或任意文本。prompt内容hash校验并写入快照。旧v1长ID协议仍可读。response.model记录实际别名，供应商实际修订仍可能unresolved。[官方 Vision](https://api-docs.deepseek.com/guides/vision/)

v4严格绑定`temporal-actions-v1`：每事件字段为startFrameId/endFrameId/observableFacts/mechanicTags/evidenceIds/uncertainty，最多3事件。程序由首尾帧sourceUs生成`[firstUs,lastUs+1)`；端点必须出现在有序引用内，至少两个不同时刻与不同图像hash。输入倒序/重复时刻、未知别名、单帧或复制图动作声明拒绝；空事件合法。v1/v2/v3仍用原schema。9帧多图与这些校验只是工程必要条件，不能证明动作/玩家控制/跨镜头因果理解；见[真实试验](../references/temporal-gameplay-validation.md)。

V5沿用v4六字段与动作证据保护，每事件最多6条事实/总1000字符（提示目标约250中文字），首句先绑定主体→外观/衣着/持有物→动作，再补其他角色、环境、目标和可见效果。官方装备/角色/技能名、Boss身份无证据不推断；看不清的细节入uncertainty，不加入正面索引。新正文泄漏f0..f8时，只用完整请求映射转为真实时间再生成eventId；未知准确小写编号拒绝。旧冻结事实不改写，以legacy-frame-alias-neutral-v1作显示/视觉索引投影；键盘F1、普通复合标识保留。静态外观独立索引和通用复合条件匹配尚未实现，不删除静帧动作保护。

ASR 使用本地 faster-whisper tiny，固定权重/运行库 hash 与 CPU int8。worker 开始前登记模型修订、参数和输入；`no_audio/no_speech/completed/failed/cancelled` 分开。源 hash、模型修订、schema 与稳定参数共同构成 v2 ASR stage 输入 hash。API 费用为本地零网络调用费用，硬件成本未测；中英文识别质量仍需人工参考。ChatGPT/开发工具额度不等于项目 API 配额。

Embedding 使用固定 `Xenova/multilingual-e5-small` ONNX 权重，384 维、attention-mask mean pooling、L2，query/passages 分别用 `query: `/`passage: ` 前缀；最多 512 token，v2 推理 batch=1。空间身份包含权重修订、文件 hash、推理合同/pooling/maxTokens/batchSize；缓存不跨不一致空间混用。同步推理同样通过可终止本地 worker 执行，不下载未知模型。

完整搜索不再受1024文本请求上限限制：本地Provider将缺失向量按每worker最多1024文本及转义JSON字节容量顺序拆分，固定单文本推理合同／空间／text hash保持。每批完整校验输出与模型文件后才缓存，结果subjectId仍按整次请求编号；全批共享一个取消／超时期。仅全部成功后返回向量并由原事务保存全部事件索引与搜索，失败不返回部分搜索；已校验缓存可供后续重算复用。executionDetails的workerBatches记录实际worker尝试数，热缓存为0，不代表API请求。真实小时级素材全链路／峰值内存仍需另测。

## 4. SQLite schema v3 与迁移

当前 schema v3 共 13 个 STRICT 表；物理定义在 `infrastructure/sqlite_schema.py`，使用事务迁移和读写双方结构验证。v1 的九表定义保持原样，v2 为 transcript_segments 添加 uncertainty，v3 加 embedding/检索四表。迁移历史与 user_version 一致；未来版本、版本断层和定义漂移拒绝打开。只由 writer 升级，read-only 不自动迁移。详见 [timeline-storage](../references/timeline-storage.md)。

| 表 | 主键、关系及约束 |
| --- | --- |
| schema_migrations | version PK；连续迁移历史/时间，与 user_version 一致 |
| media_assets | media_id PK；content_hash、duration_us>0；同项目同内容去重 |
| analysis_runs | run_id PK；配置/pipeline hash、required stages/status、manifest path/hash；UNIQUE(run_id,media_id)，绑定 media_id FK |
| stage_checkpoints | (run_id,stage_id) PK；状态、输入/输出 hash、更新时间 |
| evidence | evidence_id PK；media_id/run_id FK；有效源时间、artifact hash/path |
| transcript_segments | segment_id PK；media_id/run_id/stage FK；区间、文本、uncertainty |
| semantic_events | event_id PK；media_id/run_id FK；有效区间、结构化事实与标签 |
| event_evidence | (event_id,evidence_id) PK；两组包含 run_id/media_id 的组合 FK，不允许悬空或串 run 证据 |
| provider_invocations | invocation_id PK；UNIQUE(run_id,stage_id,logical_request_id,attempt)，状态、模型/用量/价格快照；费用为 Decimal TEXT，unknown 为 NULL |
| embeddings | 每 run/subject/完整 embedding-space/text_hash 唯一；向量维数与关联事件/证据校验 |
| retrieval_runs | retrieval_id PK；query/hash、retrieval version、参数、embedding space、耗时与结果快照 |
| retrieval_hits | (retrieval_id,rank) PK；candidate/event/run/media、区间与 score/score_kind |
| retrieval_hit_evidence | (retrieval_id,rank,evidence_id) PK；组合 FK 绑定相同 run/media 及事件引用 |

embedding 唯一键包含 run、subject/provider/model/revision_scope/dimension/normalization/text_hash；未知修订不得混用向量。检索表仅追加 Completed 分析的检索结果，不重写分析事件；事件向量、结果/rank 与证据关联按一次检索原子登记。query/rank/candidate/version/阈值与空间身份可回读。

使用标准库 `sqlite3`，连接启用 FK、WAL、`synchronous=FULL`；写事务短，有限 busy timeout；每项目一个分析写入者。连接在其所属线程创建和使用，不共享跨线程连接；明确配置事务行为，不依赖 Python 默认值。同步 DB 操作由受控单写队列/专用线程执行，不能阻塞网络事件循环或在事务内等待媒体/模型。WAL 仍是单写。[WAL](https://www.sqlite.org/wal.html)、[Python sqlite3](https://docs.python.org/3.13/library/sqlite3.html)

文件先写临时路径、完成校验和最终落盘，再将 bundle/语义输出及 Completed checkpoint 同事务登记。项目级非阻塞 OS 锁覆盖 writer 生命周期，读者可并行。恢复逐 run 报告文件/来源/快照损坏、孤儿/临时文件，把 Running 阶段/调用置 Interrupted，保留已完成记录和未知费用；不自动重放或删除。load_media_bundle 可重建未完成 run 已完成的媒体阶段，含完整音频分段映射。Completed 查询重新校验文件，损坏结果拒绝；备份以后使用 SQLite backup API，JSON 导出失败单独记录，不能冒称 DB 与导出同时原子。

## 5. 采样与检索实验

旧v2每秒抽帧并用5帧/1帧重叠覆盖全部抽取帧；v4试验用2FPS、9帧/2帧重叠，均约4秒时间跨度，最后窗口可不足上限。每窗口独立checkpoint，上传总帧数含重叠/重试，运行前预检最低额度并保留每attempt硬上限。全覆盖不保证捕获短动作，不能无条件跨窗/跨镜头拼故事。有限1FPS/2FPS真实对照已记录，但独立精度/长动作/强模型对照仍待验证。

媒体抽帧／音频调用使用有界逐行stderr consumer，已识别showinfo／ashowinfo记录即时解析，未知诊断≤16MiB且单行≤64KiB，普通Provider仍用原整段输出限流。裁前音频只累计样本，裁后保留原分段PTS及WAV映射；完整校验和原子manifest发布合同不变，原transform／schema身份保持。合成一小时／3600图／168752分段／63.2MB日志已完成真实FFmpeg、media阶段存储及第二进程回读；不等于真实游戏小时处理速度或完整ASR／视觉分析验收。

当前检索对照lexical BM25、local E5 cosine和hybrid RRF（`bm25-e5-rrf-v7`）。正向中英文动作复用有限词表补已知中文别称，覆盖jump／shoot／move／interact及attack／fight变体，以及跳跃／跳起／起跳、射击／开枪、战斗／打斗、交互／互动；NFKC／大小写及中英文相邻边界一致。不追加英文动作词到中文或其他英文别称查询，避免JUMP游戏标题被翻译成跳跃；直接jump查询仍可命中同名字词，不证明动作。不将movie／jumpsuit或摄影shot扩展为动作。扩展与明确否认过滤共用ASCII字母／数字／下划线边界；英文弯／直引号一致，否定意图查询保持原词法行为，不实现缺席语义。v5正文清理及v6有限英文词边界仍保留，v7仅追加既有中文动作别称；passage文本／哈希与缓存、源事实、CandidateClip身份、旧搜索记录、向量空间及阈值0.80/0.02不改写。uncertainty不索引为正面证据，RRF不保证任意复合属性同属一人；512token输入要求紧凑事实优先。候选按证据/区间去重，模型eventId不等于人工独立动作。已有四份完成分析／三个视频SHA只供开发审计，Atom不同文件可能同源，不能当独立检索质量或真实动作人评；测试集仍按录制会话隔离。

真实 PV 的离线三查询×三模式重复稳定，检索/向量写入和第二进程回读成功；报告位于本机 ignored `artifacts/demo-phase0/demo-validation.json`。2026-10-04 默认 hybrid 对中文攻击查询和英文 `Find clips of fighters attacking each other in the arena` 都返回 28–29、31–32、30–31 秒带证据区间；汽车维修查询 hybrid 为 0 条。pure semantic 对汽车维修负例的误召回仍在。不能用这些观察替代真实召回校准或 U10。

## 6. 成本、缓存、恢复与取消

每个网络 attempt 在发送前登记到具体窗口，重试有独立记录。仅限流、可恢复网络/服务端错误最多两次重试；认证、预算、schema 错误不自动重试。账本限制 maxCostCny/maxRequests/maxInputFrames（含重复上传），发送前预留保守预算。当前快照 `deepseek-flash-cny-2026-10-04` 保存高峰/闲时 CNY 价格及官方来源，捕获日期不是账单或声明生效日。默认用 1M 输入上界、高峰缓存未命中价与输出上限预留；缓存用量完整且模型别名已知时结算 estimated，缺失则保留整个未知预留。请求时段按 UTC+8 周末/高峰判定，法定节假日未知时采用保守高峰价。

冷成本/小时 = 所有计费尝试的原币费用按冻结汇率折算人民币 / 冻结素材时长小时。人民币定价无需汇率；其他币种缺汇率则 unknown。缺计费用量、价格、失败是否计费等证据时 `cost_status=unverified`、门槛 null。估算 estimated、账单核对 confirmed，赠送余额不抵消可规模化单位成本。GPU 秒、墙钟时间、人工主动分钟另报。§51 `<¥5/h` 作为建议成本目标，不能用热缓存通过。[DeepSeek 价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

复用只限成功且完整校验的 checkpoint 或固定本地 embedding 缓存。配置/输入 hash 包含源/证据、预处理、模型/修订、prompt 内容 hash、schema 和稳定参数；embedding 再含文本 hash、维数/归一化/推理空间身份。ASR 或 prompt 变化拒绝原 run 续跑，修改配置创建新 run。哈希读源文件采用流式，不把大视频读入内存。

若实际修订 unresolved，`response.model` 别名不足以标识向量空间或长期缓存：缓存仅在同一 run 的 checkpoint/resume 复用，不跨 run 自动命中；该 run 的 embedding 禁止与其他 run 混检。冻结的实验响应可作离线 fixture 回放，必须标明 snapshot ID，不能声称新请求仍使用同一模型修订。

Ctrl+C 停止新任务、取消 Provider、保存状态；FFmpeg/ASR worker 要显式终止并限时回收，取消 asyncio 等待不保证终止 OS 进程。结构化参数、禁止 shell 拼接，Windows 使用隐藏子进程；逐进程登记生命周期。异常稳定分类：input/media/auth/rate-limit/network/schema/budget/storage/cancelled。[Python 子进程](https://docs.python.org/3.13/library/asyncio-subprocess.html)

凭据从进程环境/本地密钥存储读取，不进入 Git、prompt、账本或错误输出。共享配置仅有 Provider 名、模型、端点及预算参数。结构化日志可关联 run/stage/invocation；计费账本不依赖采样日志。

## 7. 验收、开放问题与实施顺序

质量协议见 [benchmark 规格](../references/phase-0-benchmark.md)。真实清晰机制查询仍须 Top10 独立可用结果 ≥70%；补齐人工标签前不可标 Phase 0 通过。速度报告墙钟/素材时长实时比与配置，原方案没有硬速度阈值，本轮不编造阈值。§44 整条创作时间节省在后续生成发布包阶段验证。

当前真实 PV Demo（95.175874s）完成24窗口/111事件/0转录，run `f76f5d6495314c04ae04083614d4afd6` API 估价 ¥0.06246088，未账单确认。早期 run `823799e10a0440e8aec8b78b603bec57` 在2/24窗口后因 provider.schema 停止，原响应未保存，不能声称已查明具体模型错误。新 prompt 成功不抹去该失败。

早期失败 run 估价 ¥0.01163912、10事件、0未知调用；两 run 本轮 API 估价合计 ¥0.0741，不能只把成功 run 费用当全轮成本。实际完整 run 的运行成功和离线重读仍不代表人评验收。

开放实验项：人工 ASR/机制标签、独立录制会话、小时级素材性能/成本、第二真实视觉 Provider、采样密度与检索阈值。F001–F005技术合同已验收，F006 人评 gate 仍未验证。用户授权的本地检查工作台遵循 [ADR-002](./adr-002-local-inspection-ui.md) 和 [API合同](./inspection-workspace-api.md)，提供注册视频/证据预览、查询、筛选和区间清单导出。其浏览器时间映射只在现有PV验证，非零PTS/音视频起点不同的容器须另测。正式桌面、MP4渲染与商业系统尚未实现。

实施依赖：F001 环境/合同工程 → F002 媒体映射 → F003 ASR/视觉与账本；F004 存储依赖 F001，可与 F002/F003 并行；F005 依赖 F003＋F004，包含 F002 的传递依赖；F006 独立标签准备可以先行，最终质量 gate 在集成后执行。详见 [开发任务](../exec-plans/phase-0-plan.md)。
