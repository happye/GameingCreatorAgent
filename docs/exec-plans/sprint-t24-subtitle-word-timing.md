# Sprint T24：字幕词级时序（若 ASR 已有）（P029）

**状态（2026-11-01）：已完成（探测结论＝缺口；映射器仅在真实词级载荷存在时工作；不造假时序）。**

## 目标

探测本机 ASR／字幕链路是否已有**词级时间戳**；有则映射到剪辑输出时钟；无则把缺口写清楚，**禁止**用均分句子等方式伪造词级时间。

## 探测结论（本机现状）

| 层 | 发现 |
| --- | --- |
| `asr_worker` → faster-whisper | `transcribe(...)` **未**传 `word_timestamps=True`；写出段仅 `{start,end,text}` |
| `TranscriptSegment` | 仅 `media_id` / `source_range` / `text` / `uncertainty`，**无** words |
| SQLite `transcript_segments` | 存 start/end/text/uncertainty，**无**词级列 |
| `build_subtitles` | 按**段**与镜头源区间求交映射到输出时钟 |

**结论：当前 ASR 产物不含词级时间戳。** T24 不开启模型词级开关、不改 ASR schema、不向成片写入伪造词 cue。

## 设计

### Probe

`application/asr_word_timing.py`：

- `probe_local_asr_word_timing()` → 结构化报告：`available=False`、缺口说明、证据锚点（worker 字段、域模型、存储）
- `words_from_provider_segment(payload)`：仅当 payload 含真实 `words[]`（每项需 text + start/end 秒或 us）才提取；缺字段／空表 → 空元组，**从不**按字符数拆句

### Map（仅真实词）

- `AsrWord`：source-clock `SourceRange` + text
- `map_words_to_edit_timeline(plan, words_by_media | per_clip)`：与段级字幕相同的求交／变速映射，产出 `SubtitleCue`（uncertainty=`asr-word`）
- 无词 → 空元组

### 非目标

- 不改 `asr_worker` 开启 `word_timestamps`（属 ASR 合同变更，另开任务）
- 不改默认 `build_subtitles` 行为
- 不宣称字幕质量／样式完成；P029 仍 partial

### 测试

- Probe 报告 `available=False` 且文案含缺口关键词
- 无 words 的段／payload → 提取为空
- **拒绝**伪造：给定仅有整段 text+区间、无 words 时映射结果为空
- 给定真实词级夹具（模拟「若 ASR 将来返回 words」）→ 输出时钟区间正确

### Acceptance

- [x] sprint 设计含探测结论
- [x] probe + 条件映射实现
- [x] 测试覆盖缺口与「有词才映射」
- [x] P029 evidence 谨慎追加；标明词级仍缺
- [x] 文档：HANDOFF／progress／assignments／progress-board／grok T24 ✅；下一＝T25
