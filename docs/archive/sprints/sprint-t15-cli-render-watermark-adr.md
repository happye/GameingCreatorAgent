# Sprint T15：CLI render-creation 水印 ADR

**状态（2026-11-01）：已完成（3f73b48）**

## 目标

就 CLI `render-creation` 是否读取套餐水印做书面决定；复审结论为开发者路径**默认不加**。

## 决定

见 [adr-004-cli-render-creation-watermark.md](../../design-docs/adr-004-cli-render-creation-watermark.md)：**接受**保持 `watermark=None`，不改 CLI 行为。工作台 Free 水印不变。

## Acceptance

- [x] ADR-004 落盘并接受
- [x] 代码行为未改（main 不传 watermark）
- [x] 文档同步；T15 ✅
