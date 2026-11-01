# Sprint T23：渲染裁切画面／简单叠加（P028）

**状态（2026-11-01）：已完成。**

## 目标

在本地 FFmpeg 成片路径上补齐两类**表现层**能力，并写入 `creation-render-receipt-v1`：

1. **安全区裁切（safe-area crop）**：在 letterbox 成帧后，按每边百分比裁掉边缘，再缩放回目标宽高（偶数像素），避免平台 UI 挡边时只靠后期猜测。
2. **静态角标叠加（static corner badge）**：与 Free 套餐水印（右上 ASS）分离的短文本角标，默认左下，四角可选；同样走 ASS，不引入 PNG 素材依赖。

先设计后实现；媒体测试字节封顶；不下载、不发布、不碰 F006。

## 非目标

- 不做动态跟踪角标、贴纸时间线、多图层编辑器
- 不改平台导出包的二次裁切逻辑（仍由 package 路径负责）
- 不宣称创意质量已人评；P028 仍为 partial
- 不强制默认开启裁切／角标（缺省行为与 T22 前一致）

## 现状

- `clip_filter`：源时钟 trim + scale/pad letterbox 到 WxH
- 成片 `-vf`：`tpad/fps/trim` → 可选烧录字幕 ASS → 可选 Free 水印 ASS
- 收据 `limitations` 仍含「no overlays」／「only the plan watermark」
- 平台包另有 crop/pad；本 sprint 补的是**创作成片**层

## 设计

### PresentationOptions（domain）

`creation_presentation.py`：

- `safe_area_margin_percent: int` ∈ `{0} ∪ [1, 40]`；`0`＝关闭
- `badge_text: str | None`；非空时 `1..24` 纯文本，禁止 `{}\\\n\r`
- `badge_corner: str` ∈ `top-left|top-right|bottom-left|bottom-right`；默认 `bottom-left`（避开 Free 水印右上）
- `from_json` / `to_json` / `enabled`；非法值 fail closed

### FFmpeg 顺序（成片 `-vf`）

1. `tpad` → `fps` → `trim` → `setpts`（不变）
2. **若 margin>0**：`crop=cw:ch:x:y,scale=W:H`（cw/ch 为偶数；居中）
3. burn 字幕 ASS（若有）
4. **角标 ASS**（若有）
5. Free 水印 ASS（若有）

裁切在叠加之前，保证角标／水印落在最终画幅角上。

### 收据

有启用项时写入（全关则省略以保持旧收据形状兼容）：

- `presentation.version` = `creation-presentation-v1`
- `presentation.safeArea` = `{ marginPercent }` 或 `null`
- `presentation.badge` = `{ text, corner }` 或 `null`

`limitations`：

- 启用裁切时追加 `safe-area center crop then scale`
- 启用角标时用 `static corner badge overlay` 替代「no overlays」表述；若同时有水印则并列说明

### 接线

- `FfmpegCreationRenderer.render(..., presentation: PresentationOptions | None = None)`
- `execute_render_creation` / CLI `render-creation`：可选 `--safe-area-margin`、`--badge-text`、`--badge-corner`
- `creation_jobs` render 请求 optional：`safeAreaMarginPercent`、`badgeText`、`badgeCorner`；校验后传入
- `render_revision` 同样读取 request 可选字段

### 测试（字节封顶）

- 小 lavfi 源（≤320×180、短时长）真实 FFmpeg
- 安全区：margin>0 时收据字段正确；关闭时无 `presentation`
- 角标：左下亮区断言；非法 margin／角标文本拒绝
- 不引入大媒体

### Acceptance

- [x] sprint 设计先于实现（本文件）
- [x] PresentationOptions + FFmpeg 路径 + 收据
- [x] CLI／jobs optional 接线
- [x] 字节封顶媒体测试
- [x] P028 evidence 谨慎追加；remaining 改为安全区／静态角标已有本地证据，创意质量仍未人评
- [x] 文档：HANDOFF／progress／assignments／progress-board／grok T23 ✅；下一＝T24
