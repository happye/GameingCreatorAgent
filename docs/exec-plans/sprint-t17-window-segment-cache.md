# Sprint T17：窗口级片段缓存（P008）

**状态（2026-11-01）：已完成（8c69132）**

## 目标

为视觉分析窗口提供**本地**片段结果缓存：键含项目／录像／设置／窗口；读写以**内容哈希**校验；禁止仅靠 TTL／mtime 命中。

## 非目标

不新发起付费视觉；不代选 A／B／D；不宣称 F006；不缓存跨不同 `prompt`／模型／窗口帧内容的结果。

## 设计

### 键（全部进入指纹，缺一不可）

| 分量 | 来源 | 说明 |
| --- | --- | --- |
| project | 项目目录相对仓库的稳定路径字符串（或绝对路径规范化）的 SHA-256 | 隔离项目 |
| recording | `MediaAsset.sha256` | 同源录像 |
| settings | `planned_identity(config)` 的 canonical JSON SHA-256 | 含 prompt／窗口／流水线等，**不含**费用上限 |
| window | 窗口内有序 `evidence.sha256`（及 `evidence_id`）的 digest | 帧内容变则键变 |

总缓存文件名：`sha256(project|recording|settings|window)` 的 hex；目录：`<repository>/.cache/window-segments/`。

### 信封

```text
schemaVersion = window-segment-cache-v1
key = { project, recording, settings, window }  // 各为 hex digest
fingerprint = sha256(canonical(key))           // 与文件名一致
payload.events = [ { sourceRange, observableFacts, mechanicTags, evidenceIds, modality, uncertainty } ]
sha256 = sha256(canonical({schemaVersion,key,fingerprint,payload}))
```

- **命中**：重算 key／fingerprint 与文件名一致，且信封 `sha256` 匹配；否则视为未命中并忽略（可删坏文件）。
- **禁止**：不读 mtime 决定命中；不设过期秒数。
- 缓存内存的事件**不含** `run_id`／`event_id`；读出时按 DeepSeek 同款公式用当前 `run_id` 重铸 `event_id`，以满足库内事件归属。

### 接入点

`_run_pipeline` 视觉窗口循环：`begin_stage` 之后、`ports.vision.analyze` 之前查缓存；成功分析后写入。命中则跳过网络 Provider，仍 `persist_timeline`。

## Acceptance

- [x] sprint 设计先于实现落盘
- [x] 模块 + 命中／内容失效测试
- [x] 分析路径接线（同设置同窗可免重复视觉调用）
- [x] 更新 P008 evidence；文档；T17 ✅

