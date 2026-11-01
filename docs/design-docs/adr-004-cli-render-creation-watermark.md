# ADR-004：CLI `render-creation` 不自动套餐水印

日期：2026-11-01。状态：**接受**。依据：第二轮对抗复审结论与 grok-task-list T15；工作台成片路径已按套餐烧入 Free 水印并写入收据。

## 背景

- 工作台 `CreationJobs` 在提交渲染时调用 `watermark_for(entitlement_selection())`，Free 套餐固化 `GamingCreator Free`，收据与发布包核验比对。
- CLI `gamingcreator render-creation` → `execute_render_creation(..., watermark=None)`：**未**读取套餐，也未暴露 `--watermark` 参数；默认不烧水印。
- 复审曾讨论「CLI 是否应与套餐一致」；结论是 CLI 属**开发者／批处理路径**，与面向用户的工作台套餐闸分离，避免脚本环境无「套餐与用量」上下文时误加或误缺水印。

## 决定

1. **保持** CLI `render-creation` 默认 **不** 根据本地套餐自动加水印（`watermark=None`）。
2. **不** 在本 ADR 范围内为 CLI 新增隐式套餐读取；若未来需要开发者显式打样水印，须另增可选参数（例如显式 `--watermark` 文本）并单独验收，仍不得静默读取付费状态冒充用户套餐。
3. 用户可见 Free 水印、收据与发布包核验继续以**工作台渲染路径**为准；文档（creation-guide）已注明 CLI 与工作台差异。
4. 本决定不批准真发布、支付或未授权视觉调用。

## 后果

- 用 CLI 渲的 MP4 可能无 Free 水印，即使工作台当前选中 Free——这是刻意的开发者路径，不视为套餐绕过产品缺陷。
- 对外分发／演示成片应走工作台（或将来显式参数），并核验收据 `watermark` 字段。
- 变更此默认（改为 CLI 自动读套餐）须修订本 ADR 后再改代码与测试。

## 验证

- `src/gamingcreator/cli/main.py`：`render-creation` 调用不传 `watermark`。
- `src/gamingcreator/cli/creation_render.py`：参数默认 `None`。
- 工作台 Free 水印测试保持有效（不在本 ADR 回退）。
