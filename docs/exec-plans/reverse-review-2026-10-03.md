# 技术反向审查：2026-10-03

范围：原总方案 §70 的六个审查方向；产品方向保持原定。结论是进入 Phase 0 工程实施与实验，不是认定语义检索已经通过。实测证据见 [验证记录](./phase-0-validation-2026-10-03.md)，工程合同见 [工程规格](../design-docs/phase-0-engineering-spec.md)。

## 1. 技术可行性

FFmpeg 本地预处理 → ASR/视觉证据 → SQLite 语义时间线 → 自然语言检索是一条可实现的链路。已在合成媒体验证抽帧、16kHz 单声道音频提取、无音轨继续处理；已用三个真实短视频、15 张关键帧调用 DeepSeek 并获得结构化观察。尚未验证 ASR、完整时轴、数据库恢复、检索质量、长录像速度或第二 Provider。

原方案 §9 的核心假设包含质量、长视频和成本三个条件，任何一个不能用另一个替代。两段 PV 加一段标为“实机”的剪辑共约 214.86 秒，适合请求链路和视觉初测，不能代表小时级未剪辑素材。后续需要 §46 的 10–20 段代表录像和人工事件标签。

## 2. 系统架构

采用 Python 的 cli、application、domain、infrastructure 四层包，Media、ASR、Vision、Timeline、Retrieval 作内部模块；语言选择见 [ADR-001](../design-docs/adr-001-phase-0-language.md)。原方案 §54 是长期组织方向，不需要 Phase 0 创建所有空工程。领域模型与 SDK、SQLite、FFmpeg 解耦；接口交换带源时间的证据和结构化结果。

新增必须合同：源 PTS 映射、Provider 能力声明、每次计费尝试账本、阶段 checkpoint、恢复策略、输出 schema、检索去重。SQLite 与文件系统没有跨系统原子事务；先完整写文件再事务登记并校验恢复。WAL 不允许多个同时写入者，模型调用不得跨越数据库写事务；同步 sqlite3 连接保持线程归属。[SQLite WAL](https://www.sqlite.org/wal.html)、[Python sqlite3](https://docs.python.org/3.13/library/sqlite3.html)

## 3. 模型能力

已核实 DeepSeek 当前 `deepseek-flash` 支持图像输入；本轮通过本地抽帧调用它。其已文档化 Chat 输入没有原生视频或音频块，因此不将图片序列支持等同于原生视频理解。JSON mode 只解决 JSON 输出格式，领域字段、时间边界和事实仍需程序校验和人工审查。[DeepSeek Vision](https://api-docs.deepseek.com/guides/vision/)、[JSON mode](https://api-docs.deepseek.com/guides/json_mode/)

风险：爆炸特效不等于墙被破坏；ASR 提到机制不等于画面展示了机制；静态帧不能证明动作发生顺序。事件要存 visible facts、证据 ID、模态和 uncertainty，允许 unknown。初测返回的 `possibleMechanics` 是候选推断，不能直接用于人工判分。

ASR 优先本地，先一个实现，再对照替换。faster-whisper 支持 CPU/GPU 和时间码；FunASR 是中文与热词对照候选，权重、运行时与硬件兼容仍需实测。无音轨、无语音、处理失败必须分开，视觉链路不能因缺语音失败。[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[FunASR](https://github.com/modelscope/FunASR)

## 4. 视频处理

最高风险是证据在采样阶段丢失。1 秒间隔采样不保证捕获短动作；廉价模型筛掉的窗口不能靠之后的强模型找回。保持覆盖全时轴的粗分析，比较 1 FPS、2 FPS 和覆盖＋加密策略，并对被过滤窗口随机审计。原方案 90%/10% 是待验证比例，不是写死的架构常量。[Gemini 视频采样限制](https://ai.google.dev/gemini-api/docs/video-understanding)

VFR、非零起点、音视频偏移、切片和 VAD 都可能让时间码失真。保存流 PTS、timebase 和源归零映射，不能用帧序号/标称 FPS 计算源时刻。当前 spike 只校验解码输出时间递增，未完成这些映射合同。[FFmpeg showinfo](https://ffmpeg.org/ffmpeg-filters.html#showinfo)

## 5. 商业化与成本

§51 的建议目标 `<¥5/源素材小时` 与优化 `<¥2` 保留，逐调用记录用量、价目版本、时段和重试。初测 API 估算不能按完整视频时长外推，因为每视频只发送五帧。缺价格或用量时成本 unknown，不能写零。

当前 DeepSeek 价格分高峰和空闲时段；图像 token 与文本共同计费，缓存命中不能当作首次分析成本。按文档单图 1024 token 上界推算，1 FPS 每小时最多约 369 万图像 token，输出和重试尚未计入；这是预算压力示例，不是实测消耗。[Vision 计量](https://api-docs.deepseek.com/guides/vision/)、[人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

整条内容制作节省 >60%、可投稿、复用和付费是 §43–44、67 的后续商业验证。Phase 0 检索耗时不能替代这些证据。本机 FFmpeg 构建包含 GPL 组件；正式分发需固定二进制、组件许可证和对应合规方案，不能把本机可运行推导成可直接商业打包。[FFmpeg 许可说明](https://ffmpeg.org/legal.html)

## 6. 工程风险与维护

用户明确 C# 不是硬约束后，将初版 .NET 建议改为 CPython 3.13 模块化核心：直接使用 ASR/评测生态，减少跨语言 IPC 与双运行时负担；Windows 正式 UI 后续另选。尚未安装项目 uv/Python 或构建应用。先冻结 CLI/DTO/账本和恢复合同，再拆任务，类型与导入检查约束多 Agent 开发。性能优势不能凭语言宣称，仍要测量；取舍与回退见 [ADR-001](../design-docs/adr-001-phase-0-language.md)。

API 超时和取消可能已产生费用；调用发出前记录 attempt，恢复不能把 unknown 请求自动当免费重放。缓存必须包含内容、采样配置、Provider/模型修订、prompt/schema，不能只靠文件路径。模型浮动别名无法确认修订时限制长期缓存复用。

## 风险优先级与处理

| 风险 | 级别 | 验证或处理 |
| --- | --- | --- |
| 采样或粗筛漏掉游戏事件 | P0 | 标注事件＋采样对照＋被过滤窗口审计 |
| 模型描述正确却检索片段不可用 | P0 | 看原片段人工评级，不看模型摘要判分 |
| Top10 缺项/重复灌水与测试集泄漏 | P0 | 固定分母、独立事件、按录制会话冻结集 |
| 时间轴失真、ASR 静音误转写 | P1 | PTS/VFR/偏移/VAD 回映射测试 |
| 断点、SQLite 和文件不一致 | P1 | 阶段故障注入和单写恢复测试 |
| 重试、图片用量和价格变动 | P1 | attempt 账本、预算停止、未知成本阻止通过 |
| 无隔离 Python 环境/本地 ASR 权重 | P1 | 固定运行时与依赖，不以文档假装构建通过 |
| 商业分发与多运行时负担 | P2 | 先外部 FFmpeg、一个本地 ASR；分发前评审 |

## 收敛决定

Phase 0 实现本地输入、ASR 与视觉、语义时间线、SQLite、自然语言查询、候选时间码和可重复评测。OCR、情绪打分、完整素材评分、知识 RAG、创作规划、渲染、UI、平台与商业系统按原方案阶段推进。先对照验证现成模型，不训练基础模型。这个范围没有改变产品方向，而是落实 §58–59、71 的先后顺序。
