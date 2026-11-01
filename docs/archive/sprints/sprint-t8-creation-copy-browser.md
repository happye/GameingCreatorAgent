# Sprint T8：新界面文案的浏览器测试

**状态（2026-11-01）：已推送 origin/main 2eb9f6c。**

用现有 strict-route 浏览器测试（参考 `tests/test_narration_browser.py`）锁住新文案：成片水印说明、「套餐与用量」水印提示、方案卡「你常用的结构」（`rankedByHistory` 真/假）、时间线导出点击写入 `size`。Mock 登记 entitlement / team / timeline 等端点，未登记路径返回「未模拟」。

## Acceptance

- [x] 成片下「成片右上角带…水印（Free 套餐，生成时确定）」
- [x] 「套餐与用量」`#plan-info` 含水印提示
- [x] 方案卡 `rankedByHistory` true 带「所以排到了通用方案前面」；false 仅「你常用的结构…」无该后缀；无 `localRenders` 不出现该文案
- [x] `#timeline-fcpxml` 点击后 href 含 `size=720x1280`（由 `#size` `720,1280` 转换）

## Verification

```text
pytest tests/test_creation_copy_browser.py -p no:cacheprovider --basetemp .cache/pt-t8 -q
```

## Non-claims

无手动点点点；不接支付/下载/云端；不改产品文案逻辑（仅测已有 UI）。
