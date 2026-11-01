# Sprint T25：时间线导出音字轨实验（P033）

**状态（2026-11-01）：已完成（结构级最佳努力；真机 NLE 导入仍非宣称）。**

## 目标

在现有 FCPXML 1.9／OTIO／xmeml 导出上，做**字幕轨与立体声音轨**的最佳努力写出＋夹具测试；明确：**未**在 Final Cut／DaVinci／Premiere 真机验证导入。

## 非目标

- 不宣称 NLE 可完整还原样式／声道布局／字幕引擎
- 不下载体、不发布、不碰 F006
- 不把实验轨写成「已商用验收」

## 设计

### ExportCaption

输出时钟整帧：`start_frame`／`end_frame`／`text`。可由 `captions_from_cues(SubtitleCue…, fps)` 从成片字幕换算（量化到帧）。

### 立体声音轨（best-effort）

- **FCPXML**：资源仍 `hasAudio="1"`；每个 `asset-clip` 在启用时写入 `<audio-channel-source srcCh="1,2" …/>`（声明立体声意图）
- **OTIO**：追加 `Track` `kind=Audio` 名 `A1`，clip 与画面同源、同时长；`metadata.gamingcreator.audio="stereo-best-effort"`
- **xmeml**：在 `<media>` 下追加 `<audio><track>`，clipitem 与视频同 file／in／out／时间线起止

### 字幕轨（best-effort）

- **FCPXML**：spine 上 `lane="1"` 的 `<title>`（Basic Title 文本），带 `gamingcreator` 注释式 name 前缀可选；仅结构
- **OTIO**：追加 Caption track（`kind=Video` 名 `Captions`），clip `name=text`，metadata `caption=true`
- **xmeml**：sequence 级 `<marker>`（in/out/name=text）；非 Generator 字幕引擎

均在 timeline／sequence metadata 保留 `importVerified: false`（OTIO）及模块头注释声明未真机导入。

### 接线

- `to_fcpxml`／`to_otio`／`to_xmeml` 增加 `captions=()`、`include_audio_track=False`（默认保持旧形状兼容）
- `creation_jobs.timeline_export`：导出时 `include_audio_track=True`；若链上可建字幕则填 captions，否则空

### 测试夹具

- 固定 EDL＋2 条 ExportCaption；断言三格式出现音／字结构
- 旧测试仍通过（默认关音轨、无字幕）
- 文档写明非宣称

### Acceptance

- [x] sprint 设计
- [x] 三格式音／字 best-effort
- [x] 夹具测试
- [x] P033 evidence 谨慎追加
- [x] 文档；grok T25 ✅；下一＝T26
