# Sprint：非 200 传输正文有界保留与失败投影

**状态（2026-10-22）：已交付并推送 acca03e。** `HttpxVisionTransport` 对非 200 响应保留有界正文（历史会丢空）；DeepSeek 失败元数据写入 `httpStatus`／`httpErrorProjection`（截断、无凭据）。0 付费／0 真网调用（MockTransport／FakeTransport）；不代选 A／B／D；不声称三缺口已清；不改 feature_list。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`http_transport.py`、`deepseek_vision.py` 失败投影、相关 pytest、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D

## 白话

以前接口返回错误时，程序把错误正文扔掉了，事后只能看到「HTTP 失败」却不知道对方说了啥。现在会在限额内留住正文摘要，方便离线查拒因；仍然不会自动重发、不会花钱。

## Acceptance

- [x] 非 200 有界正文保留；200 压缩仍拒
- [x] 失败 execution_details 含 httpErrorProjection
- [x] 相关 pytest 绿（含既有 httpx 合同用例更新）
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [x] 已推送 `origin/codex/visual-details`（acca03e）
