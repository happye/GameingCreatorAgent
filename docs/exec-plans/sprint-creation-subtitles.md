# R2字幕：源语音映射到成片字幕

2026-10-30，按加速路线接下一项制作功能。并行先实现纯时间映射及SRT编解码，UI切片完成后接实际导出/渲染入口；没有公开入口和真实产物前不把字幕整项算完成。

ownership：独立creation-subtitles工作树，domain/creation_subtitles.py、application/creation_subtitles.py、tests/test_creation_subtitles.py由一个Sol/medium拥有，不改正在并行实现的CLI/renderer/server/static或公共文档，不递归。不是唯一开发者，保留他人修改。

复用RenderPlan/RenderClip和TranscriptSegment：每个编辑源区间与同media_id的已保存语音求半开交集，裁到片段实际输出时长，按EDL顺序累加输出帧；源微秒和成片有理数时钟明确映射，禁止浮点累计漂移、跨媒体串字幕或把未覆盖语音编造出来。只用已有ASR/用户字幕，不发模型/下载。

输出Cue类型、可调用build_subtitles(plan, transcripts)和SRT文本编解码（具体签名可小幅简化并说明）。SRT时间毫秒量化后0≤start<end，编号连续，清理可能误入结构的CR/空白但保留用户文字，重排/切分/重复使用片段对应各自输出位置。原transcript不改，uncertainty保留到内部cue，不把转录可靠性写成人评通过。

必要行为验证：跨剪点语音裁切；两源相同时间不串；非源顺序/重复用片映射；片外语音无字幕；非整秒输出帧不漂移；SRT中英文多行/重读/非法时间拒绝；空转录生成明确空字幕。Ruff/mypy必要检查，不跑全量。后续主控接CLI导出/成片字幕和真实片段烧录验证时再计对应部分/完成。

2026-10-30额度收尾：用户提醒剩余不足8%，停止新功能。Sol/medium已在creation-subtitles工作树完成上述3文件，报告15测试/Ruff/mypy通过；build_subtitles(plan,transcripts)→tuple[SubtitleCue,...]，Cue用Fraction秒，serialize_srt/parse_srt。含箭头结构/NUL文本明确拒绝，毫秒量化零长略过。尚未独立审查、未集成主树、未接公开导出/实际成片，不计字幕功能完成。路径/三文件SHA已保存.cache/subtitle-handoff.json，工作树保留，恢复时先读该记录，不重新从零实现。
