# Phase 0 工程规格 v2

状态：实施合同；F001 输入/领域/Provider 基础与 F002 媒体 service 已实现，完整分析流水线仍待后续特性。来源：原总方案 §58–59、69–71；按用户补充使用 Python，见 [ADR-001](./adr-001-phase-0-language.md)；审查：[reverse-review](../exec-plans/reverse-review-2026-10-03.md)。目标是让多个 Agent 按相同合同实现和验证。

## 1. CLI 与外部行为

用户硬约束：所有工具、包、模型权重和缓存隔离于本机系统。portable uv 放 `.tools/uv`，CPython 3.13 运行时放 `.tools/python`，应用/开发/ASR 包全部装入 `.venv`；FFmpeg 放 `.tools/ffmpeg/bin`，缓存放 `.cache`。仅使用进程环境，不写注册表、系统/用户 PATH 或全局包目录；uv 注册和全局链接显式禁用。版本固定及校验在 F001 完成，详见 [隔离环境](../references/isolated-environment.md)。

以下命令入口和输入合同已建立，正常处理仍返回退出 3 / `feature.not_implemented`，不产生项目输出。实验脚本见 [验证记录](../exec-plans/phase-0-validation-2026-10-03.md)。

```text
gamingcreator analyze <local-video> --project <directory> --config <json> --max-cost-cny <amount>
gamingcreator analyze <local-video> --project <directory> --resume <run-id>
gamingcreator search "机制描述" --project <directory> --run <completed-run-id> --top-k 10 --format json
gamingcreator benchmark --input <frozen-manifest> --project <directory> --output <report.json>
```

`analyze` 校验文件、能力、预算和空间后创建 run。首次成功写 SQLite 与 `semantic_timeline.json`；失败或取消输出 run ID 和稳定错误码，保持已完成 checkpoint。resume 使用原配置，配置变更创建新 run，不能拼接不同版本结果。

F001 配置边界：`config.example.json` 的 `schemaVersion=1`，仅接受 `vision.provider/model` 两个非空字符串、`limits.maxRequests/maxInputFrames` 两个正整数；未知字段（包括密钥）被拒绝。新分析费用上限由 CLI 传入有限正 Decimal；resume 不接受配置或预算覆盖。完整 ASR/采样/端点配置在相应特性扩展 schema，不能默默忽略旧字段。

`search` 指定完整 run；找不到时返回明确错误。候选含 `candidateId, mediaId, eventId, startUs, endUs, sourceTimecode, score, scoreKind, evidenceIds`；时间采用半开区间，分数说明其语义，不表示事实成立的概率。稳定排序先 score，再 mediaId/startUs/candidateId。空结果合法并附原因，不编造镜头。保留 rank、去重和排除理由。

stdout 为结果或 JSON；进度/JSON 诊断写 stderr。退出码：0 成功，2 输入，3 环境/配置，4 Provider，5 存储/完整性，6 benchmark 未过门槛，7 预算停止，130 用户取消。JSON 错误含 code、runId、retryable、友好说明，不含凭据。

## 2. 时间与数据合同

所有领域时间是从源视频规范化起点计量的 Int64 微秒 `[startUs,endUs)`；非负且小于等于源时长，Python int 必须校验不超过 `2^63-1`。格式化显示时间可以舍入，持久化不可用显示字符串反推。Evidence 另存原始 PTS、timebase、streamStart、切片偏移、音视频偏移和变换版本；模型局部时间由程序回映射并检查范围，VAD 必须有回映射。

F002 采用最早选中流 presentation start 为共同 origin，精确 Fraction 先相减，点/起点 floor 到微秒，终点/时长 ceil。音频输出保留逐帧 sampleOffset/PTS/样本数；gap/overlap 与≤1输出样本的边界量化裁切均可追溯。按元信息音轨 end_pts 裁去本次解码观察到的越界样本。完成 bundle 不等于 Completed AnalysisRun。实现/支持范围见 [媒体合同](../references/media-processing.md)。

| 记录 | 必需字段 |
| --- | --- |
| MediaAsset | mediaId、源路径（本地）、SHA256、durationUs、streams、probeVersion |
| Evidence | evidenceId、mediaId、kind、源区间/时刻、PTS/timebase、artifactPath、hash、transformVersion |
| TranscriptSegment | mediaId、源区间、text、词级时间可选、ASR 模型/版本、状态 |
| SemanticEvent | eventId、mediaId、源区间、observableFacts、mechanicTags、evidenceIds、modality、uncertainty、runId |
| Embedding | subjectId、provider/model/revision、dimension、normalization、vector、textHash |
| CandidateClip | candidateId、eventId、源区间、rank、scoreKind/score、证据与排除原因 |
| AnalysisRun | runId、配置快照/hash、pipelineVersion、状态、开始/结束/错误 |
| StageCheckpoint | runId/stageId、输入/输出 hash、状态、attempt、错误 |
| ProviderInvocation | invocationId、run/stage、attempt、Provider/模型、用量、价格/币种、费用状态、耗时、requestId |

