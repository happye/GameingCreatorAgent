# R2字幕：源语音映射到成片字幕

2026-10-30，Goal已恢复，按加速路线接下一项制作功能。复用已保存的纯映射核心，接公开SRT及实际烧录入口；没有公开入口和真实产物前不把字幕整项算完成。

## 本轮交付与证据

已集成：公开CLI/PS和工作台三种字幕选择、逐准确分析版本的语音映射、SRT下载与真实ASS烧录；下载固定任务路径、字幕SHA进完成收据、旧none任务兼容。联合64测试通过（含原15渲染），Ruff通过，6源码mypy通过；唯一Sol/high关键评估PASS（静态审查，不冒称亲跑测试）。

真实页面使用原demo-phase0的无转录版本：6秒MP4完成、SRT为空且明确0条、下载成功，刷新0新POST、无页面错误；记录.cache/subtitle-workspace-real-browser.json。非空烧录用本地合成素材验证重排/时间窗/像素和源SHA，中文“本地字幕测试”单项实测通过并查看.cache/subtitle-chinese-frame.png；不是原录像语音质量验收。已有ASR旧项目只读加载提示迁移，不改原库、不为演示补写语音。

当前限制：只能用已保存语音；字幕文本/样式编辑尚未接入，烧录百分之一秒精度，ASS特殊反斜杠和花括号用全宽可见字符。P029由未开始变部分，全部51项10/13/28≈32%，首产品0/7/15≈16%。下一步按架构师合同实现镜头裁短/排序/删除、不可变版本及撤销重渲染；不等待人评，不产生模型费用。

## 当前公开切片合同

- Sol/medium `subtitle_render_public`：独立subtitle-render-public工作树，拥有原3个核心文件、cli/creation_render.py、main.py相关参数、infrastructure/ffmpeg_render.py、scripts/render-creation.ps1及新增字幕渲染测试。公开`--subtitles none|sidecar|burn`，缺省none；只读各片段原Completed版本的转录，生成成片时间字幕，不跨分析版本混用。
- Sol/medium `subtitle_workspace_public`：独立subtitle-workspace-public工作树，拥有ui/creation_jobs.py、server.py、creation静态页及相关测试。工作台可选不加字幕、导出SRT、烧入并导出；新增可选subtitleMode，旧请求兼容。固定字幕下载地址，不接受客户端文件路径；请求、完成收据和下载SHA绑定。
- 主控：公共合同、集成、真实浏览器/产物验证；唯一Sol/high关键评估者在实现完成后检查来源时钟和持久任务边界。Astra/low只读准备下一编辑修订方案，不阻塞字幕实现。

完成标准：已有语音按剪辑顺序生成SRT；重排/裁切仍时间正确；sidecar/burn产物收据包含SRT哈希，视频真实可解码且烧录区间有文字；无转录明确0条；旧none行为和已完成任务可回查。原素材/分析/费用不改，0新模型/ASR/下载。工作台完成选择、视频预览与SRT下载后，仅计P029部分实现，修改字幕/样式/完整质量仍有后续任务。针对性行为测试和真实产物证明，不重跑旧全量。

ownership：独立creation-subtitles工作树，domain/creation_subtitles.py、application/creation_subtitles.py、tests/test_creation_subtitles.py由一个Sol/medium拥有，不改正在并行实现的CLI/renderer/server/static或公共文档，不递归。不是唯一开发者，保留他人修改。

复用RenderPlan/RenderClip和TranscriptSegment：每个编辑源区间与同media_id的已保存语音求半开交集，裁到片段实际输出时长，按EDL顺序累加输出帧；源微秒和成片有理数时钟明确映射，禁止浮点累计漂移、跨媒体串字幕或把未覆盖语音编造出来。只用已有ASR/用户字幕，不发模型/下载。

输出Cue类型、可调用build_subtitles(plan, transcripts)和SRT文本编解码（具体签名可小幅简化并说明）。SRT时间毫秒量化后0≤start<end，编号连续，清理可能误入结构的CR/空白但保留用户文字，重排/切分/重复使用片段对应各自输出位置。原transcript不改，uncertainty保留到内部cue，不把转录可靠性写成人评通过。

必要行为验证：跨剪点语音裁切；两源相同时间不串；非源顺序/重复用片映射；片外语音无字幕；非整秒输出帧不漂移；SRT中英文多行/重读/非法时间拒绝；空转录生成明确空字幕。Ruff/mypy必要检查，不跑全量。后续主控接CLI导出/成片字幕和真实片段烧录验证时再计对应部分/完成。

2026-10-30额度收尾：用户提醒剩余不足8%，停止新功能。Sol/medium已在creation-subtitles工作树完成上述3文件，报告15测试/Ruff/mypy通过；build_subtitles(plan,transcripts)→tuple[SubtitleCue,...]，Cue用Fraction秒，serialize_srt/parse_srt。含箭头结构/NUL文本明确拒绝，毫秒量化零长略过。尚未独立审查、未集成主树、未接公开导出/实际成片，不计字幕功能完成。路径/三文件SHA已保存.cache/subtitle-handoff.json，工作树保留，恢复时先读该记录，不重新从零实现。
