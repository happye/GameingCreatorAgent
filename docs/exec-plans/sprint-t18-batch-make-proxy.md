# Sprint T18：批量 make-proxy 入口（P011）

**状态（2026-11-01）：已完成（b73a5bd）**

## 目标

为**多条**已登记素材任务（已准备／已分析，即项目库中已有 `MediaAsset` 的 run）排队生成编辑代理；每条仍走既有单条 `make_proxy` 合同（时长字节限额、时长核对、失败整目录删除、收据匹配才复用）。

## 非目标

- 不改代理画质／码率／路径布局
- 不自动切换播放器默认到代理（已有可选开关保留）
- 不做清理入口（仍属 P011 后续）
- 不下载、不付费视觉、不发布、不选 A/B/D、不碰 F006
- 测试不复制大媒体；合成片带字节上限，测完即删

## 设计

### 资格（eligible）

项目 `analysis_runs` 中可 `load_run`、且 `asset.duration_us > 0`、`sha256` 合法、源路径可解析的任务。不要求 `completed`（准备完成尚未分析的也可生成预览代理）。`--run` 显式列出时：缺库／不合格则该条记 `failed`，不中断队列。

### 队列语义

1. **顺序**逐条调用现有 `make_proxy`（同一进程内排队，不并行），保留单条限额与 `finally` 删临时目录。
2. 同批内按 `sourceSha256` **去重**：首条真正 build／reuse；后续同 SHA 记 `shared`（指向首条结果，不再二次编码）。
3. 单条 `ValueError`／`OSError` → 该条 `failed` + 原因；**继续**下一条；失败条不留半成品目录（由 `make_proxy` 保证）。
4. 输出信封 `make-proxy-batch-v1`：`items[]` + `summary{built,reused,shared,failed}`。

### 入口

| 入口 | 行为 |
| --- | --- |
| CLI `make-proxy` | `--run` 可重复；或 `--all-eligible`；互斥于“零 run”。stdout JSON 信封。 |
| `scripts/make-proxy.ps1` | 支持多 `-Run` 与 `-AllEligible`。 |
| POST `/api/make-proxy-batch` | `{project, runs:[...]}` 或 `{project, allEligible:true}`；同步排队，返回同一信封。 |
| 素材工作台 | 素材任务对话框增加「批量生成编辑代理」：对当前项目 `allEligible` 调上述 API，展示摘要。 |

### Acceptance

- [x] sprint 设计先于实现落盘
- [x] 批量模块／CLI／API／工作台入口
- [x] 测试：多 run 排队、同 SHA shared、单条失败不留目录且不影响其他
- [x] 更新 P011 evidence；文档；T18 ✅