`confidence`、GPU 时间和供应商未提供用量可以 null；未知不是 0。推断机制与可观察事实分开。没有足够证据的动作边界存不确定性，不允许模型输出越界时间或编造 evidenceId。OCR/情绪等后续字段可缺失，未测量值不能虚填。

## 3. Provider ports 与首个实现

Application 用 `typing.Protocol` 定义类型化 async ports，await 得到 `ProviderResult[T]`，请求携带明确取消/超时上下文。`VisionProvider.analyze(VisionRequest)`、`AsrProvider.transcribe(AsrRequest)`、`EmbeddingProvider.embed(EmbeddingRequest)` 对应原方案 IVisionModel/IASRModel/IEmbeddingModel；查询扩展/重排需要时用 `LlmProvider.complete(StructuredRequest)`。不创建 Phase 0 不用的 IImageModel 实现。

同步 ASR/原生推理放可终止 worker，由异步 facade 收集完整结果并校验；不能仅用取消 await 或线程假装终止推理。faster-whisper segments 的惰性迭代必须在 worker 内完成，再返回可序列化段落。[官方运行语义](https://github.com/SYSTRAN/faster-whisper)

请求含 runId、输入证据引用、语言/游戏词表、prompt/schema 版本、输出预算；结果含 typed output、usage、实际 model/revision、requestId、elapsed、状态与错误。Capabilities 声明图片序列/视频/音频、尺寸/数量限制、结构化输出和局部时间语义。Capability mismatch 在请求前失败。

首个视觉 Provider：DeepSeek `deepseek-flash`，`POST https://api.deepseek.com/chat/completions`，`user.content` 用带时间说明的 text 与 `image_url`；只上传选定证据，不上传整视频。禁用 thinking 的对照使用 `json_object`，输出经过字段、证据和时间校验，`finish_reason=length` 不算成功。当前模型别名可浮动，记录 response.model；不能识别修订时明确 unresolved，而不是假装固定版本。[官方 Vision](https://api-docs.deepseek.com/guides/vision/)

ASR 初始选本地 CPU 可运行方案，faster-whisper 为候选，FunASR 作中文/热词对照；先验证运行时和权重再锁实现。`no_audio/no_speech/completed/failed` 分开。本地模型也记录模型、权重 hash、耗时与计量；ChatGPT/开发工具额度不等于项目模型 API 配额。

## 4. SQLite v1 逻辑 schema 与迁移

迁移表 `schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)`；迁移有事务和集成测试。下面定义数据合同，物理 SQL 与索引在 F004 依据此表实现、验证并版本化。

| 表 | 主键、关系及约束 |
| --- | --- |
| media_assets | media_id PK；content_hash、duration_us>0；同项目同内容去重 |
| analysis_runs | run_id PK；配置/pipeline hash、status；绑定 media_id FK |
| stage_checkpoints | (run_id,stage_id) PK；状态、输入/输出 hash、更新时间 |
| evidence | evidence_id PK；media_id/run_id FK；有效源时间、artifact hash/path |
| transcript_segments | id PK；media_id/run_id FK；区间、文本、状态/模型版本 |
| semantic_events | event_id PK；media_id/run_id FK；有效区间、结构化事实与标签 |
| event_evidence | (event_id,evidence_id) PK；两个 FK，不允许悬空证据 |
| embeddings | (subject_id,provider,model,revision_scope,dimension,normalization,text_hash) 唯一；revision_scope 为已确认修订或隔离的 run ID；禁止不同向量空间混检 |
| provider_invocations | invocation_id PK；attempt、状态、用量/价格快照/费用、unknown 字段可 null |
| retrieval_runs/hits | query/runId、rank、candidateId、版本和排序参数；供复现和人工标注 |

使用标准库 `sqlite3`，连接启用 FK、WAL、`synchronous=FULL`；写事务短，有限 busy timeout；每项目一个分析写入者。连接在其所属线程创建和使用，不共享跨线程连接；明确配置事务行为，不依赖 Python 默认值。同步 DB 操作由受控单写队列/专用线程执行，不能阻塞网络事件循环或在事务内等待媒体/模型。WAL 仍是单写。[WAL](https://www.sqlite.org/wal.html)、[Python sqlite3](https://docs.python.org/3.13/library/sqlite3.html)

文件先写临时路径、完成校验和最终落盘，再事务登记与 checkpoint；恢复检测数据库已登记但文件丢失/损坏、未登记孤立文件和 Running 未完成阶段。可重做本地阶段，网络 attempt 的 unknown 计费不能默认免费重放。只从一致且 Completed 的 run 搜索；备份使用 SQLite backup API，而非任意复制活动 DB/WAL。

## 5. 采样与检索实验

保持全时轴覆盖而非先挑高光。冻结素材后对照：1 FPS、2 FPS、低密度覆盖＋候选加密、小样本强模型/高密度基线；评测短事件漏检和被过滤窗口。窗口大小、重叠、分辨率、场景触发阈值是配置并写入缓存键，先小规模找到质量/成本可接受组合，不将 90/10 写死。

检索先建立词法基线，再对照语义扩展/embedding 与重排，记录采用方案。事件是去重单位：同一动作切成不同片段仍属一个事件。模型识别 eventId 和人工 benchmark 事件归属分开，通过人工匹配评价。冷运行与缓存运行分开，测试集按录制会话隔离，同源 PV/剪辑不得跨开发和测试集。

## 6. 成本、缓存、恢复与取消

每个网络 attempt 在发送前登记，重试有独立记录。仅限流、可恢复网络/服务端错误有限退避（初版最多两次重试）；认证、预算、领域校验错误不无限重试。配置 `maxCostCny`、`maxRequests`、`maxInputFrames`，发新请求前预留保守预算，无法估计时停下来记录缺口。价目时段改变要换版本。

冷成本/小时 = 所有计费尝试的原币费用按冻结汇率折算人民币 / 冻结素材时长小时。人民币定价无需汇率；其他币种缺汇率则 unknown。缺计费用量、价格、失败是否计费等证据时 `cost_status=unverified`、门槛 null。估算 estimated、账单核对 confirmed，赠送余额不抵消可规模化单位成本。GPU 秒、墙钟时间、人工主动分钟另报。§51 `<¥5/h` 作为建议成本目标，不能用热缓存通过。[DeepSeek 价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

缓存键包含源/证据 hash、源区间、预处理配置/版本、Provider/实际模型修订、prompt 内容 hash、schema、生成参数；embedding 再含文本 hash、维数/归一化。仅复用成功且完整校验结果；模型、采样或 prompt 变化失效。哈希读源文件采用流式，不把大视频读入内存。

若实际修订 unresolved，`response.model` 别名不足以标识向量空间或长期缓存：缓存仅在同一 run 的 checkpoint/resume 复用，不跨 run 自动命中；该 run 的 embedding 禁止与其他 run 混检。冻结的实验响应可作离线 fixture 回放，必须标明 snapshot ID，不能声称新请求仍使用同一模型修订。

Ctrl+C 停止新任务、取消 Provider、保存状态；FFmpeg/ASR worker 要显式终止并限时回收，取消 asyncio 等待不保证终止 OS 进程。结构化参数、禁止 shell 拼接，Windows 使用隐藏子进程；逐进程登记生命周期。异常稳定分类：input/media/auth/rate-limit/network/schema/budget/storage/cancelled。[Python 子进程](https://docs.python.org/3.13/library/asyncio-subprocess.html)

凭据从进程环境/本地密钥存储读取，不进入 Git、prompt、账本或错误输出。共享配置仅有 Provider 名、模型、端点及预算参数。结构化日志可关联 run/stage/invocation；计费账本不依赖采样日志。

## 7. 验收、开放问题与实施顺序

质量协议见 [benchmark 规格](../references/phase-0-benchmark.md)。真实清晰机制查询仍须 Top10 独立可用结果 ≥70%；补齐人工标签前不可标 Phase 0 通过。速度报告墙钟/素材时长实时比与配置，原方案没有硬速度阈值，本轮不编造阈值。§44 整条创作时间节省在后续生成发布包阶段验证。

开放实验项：本地 ASR 权重/运行时、完整采样配置、首个 embedding 实现、第二视觉 Provider、独立录制会话/标签、等待时间容忍。环境/CLI 合同已验收 F001，局部媒体 service 已验收 F002；SQLite、ASR、检索和完整分析命令仍待实现。工程合同和 spike 通过不替代这些条件。

实施依赖：F001 环境/合同工程 → F002 媒体映射 → F003 ASR/视觉与账本；F004 存储依赖 F001，可与 F002/F003 并行；F005 依赖 F003＋F004，包含 F002 的传递依赖；F006 独立标签准备可以先行，最终质量 gate 在集成后执行。详见 [开发任务](../exec-plans/phase-0-plan.md)。
