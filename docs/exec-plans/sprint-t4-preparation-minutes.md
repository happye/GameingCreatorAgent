# Sprint T4：Free 套餐“分析分钟数”计量（总方案 §40）

**状态（2026-11-01）：已实现并推送 origin/main（见本提交）。** 工作台“准备录像”在新提交时用本机 ffprobe 读录像时长，按自然月累计到 `.cache/workspace/creations/entitlement-usage.json`（独占锁 + 原子替换）。Free 每月 60 分钟；Creator / Pro / 创始人版不限。超出返回 `entitlement.denied` 中文说明。“套餐与用量”显示本月已用准备分钟。

## 政策（失败批次）

**接受时计数**：新提交在通过忙碌检查并接受任务时写入账本；之后批次失败/部分失败/取消仍占用当月额度。续跑（resume）不探测、不记账。同一项目+相同录像路径本月已记账则不再累加。

## Acceptance

- [x] 仅计量本地媒体准备 submit（非付费视觉账本）
- [x] Free 60 分钟上限；超额拒绝
- [x] 续跑不重复计数
- [x] 失败批次政策写明并测（接受时计数）
- [x] `summary()` / 套餐页展示本月准备分钟

## Verification

```text
pytest tests/test_preparation_minutes.py tests/test_entitlements.py tests/test_media_preparation_jobs.py -p no:cacheprovider --basetemp .cache/pt-t4 -q
```

## Non-claims

不接支付/订阅；不碰付费视觉授权账本；不宣称已做人机联调点击验收（逻辑与摘要字段已测）。
