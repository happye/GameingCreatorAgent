# Sprint T7：发布包水印核验

**状态（2026-11-01）：已推送 origin/main e7c5a2a。**

`package_jobs.verify` 核对包收据 `watermark` 与父成片收据 `watermark` 一致；旧包缺字段视为 `None`。包结果状态带上 `watermark`；创作页发布包结果在有水印时显示「含 Free 水印」。

## Acceptance

- [x] verify 比对父子 watermark（缺省 = None）
- [x] 页面文案「含 Free 水印」
- [x] Free 成片→包→篡改收据→核验失败；旧包无字段仍可通过

## Verification

```text
pytest tests/test_platform_package.py::test_free_package_watermark_matches_and_tamper_fails tests/test_platform_package.py::test_legacy_package_without_watermark_field_still_verifies -p no:cacheprovider --basetemp .cache/pt-t7 -q
```

## Non-claims

不接支付；不做浏览器点点点验收（逻辑与页面文案字段已测）。
