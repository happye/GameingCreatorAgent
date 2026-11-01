# Sprint T10：企业版增强（P051）

**状态（2026-11-01）：已推送 origin/main 1c08bcc。**

## 背景

P051 已有本机团队模型（角色、品牌词、发布包审核、审核闸沙箱发布），团队存全局 `enterprise-team.json`，审核历史在页面缩成一行，无审计导出。

## 设计

### 1. 按项目团队

- 存储：`.cache/workspace/creations/enterprise/teams/<sha256(projectId)>.json`（内容仍为 `validate_team` 结果）。
- API：`GET/POST /api/enterprise/team` **必须**带 `projectId`（GET query / POST body）。
- `review` / `publish_blockers` 从发布包 `status.projectId` 取团队，不再读全局文件。
- 兼容：若项目文件不存在但旧的全局 `enterprise-team.json` 仍在，**只读**回退到全局（不写入）；`set_team` 只写项目文件。诚实说明不变：姓名自报、非登录账号。

### 2. 审计日志导出

- 追加写：`.cache/workspace/creations/enterprise/audit/<sha256>.jsonl`
  - `team_change`：actor、before/after、`actorSelfReported: true`
  - `review`：packageJobId、action、state、comment、brandIssues、`actorSelfReported: true`
- `GET /api/enterprise/audit?projectId=&format=json|csv`
  - 合并 jsonl 与该项目下各发布包审核记录事件（按 at+package+action+actor 去重），按时间排序。
  - CSV 表头含 `actorSelfReported`，避免被当成登录账号。

### 3. 页面

- 团队面板随当前项目加载/保存；文案标明「操作人姓名由本人填写，不是登录账号」。
- 发布包审核：状态摘要 + `<details>` 可展开逐步历史。
- 提供「导出审计 JSON / CSV」链接（当前项目）。

### 非目标

账号登录、跨设备、席位计费、真发布、付费云。

## Acceptance

- [x] 两项目可设不同团队；审核用包所属项目团队
- [x] 团队变更与审核写入审计；JSON/CSV 导出含自报标记
- [x] 页面可展开审核历史；诚实文案可见
- [x] 旧全局团队只读回退仍可读

## 已交付

- 按项目团队文件 + 旧 `enterprise-team.json` 只读回退
- 审计 jsonl + `GET /api/enterprise/audit` JSON/CSV（`actorSelfReported`）
- 页面：项目团队、展开审核历史、审计导出链接、姓名自报文案
- `tests/test_enterprise.py` 扩展；浏览器 mock 兼容 `projectId` query

## Verification

```text
pytest tests/test_enterprise.py -p no:cacheprovider --basetemp .cache/pt-t10 -q
```
