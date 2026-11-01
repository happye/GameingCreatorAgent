# Sprint T16：CreationJobs.feedback 内容哈希缓存

**状态（2026-11-01）：已完成（待 SHA）**

## 目标

`feedback()` 每次全量扫任务目录并 JSON 解析；增加项目级缓存，用**参与统计的文件内容 SHA-256** 作指纹（非 TTL／纯 mtime）。

## 设计

- 扫描仍读取贡献文件字节以计算指纹（内容失效所必需）。
- 指纹命中：跳过 JSON 结构化汇总，直接返回 `feedback-cache/<sha256(projectId)>.json` 中的 `summary`。
- 未命中：`summarize_feedback` 后原子写入；缓存损坏不挡统计。
- 目录：`.cache/workspace/creations/feedback-cache/`（任务根下，不入作业身份目录）。

## Verification

```text
pytest tests/test_creation_feedback.py -W error --basetemp .cache/pt-t16 -o cache_dir=.cache/pt-t16-c -q
```

## Acceptance

- [x] 命中／未命中／改文件内容后指纹变化有测试
- [ ] 文档同步；T16 ✅
