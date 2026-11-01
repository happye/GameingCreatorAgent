# Sprint T6：TD021 剩余项

**状态（2026-11-01）：已推送 origin/main（见功能提交 SHA）。**

## 1. 知识库改用 local_files helper

`knowledge_store.py` 读写改为 `local_files.read_bounded` / `write_exclusive_text`。`entries()` 按 mtime 排序时对 `stat` 失败（文件已消失）跳过，不再整表失败。

## 2. Premiere xmeml 变速

按 Apple Final Cut Pro XML Interchange Format 的 Time Remap（`effectid=timeremap`）与 Premiere 常用的恒定速度百分参量，为变速 `clipitem` 写入：

- `<rate><timebase>…</timebase><ntsc>FALSE</ntsc></rate>`（原有）
- `<filter><effect>…timeremap…</effect></filter>`：`variablespeed=0`、`speed` 为百分数、线性 `graphdict` 关键帧

时间线长度与 `in`/`out` 不变。XML 结构测试覆盖。**本机无 Premiere，未做真实导入实测**（仍为非宣称）。

## Acceptance

- [x] knowledge_store 使用 local_files 有界读 / 独占写
- [x] entries() 对消失文件容错
- [x] xmeml 变速写入 timeremap 并有结构测试
- [x] TD021 状态更新

## Verification

```text
pytest tests/test_knowledge.py tests/test_timeline_export.py -p no:cacheprovider --basetemp .cache/pt-t6 -q
```

## Non-claims

未在 Premiere / Final Cut / DaVinci 中实测导入；未接支付/云/下载。
